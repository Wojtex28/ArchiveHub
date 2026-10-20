"""Synchronizacja biblioteki: każdy folder w ``ARCHIVEHUB_ALBUMS_DIR`` to album.

Zdjęcia do biblioteki wkłada import (``albums.importer``). Synchronizacja sprawdza,
czy biblioteka zgadza się z bazą. Nic nie jest kasowane: album bez folderu
i zdjęcie bez pliku dostają tylko znacznik i trafiają do raportu.
"""

import logging
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Album, Photo, SyncReport

logger = logging.getLogger(__name__)


def albums_dir():
    return Path(settings.ARCHIVEHUB_ALBUMS_DIR)


def title_from_folder(name):
    return " ".join(name.lstrip("_").replace("_", " ").split()) or name


def sync_albums(triggered_by=None):
    report = SyncReport.objects.create(triggered_by=triggered_by)
    root = albums_dir()
    try:
        root.mkdir(parents=True, exist_ok=True)
        found = {entry.name for entry in root.iterdir() if entry.is_dir() and not entry.name.startswith(".")}
    except OSError as exc:
        logger.exception("Synchronizacja: nie można odczytać %s", root)
        report.error = f"Nie można odczytać folderu biblioteki: {exc.strerror or exc}"
        report.finished_at = timezone.now()
        report.save()
        return report

    with transaction.atomic():
        existing = {album.folder: album for album in Album.objects.all()}
        for name in sorted(found - existing.keys()):
            Album.objects.create(
                folder=name,
                title=title_from_folder(name),
                # Folder z „_” na początku nazwy jest ukryty, dopóki go nie odkryjesz w panelu.
                is_hidden=name.startswith("_"),
            )
            report.new_albums.append(name)
        for name, album in existing.items():
            missing = name not in found
            if missing:
                report.missing_albums.append(name)
            if album.folder_missing != missing:
                album.folder_missing = missing
                album.save(update_fields=["folder_missing", "updated_at"])

        for photo in Photo.objects.select_related("album").filter(album__folder__in=found):
            missing = not photo.web_path().is_file() or not photo.thumb_path().is_file()
            if missing:
                report.missing_photos.append(f"{photo.album.folder}/{photo.name}")
            if photo.file_missing != missing:
                photo.file_missing = missing
                photo.save(update_fields=["file_missing"])

        for album in Album.objects.filter(folder__in=found):
            count = album.photos.filter(file_missing=False).count()
            if album.photo_count != count:
                album.photo_count = count
                album.save(update_fields=["photo_count", "updated_at"])

    visible = Album.objects.filter(folder__in=found)
    report.albums_total = visible.count()
    report.photos_total = sum(visible.values_list("photo_count", flat=True))
    report.finished_at = timezone.now()
    report.save()
    logger.info(
        "Synchronizacja: %s albumów, %s zdjęć, nowe: %s, bez folderu: %s, brak plików: %s",
        report.albums_total,
        report.photos_total,
        len(report.new_albums),
        len(report.missing_albums),
        len(report.missing_photos),
    )
    return report
