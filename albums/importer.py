"""Import albumów z udziału sieciowego ``ARCHIVEHUB_IMPORT_DIR``.

Każdy folder w udziale to album. Folder trafia do importu, gdy jego zawartość
(nazwy i rozmiary plików) nie zmienia się przez ``ARCHIVEHUB_IMPORT_STABLE_MINUTES``,
czyli gdy kopiowanie z Windowsa na pewno się skończyło. Ze skanu powstaje wersja
do oglądania (JPEG, dłuższy bok ``ARCHIVEHUB_WEB_MAX_SIDE``) i miniatura (WebP).

Udział jest tylko czytany: aplikacja niczego w nim nie zmienia ani nie usuwa.
Dorzucenie plików do zaimportowanego folderu uruchamia import ponownie;
zdjęcia już obecne w albumie (ta sama nazwa albo ta sama suma kontrolna) są pomijane.
"""

import hashlib
import logging
import os
import re
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from PIL import Image, ImageOps

from .models import THUMB_DIR, WEB_DIR, Album, ImportJob, Photo
from .sync import title_from_folder

logger = logging.getLogger(__name__)

SCAN_EXTENSIONS = {".jpg", ".jpeg", ".tif", ".tiff", ".png"}
WEB_QUALITY = 85
THUMB_QUALITY = 80

# Skany z importu są zaufane i bywają duże (np. 12000 × 9000 px); domyślny limit Pillow jest niższy.
Image.MAX_IMAGE_PIXELS = 400_000_000


def import_dir():
    return Path(settings.ARCHIVEHUB_IMPORT_DIR)


def _scan_files(folder):
    return sorted(
        f
        for f in folder.iterdir()
        if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in SCAN_EXTENSIONS
    )


def folder_signature(files):
    """Odcisk zawartości folderu: zmienia się, gdy dochodzi plik albo plik wciąż się kopiuje."""
    digest = hashlib.sha256()
    for f in files:
        digest.update(f"{f.name}\0{f.stat().st_size}\n".encode())
    return digest.hexdigest()


def natural_key(name):
    """„2” przed „10”: kolejność jak w Eksploratorze Windows."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def file_checksum(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --- Konwersja ----------------------------------------------------------------


def _to_displayable(image):
    """Tryby skanerów (16-bit, CMYK, z przezroczystością) zamienia na RGB albo skalę szarości."""
    if image.mode in ("I;16", "I;16B", "I;16L", "I"):
        return image.point(lambda value: value / 256).convert("L")
    if image.mode in ("RGB", "L"):
        return image
    return image.convert("RGB")


def _save_atomic(image, target, fmt, **options):
    """Zapis do pliku tymczasowego i podmiana: przerwany import nie zostawia uszkodzonego pliku."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp")
    image.save(tmp, fmt, **options)
    os.replace(tmp, target)


def convert_scan(source, web_target, thumb_target):
    """Tworzy wersję do oglądania i miniaturę. Zwraca rozmiar wersji do oglądania."""
    web_side = settings.ARCHIVEHUB_WEB_MAX_SIDE
    with Image.open(source) as original:
        # Przy bardzo dużych JPEG-ach dekoder od razu czyta zmniejszony obraz: mniej pamięci.
        original.draft(original.mode, (web_side, web_side))
        icc = original.info.get("icc_profile")
        image = _to_displayable(ImageOps.exif_transpose(original))
        image.thumbnail((web_side, web_side), Image.Resampling.LANCZOS)
    # Profil kolorów zostaje (skanery często zapisują AdobeRGB); metadane EXIF nie.
    _save_atomic(
        image, web_target, "JPEG", quality=WEB_QUALITY, optimize=True, progressive=True, icc_profile=icc
    )
    thumb_side = settings.ARCHIVEHUB_THUMB_MAX_SIDE
    image.thumbnail((thumb_side, thumb_side), Image.Resampling.LANCZOS)
    _save_atomic(image, thumb_target, "WEBP", quality=THUMB_QUALITY, method=4, icc_profile=icc)
    return image_size(web_target)


def image_size(path):
    with Image.open(path) as image:
        return image.size


def touch_heartbeat():
    """Healthcheck kontenera workera sprawdza, czy ten plik jest świeży (także w trakcie długiego importu)."""
    try:
        (Path(settings.DATA_DIR) / "import-worker.heartbeat").touch()
    except OSError:
        logger.warning("Import: nie można zapisać pliku heartbeat")


# --- Kolejka folderów ---------------------------------------------------------


def scan_import_dir(now=None):
    """Jedno przejście po udziale: zauważa nowe i zmienione foldery, importuje te gotowe.

    Zwraca listę importów zakończonych w tym przejściu.
    """
    now = now or timezone.now()
    root = import_dir()
    if not root.is_dir():
        return []
    stable_for = timedelta(minutes=settings.ARCHIVEHUB_IMPORT_STABLE_MINUTES)
    finished = []
    for folder in sorted(root.iterdir(), key=lambda p: natural_key(p.name)):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        try:
            files = _scan_files(folder)
            if not files:
                continue
            signature = folder_signature(files)
        except OSError:
            logger.exception("Import: nie można odczytać folderu %s", folder)
            continue

        job = ImportJob.objects.filter(folder=folder.name).first()
        if job is None or (job.signature != signature and job.status in (ImportJob.DONE, ImportJob.FAILED)):
            ImportJob.objects.create(folder=folder.name, signature=signature, stable_since=now)
            logger.info("Import: nowy folder %s, czekam na koniec kopiowania", folder.name)
        elif job.status == ImportJob.WAITING:
            if job.signature != signature:
                job.signature = signature
                job.stable_since = now
                job.save(update_fields=["signature", "stable_since"])
            elif now - job.stable_since >= stable_for:
                finished.append(run_import(job, folder))
    return finished


def reset_interrupted():
    """Po restarcie: import przerwany w połowie zaczyna się od nowa (gotowe zdjęcia są pomijane)."""
    return ImportJob.objects.filter(status=ImportJob.PROCESSING).update(status=ImportJob.WAITING)


# --- Import jednego folderu ---------------------------------------------------


def _split_reverses(files):
    suffix = settings.ARCHIVEHUB_REVERSE_SUFFIX.lower()
    fronts, reverses = {}, {}
    for f in files:
        stem = f.stem
        if suffix and stem.lower().endswith(suffix) and len(stem) > len(suffix):
            reverses.setdefault(stem[: -len(suffix)].lower(), f)
        else:
            fronts.setdefault(stem.lower(), f)
    return fronts, reverses


def run_import(job, folder):
    job.status = ImportJob.PROCESSING
    job.save(update_fields=["status"])
    logger.info("Import: zaczynam %s", folder.name)
    try:
        _import_folder(job, folder)
        job.status = ImportJob.DONE
    except Exception as exc:
        logger.exception("Import: błąd w folderze %s", folder.name)
        job.status = ImportJob.FAILED
        job.error = str(exc) or exc.__class__.__name__
    job.finished_at = timezone.now()
    job.save()
    logger.info(
        "Import: %s %s, zdjęcia: %s, rewersy: %s, pominięte: %s",
        folder.name,
        job.get_status_display(),
        job.photos_added,
        job.reverses_added,
        len(job.skipped),
    )
    return job


def _import_folder(job, folder):
    album, created = Album.objects.get_or_create(
        folder=folder.name,
        defaults={"title": title_from_folder(folder.name), "is_hidden": folder.name.startswith("_")},
    )
    if album.folder_missing:
        album.folder_missing = False
        album.save(update_fields=["folder_missing", "updated_at"])
    job.album = album
    job.save(update_fields=["album"])

    fronts, reverses = _split_reverses(_scan_files(folder))
    taken_names = {name.lower() for name in album.photos.values_list("name", flat=True)}
    taken_checksums = set(album.photos.values_list("checksum", flat=True))
    position = (album.photos.aggregate(top=Max("position"))["top"] or 0) + 1

    for key in sorted(fronts, key=natural_key):
        source = fronts[key]
        reverse = reverses.pop(key, None)
        if key in taken_names:
            existing = album.photos.filter(name__iexact=source.stem).first()
            if reverse is not None and existing is not None and not existing.has_reverse:
                # Rewers dorzucony później do zdjęcia, które już jest w albumie.
                _attach_reverse(job, existing, reverse)
                existing.save(update_fields=["has_reverse", "reverse_checksum"])
                job.reverses_added += int(existing.has_reverse)
                job.save(update_fields=["reverses_added", "skipped"])
            continue
        try:
            checksum = file_checksum(source)
            if checksum in taken_checksums:
                job.skipped.append(f"{source.name}: to samo zdjęcie jest już w albumie")
                continue
            photo = Photo(
                album=album, name=source.stem, source_name=source.name, position=position, checksum=checksum
            )
            photo.width, photo.height = convert_scan(source, photo.web_path(), photo.thumb_path())
        except Exception as exc:
            logger.warning("Import: nie udało się przetworzyć %s/%s: %s", folder.name, source.name, exc)
            job.skipped.append(f"{source.name}: nie udało się odczytać pliku ({exc.__class__.__name__})")
            continue

        if reverse is not None:
            _attach_reverse(job, photo, reverse)

        with transaction.atomic():
            photo.save()
        taken_names.add(key)
        taken_checksums.add(checksum)
        position += 1
        job.photos_added += 1
        job.reverses_added += int(photo.has_reverse)
        # Postęp widać w panelu na bieżąco.
        job.save(update_fields=["photos_added", "reverses_added", "skipped"])
        touch_heartbeat()

    for reverse in reverses.values():
        job.skipped.append(f"{reverse.name}: rewers bez zdjęcia głównego")

    album.photo_count = album.photos.count()
    album.save(update_fields=["photo_count", "updated_at"])
    (album.path / WEB_DIR).mkdir(parents=True, exist_ok=True)
    (album.path / THUMB_DIR).mkdir(parents=True, exist_ok=True)


def _attach_reverse(job, photo, reverse):
    try:
        photo.reverse_checksum = file_checksum(reverse)
        convert_scan(reverse, photo.web_path(reverse=True), photo.thumb_path(reverse=True))
        photo.has_reverse = True
    except Exception as exc:
        logger.warning("Import: nie udało się przetworzyć rewersu %s: %s", reverse.name, exc)
        photo.reverse_checksum = ""
        job.skipped.append(f"{reverse.name}: nie udało się odczytać rewersu ({exc.__class__.__name__})")
