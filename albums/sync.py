"""Synchronizacja biblioteki: każdy folder w ``ARCHIVEHUB_ALBUMS_DIR`` to album.

Na razie liczymy tylko zdjęcia w folderze. Konwersję, miniatury i rewersy
dokłada ETAP 4. Nic nie jest kasowane: album bez folderu dostaje znacznik
„brak folderu” i znika z archiwum, ale zostaje w bazie z uprawnieniami.
"""

import logging
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Album, SyncReport

logger = logging.getLogger(__name__)

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}


def albums_dir():
    return Path(settings.ARCHIVEHUB_ALBUMS_DIR)


def _is_visible_entry(path):
    return not path.name.startswith(".")


def _count_photos(folder):
    return sum(
        1
        for f in folder.iterdir()
        if f.is_file() and _is_visible_entry(f) and f.suffix.lower() in PHOTO_EXTENSIONS
    )


def _title_from_folder(name):
    return " ".join(name.lstrip("_").replace("_", " ").split()) or name


def sync_albums(triggered_by=None):
    report = SyncReport.objects.create(triggered_by=triggered_by)
    root = albums_dir()
    try:
        root.mkdir(parents=True, exist_ok=True)
        found = {
            entry.name: _count_photos(entry)
            for entry in root.iterdir()
            if entry.is_dir() and _is_visible_entry(entry)
        }
    except OSError as exc:
        logger.exception("Synchronizacja: nie można odczytać %s", root)
        report.error = f"Nie można odczytać folderu biblioteki: {exc.strerror or exc}"
        report.finished_at = timezone.now()
        report.save()
        return report

    with transaction.atomic():
        existing = {album.folder: album for album in Album.objects.all()}
        for name, count in sorted(found.items()):
            album = existing.get(name)
            if album is None:
                Album.objects.create(
                    folder=name,
                    title=_title_from_folder(name),
                    # Folder z „_” na początku nazwy jest ukryty, dopóki go nie odkryjesz w panelu.
                    is_hidden=name.startswith("_"),
                    photo_count=count,
                )
                report.new_albums.append(name)
            elif album.photo_count != count or album.folder_missing:
                album.photo_count = count
                album.folder_missing = False
                album.save(update_fields=["photo_count", "folder_missing", "updated_at"])
        for name, album in existing.items():
            if name not in found:
                if not album.folder_missing:
                    album.folder_missing = True
                    album.save(update_fields=["folder_missing", "updated_at"])
                report.missing_albums.append(name)

    report.albums_total = len(found)
    report.photos_total = sum(found.values())
    report.finished_at = timezone.now()
    report.save()
    logger.info(
        "Synchronizacja: %s albumów, %s zdjęć, nowe: %s, bez folderu: %s",
        report.albums_total,
        report.photos_total,
        len(report.new_albums),
        len(report.missing_albums),
    )
    return report
