"""Import albumów z udziału sieciowego ``ARCHIVEHUB_IMPORT_DIR``.

Każdy folder w udziale to album. Folder trafia do importu, gdy jego zawartość
(nazwy i rozmiary plików) nie zmienia się przez ``ARCHIVEHUB_IMPORT_STABLE_MINUTES``,
czyli gdy kopiowanie z Windowsa na pewno się skończyło. Ze skanu powstają trzy pliki:
oryginał do pobrania (JPEG w pełnej rozdzielczości), podgląd na ekran (JPEG,
``ARCHIVEHUB_PREVIEW_MAX_SIDE``) i miniatura (WebP).

Udział jest tylko czytany: aplikacja niczego w nim nie zmienia ani nie usuwa.
Dorzucenie plików do zaimportowanego folderu uruchamia import ponownie;
zdjęcia już obecne w albumie (ta sama nazwa albo ta sama suma kontrolna) są pomijane.
„Przetwórz ponownie” w panelu robi wszystkie pliki albumu od nowa ze skanów w udziale.
"""

import hashlib
import logging
import os
import re
import shutil
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.template.defaultfilters import filesizeformat
from django.utils import timezone
from PIL import Image, ImageOps

from .models import LEGACY_WEB_DIR, ORIGINAL_DIR, PREVIEW_DIR, THUMB_DIR, Album, ImportJob, Photo
from .sync import title_from_folder

logger = logging.getLogger(__name__)

SCAN_EXTENSIONS = {".jpg", ".jpeg", ".tif", ".tiff", ".png"}
PREVIEW_QUALITY = 85
THUMB_QUALITY = 80

# Pliki albumu (JPEG q92 w pełnej rozdzielczości, podgląd, miniatura) zajmują zwykle 25–35% skanów PNG;
# liczymy połowę, z zapasem na skany JPEG i TIFF.
OUTPUT_RATIO = 0.5
# Tyle miejsca musi zostać po imporcie albumu; mniej to ostrzeżenie w Panel → Stan serwera.
MIN_FREE_AFTER_IMPORT = 5 * 1024**3

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


def convert_scan(source, photo, reverse=False):
    """Tworzy oryginał, podgląd i miniaturę zdjęcia (albo rewersu). Zwraca rozmiar oryginału.

    Skan może mieć ponad 100 Mpx, więc obraz jest w pamięci tylko raz: obrót i zmniejszanie
    działają na miejscu, a oryginał jest zapisywany bez optymalizacji wymagającej drugiej kopii.
    """
    original_side = settings.ARCHIVEHUB_ORIGINAL_MAX_SIDE
    with Image.open(source) as scan:
        if original_side:
            # Przy bardzo dużych JPEG-ach dekoder od razu czyta zmniejszony obraz: mniej pamięci.
            scan.draft(scan.mode, (original_side, original_side))
        icc = scan.info.get("icc_profile")
        scan.load()
        ImageOps.exif_transpose(scan, in_place=True)
        image = _to_displayable(scan)
        if original_side:
            image.thumbnail((original_side, original_side), Image.Resampling.LANCZOS)
        # Obrót ustawiony przez rodzinę w galerii przeżywa ponowne przetworzenie albumu.
        rotation = photo.target_rotation(reverse)
        if rotation:
            from .rotation import TRANSPOSE

            image = image.transpose(TRANSPOSE[rotation])
        size = image.size
        # Profil kolorów zostaje (skanery często zapisują AdobeRGB); metadane EXIF nie.
        _save_atomic(
            image,
            photo.original_path(reverse),
            "JPEG",
            quality=settings.ARCHIVEHUB_ORIGINAL_QUALITY,
            icc_profile=icc,
        )
        preview_side = settings.ARCHIVEHUB_PREVIEW_MAX_SIDE
        image.thumbnail((preview_side, preview_side), Image.Resampling.LANCZOS)
        _save_atomic(
            image,
            photo.preview_path(reverse),
            "JPEG",
            quality=PREVIEW_QUALITY,
            optimize=True,
            progressive=True,
            icc_profile=icc,
        )
        thumb_side = settings.ARCHIVEHUB_THUMB_MAX_SIDE
        image.thumbnail((thumb_side, thumb_side), Image.Resampling.LANCZOS)
        _save_atomic(
            image, photo.thumb_path(reverse), "WEBP", quality=THUMB_QUALITY, method=4, icc_profile=icc
        )
    # Stara wersja 5000 px (sprzed pełnej rozdzielczości) nie jest już potrzebna.
    photo.legacy_path(reverse).unlink(missing_ok=True)
    setattr(photo, "reverse_applied_rotation" if reverse else "applied_rotation", rotation)
    return size


def touch_heartbeat():
    """Healthcheck kontenera workera sprawdza, czy ten plik jest świeży (także w trakcie długiego importu)."""
    try:
        (Path(settings.DATA_DIR) / "import-worker.heartbeat").touch()
    except OSError:
        logger.warning("Import: nie można zapisać pliku heartbeat")


# --- Kolejka folderów ---------------------------------------------------------


def scan_import_dir(now=None):
    """Jedno przejście po udziale: zauważa nowe i zmienione foldery, importuje najwyżej jeden gotowy.

    Po jednym folderze na przejście, żeby przy imporcie wielu albumów worker między nimi
    obracał zdjęcia i robił kopię bazy. Zwraca listę importów zakończonych w tym przejściu.
    """
    now = now or timezone.now()
    root = import_dir()
    if not root.is_dir():
        return []
    stable_for = timedelta(minutes=settings.ARCHIVEHUB_IMPORT_STABLE_MINUTES)
    finished = _run_reprocess_requests(root)
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
                job.note = ""
                job.save(update_fields=["signature", "stable_since", "note"])
            elif now - job.stable_since >= stable_for and not finished and _has_room(job, files):
                finished.append(run_import(job, folder))
    return finished


def free_space():
    return shutil.disk_usage(settings.DATA_DIR).free


def estimated_output(source_bytes):
    """Ile miejsca zajmą pliki albumu ze skanów o tym rozmiarze (szacunek z zapasem)."""
    return int(source_bytes * OUTPUT_RATIO)


def _has_room(job, files):
    """Czy po imporcie folderu zostanie zapas miejsca; jeśli nie, folder czeka z notatką w panelu."""
    needed = estimated_output(sum(f.stat().st_size for f in files))
    try:
        free = free_space()
    except OSError:
        return True  # nie da się sprawdzić: import i tak zgłosi błąd zapisu
    if free - needed >= MIN_FREE_AFTER_IMPORT:
        if job.note:
            job.note = ""
            job.save(update_fields=["note"])
        return True
    note = (
        f"Czeka na miejsce na dysku: album zajmie ok. {filesizeformat(needed)}, "
        f"wolne {filesizeformat(free)}, a zostać musi {filesizeformat(MIN_FREE_AFTER_IMPORT)}."
    )
    if job.note != note:
        logger.warning("Import: %s %s", job.folder, note[0].lower() + note[1:])
        job.note = note
        job.save(update_fields=["note"])
    return False


def _run_reprocess_requests(root):
    finished = []
    for album in Album.objects.filter(reprocess_requested=True):
        if finished:
            break  # następne albumy w kolejnych przejściach
        folder = root / album.folder
        latest = ImportJob.objects.filter(folder=album.folder).first()
        if latest is not None and latest.status == ImportJob.WAITING and folder.is_dir():
            # Folder wciąż się kopiuje: ponowne przetworzenie poczeka na koniec kopiowania.
            continue
        album.reprocess_requested = False
        album.save(update_fields=["reprocess_requested"])
        if not folder.is_dir():
            ImportJob.objects.create(
                folder=album.folder,
                album=album,
                is_reprocess=True,
                status=ImportJob.FAILED,
                error=(
                    f"W udziale nie ma folderu „{album.folder}”. Wrzuć skany ponownie i kliknij jeszcze raz."
                ),
                finished_at=timezone.now(),
            )
            continue
        job = ImportJob.objects.create(
            folder=album.folder,
            album=album,
            is_reprocess=True,
            signature=folder_signature(_scan_files(folder)),
        )
        finished.append(run_import(job, folder, regenerate=True))
    return finished


def queue_legacy_albums():
    """Albumy z wersjami 5000 px z pierwszego wydania importu trafiają do ponownego przetworzenia."""
    queued = 0
    for album in Album.objects.filter(reprocess_requested=False):
        if any(
            photo.legacy_path().is_file() and not photo.original_path().is_file()
            for photo in album.photos.all()
        ):
            album.reprocess_requested = True
            album.save(update_fields=["reprocess_requested"])
            queued += 1
    return queued


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


def run_import(job, folder, regenerate=False):
    job.status = ImportJob.PROCESSING
    job.started_at = timezone.now()
    job.note = ""
    job.save(update_fields=["status", "started_at", "note"])
    logger.info("Import: zaczynam %s%s", folder.name, " (ponowne przetworzenie)" if regenerate else "")
    try:
        _import_folder(job, folder, regenerate=regenerate)
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


def _import_folder(job, folder, regenerate=False):
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
    job.photos_total = len(fronts)
    job.save(update_fields=["photos_total"])
    taken_names = {name.lower() for name in album.photos.values_list("name", flat=True)}
    taken_checksums = set(album.photos.values_list("checksum", flat=True))
    position = (album.photos.aggregate(top=Max("position"))["top"] or 0) + 1
    regenerated = set()

    for key in sorted(fronts, key=natural_key):
        source = fronts[key]
        reverse = reverses.pop(key, None)
        if key in taken_names:
            existing = album.photos.filter(name__iexact=source.stem).first()
            if regenerate and existing is not None:
                _regenerate(job, existing, source, reverse)
                regenerated.add(existing.pk)
            elif reverse is not None and existing is not None and not existing.has_reverse:
                # Rewers dorzucony później do zdjęcia, które już jest w albumie.
                _attach_reverse(job, existing, reverse)
                existing.save(update_fields=["has_reverse", "reverse_checksum", "reverse_applied_rotation"])
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
            photo.width, photo.height = convert_scan(source, photo)
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
    if regenerate:
        for photo in album.photos.exclude(pk__in=regenerated):
            job.skipped.append(f"{photo.source_name}: brak skanu w udziale, zostaje dotychczasowa wersja")

    album.photo_count = album.photos.count()
    album.save(update_fields=["photo_count", "updated_at"])
    for name in (ORIGINAL_DIR, PREVIEW_DIR, THUMB_DIR):
        (album.path / name).mkdir(parents=True, exist_ok=True)
    try:
        (album.path / LEGACY_WEB_DIR).rmdir()
    except OSError:
        pass  # brak folderu albo zostały w nim pliki zdjęć bez skanu w udziale


def _regenerate(job, photo, source, reverse):
    try:
        photo.width, photo.height = convert_scan(source, photo)
    except Exception as exc:
        logger.warning("Import: nie udało się przetworzyć %s: %s", source.name, exc)
        job.skipped.append(f"{source.name}: nie udało się odczytać pliku ({exc.__class__.__name__})")
        return
    photo.source_name = source.name
    job.photos_added += 1
    if reverse is not None:
        had_reverse, old_checksum = photo.has_reverse, photo.reverse_checksum
        photo.has_reverse = False
        _attach_reverse(job, photo, reverse)
        job.reverses_added += int(photo.has_reverse)
        if had_reverse and not photo.has_reverse:
            # Nieudane przetworzenie rewersu: zostaje jego dotychczasowa wersja.
            photo.has_reverse, photo.reverse_checksum = True, old_checksum
    elif photo.has_reverse:
        job.skipped.append(f"{photo.file_stem(True)}: brak rewersu w udziale, zostaje dotychczasowa wersja")
    photo.save(
        update_fields=[
            "width",
            "height",
            "source_name",
            "has_reverse",
            "reverse_checksum",
            "applied_rotation",
            "reverse_applied_rotation",
        ]
    )
    job.save(update_fields=["photos_added", "reverses_added", "skipped"])
    touch_heartbeat()


def _attach_reverse(job, photo, reverse):
    try:
        photo.reverse_checksum = file_checksum(reverse)
        convert_scan(reverse, photo, reverse=True)
        photo.has_reverse = True
    except Exception as exc:
        logger.warning("Import: nie udało się przetworzyć rewersu %s: %s", reverse.name, exc)
        photo.reverse_checksum = ""
        job.skipped.append(f"{reverse.name}: nie udało się odczytać rewersu ({exc.__class__.__name__})")


# --- Podgląd udziału w panelu -------------------------------------------------


SHARE_STATES = {
    "new": "nowy",
    "copying": "trwa kopiowanie",
    "queued": "w kolejce",
    ImportJob.PROCESSING: "importowanie",
    ImportJob.DONE: "zaimportowany",
    ImportJob.FAILED: "błąd",
    "changed": "dorzucone pliki",
}


@dataclass
class ShareFolder:
    name: str
    photos: int
    reverses: int
    size: int
    orphan_reverses: list
    job: ImportJob | None
    signature: str

    @property
    def state(self):
        job = self.job
        if job is None:
            return "new"
        if job.signature != self.signature:
            # Worker zauważy zmianę w najbliższym przejściu.
            return "changed" if job.status in (ImportJob.DONE, ImportJob.FAILED) else "copying"
        if job.status == ImportJob.WAITING:
            return "queued" if job.is_queued else "copying"
        return job.status

    @property
    def state_label(self):
        return SHARE_STATES[self.state]

    @property
    def is_pending(self):
        return self.state not in (ImportJob.DONE, ImportJob.FAILED)


def share_overview():
    """Foldery w udziale importu z liczbą zdjęć, rozmiarem i stanem importu (dla Panel → Synchronizacja).

    Zwraca (lista ShareFolder, szacowane miejsce na foldery jeszcze niezaimportowane).
    """
    root = import_dir()
    if not root.is_dir():
        return [], 0
    latest = {}
    for job in ImportJob.objects.order_by("created_at", "pk"):
        latest[job.folder] = job
    folders, pending_bytes = [], 0
    for folder in sorted(root.iterdir(), key=lambda p: natural_key(p.name)):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        try:
            files = _scan_files(folder)
            size = sum(f.stat().st_size for f in files)
        except OSError:
            continue
        if not files:
            continue
        fronts, reverses = _split_reverses(files)
        row = ShareFolder(
            name=folder.name,
            photos=len(fronts),
            reverses=len(reverses),
            size=size,
            orphan_reverses=sorted(r.name for key, r in reverses.items() if key not in fronts),
            job=latest.get(folder.name),
            signature=folder_signature(files),
        )
        if row.is_pending:
            pending_bytes += size
        folders.append(row)
    return folders, estimated_output(pending_bytes)


def seconds_per_photo():
    """Średni czas importu jednego zdjęcia (z rewersem) z ostatnich importów; None, gdy brak danych."""
    current = ImportJob.objects.filter(status=ImportJob.PROCESSING).exclude(started_at=None).first()
    if current is not None and current.photos_added >= 5:
        return (timezone.now() - current.started_at).total_seconds() / current.photos_added
    seconds = photos = 0
    for job in ImportJob.objects.filter(status=ImportJob.DONE).exclude(started_at=None)[:10]:
        if job.photos_added:
            seconds += (job.finished_at - job.started_at).total_seconds()
            photos += job.photos_added
    return seconds / photos if photos else None


def queue_summary(folders):
    """Podsumowanie kolejki: ile folderów i zdjęć zostało oraz ile to potrwa (szacunek)."""
    pending = [f for f in folders if f.is_pending]
    current = ImportJob.objects.filter(status=ImportJob.PROCESSING).first()
    photos_left = sum(f.photos for f in pending if f.state != ImportJob.PROCESSING)
    if current is not None:
        photos_left += max(current.photos_total - current.photos_added, 0)
    per_photo = seconds_per_photo()
    return {
        "folders": len(pending),
        "photos": photos_left,
        "seconds": per_photo * photos_left if per_photo is not None and photos_left else None,
        "current": current,
        "failed": sum(1 for f in folders if f.state == ImportJob.FAILED),
        "done": sum(1 for f in folders if f.state == ImportJob.DONE),
    }
