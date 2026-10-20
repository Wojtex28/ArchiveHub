"""Obracanie zdjęć przez rodzinę.

Kliknięcie ↺/↻ w galerii od razu zapisuje docelowy obrót w bazie, a przeglądarka obraca obraz
sama (CSS). Pliki (oryginał do pobrania, podgląd, miniaturę) obraca worker, gdy przez
``ARCHIVEHUB_ROTATION_DELAY_SECONDS`` nikt już tego zdjęcia nie obracał: kilka kliknięć pod rząd
to jedno przeliczenie pliku, a nie kilka.
"""

import fcntl
import logging
import os
from contextlib import contextmanager
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from PIL import Image

from .importer import PREVIEW_QUALITY, THUMB_QUALITY, touch_heartbeat
from .models import Photo

logger = logging.getLogger("albums.importer")

STEP = 90
# Obrót zgodnie z ruchem wskazówek zegara; Pillow liczy przeciwnie.
TRANSPOSE = {
    90: Image.Transpose.ROTATE_270,
    180: Image.Transpose.ROTATE_180,
    270: Image.Transpose.ROTATE_90,
}


def rotate(photo, user, reverse=False, clockwise=True):
    """Obraca zdjęcie (albo rewers) o 90° i zwraca nowy obrót. Zapis od razu, bez potwierdzania."""
    field = "reverse_rotation" if reverse else "rotation"
    step = STEP if clockwise else -STEP
    with transaction.atomic():
        current = Photo.objects.select_for_update().get(pk=photo.pk)
        value = (getattr(current, field) + step) % 360
        changes = {field: value, "rotated_at": timezone.now(), "rotated_by": user}
        Photo.objects.filter(pk=photo.pk).update(**changes)
    setattr(photo, field, value)
    logger.info("%s obrócił(a) %s%s: %s°", user, photo, " (rewers)" if reverse else "", value)
    return value


def _rotate_file(path, delta, fmt, **options):
    """Obraca plik i zapisuje go obok jako plik tymczasowy. Zwraca ścieżkę tymczasową (albo None)."""
    if not path.is_file():
        return None
    with Image.open(path) as image:
        icc = image.info.get("icc_profile")
        rotated = image.transpose(TRANSPOSE[delta])
    tmp = path.with_name(f".{path.name}.obrot")
    try:
        rotated.save(tmp, fmt, icc_profile=icc, **options)
    finally:
        rotated.close()
    return tmp


@contextmanager
def _photo_lock(photo):
    """Worker i aplikacja (pobieranie) mogą chcieć obrócić te same pliki naraz; obracają po kolei."""
    folder = photo.album.path
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / ".obracanie.lock", "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def bake(photo, reverse=False, heartbeat=False):
    """Obraca pliki zdjęcia (albo rewersu) do obrotu z galerii. Bezpieczne przy wywołaniu naraz."""
    with _photo_lock(photo):
        # Stan sprzed blokady mógł się zmienić: ktoś inny właśnie obrócił pliki.
        photo.refresh_from_db()
        _bake(photo, reverse, heartbeat)


def _bake(photo, reverse, heartbeat):
    delta = photo.pending_rotation(reverse)
    if not delta:
        return
    # Najpierw wszystkie trzy pliki obok, potem szybka podmiana: przerwanie nie zostawia
    # zdjęcia z obróconą miniaturą i nieobróconym oryginałem.
    staged = []
    try:
        for path, fmt, options in (
            (photo.original_path(reverse), "JPEG", {"quality": settings.ARCHIVEHUB_ORIGINAL_QUALITY}),
            (
                photo.preview_path(reverse),
                "JPEG",
                {"quality": PREVIEW_QUALITY, "optimize": True, "progressive": True},
            ),
            (photo.thumb_path(reverse), "WEBP", {"quality": THUMB_QUALITY, "method": 4}),
        ):
            tmp = _rotate_file(path, delta, fmt, **options)
            if tmp:
                staged.append((tmp, path))
            if heartbeat:
                touch_heartbeat()
    except Exception:
        for tmp, _ in staged:
            tmp.unlink(missing_ok=True)
        raise
    for tmp, path in staged:
        os.replace(tmp, path)

    target = photo.target_rotation(reverse)
    if reverse:
        photo.reverse_applied_rotation = target
        Photo.objects.filter(pk=photo.pk).update(reverse_applied_rotation=target)
    else:
        photo.applied_rotation = target
        if delta in (90, 270):
            photo.width, photo.height = photo.height, photo.width
        Photo.objects.filter(pk=photo.pk).update(
            applied_rotation=target, width=photo.width, height=photo.height
        )
    logger.info("Obrót: zapisano w plikach %s%s (%s°)", photo, " (rewers)" if reverse else "", target)


def apply_rotations(now=None):
    """Zapisuje w plikach obroty, których nikt nie zmieniał od chwili. Zwraca liczbę obróconych zdjęć."""
    now = now or timezone.now()
    settled = now - timedelta(seconds=settings.ARCHIVEHUB_ROTATION_DELAY_SECONDS)
    waiting = Photo.objects.filter(
        ~Q(rotation=F("applied_rotation")) | ~Q(reverse_rotation=F("reverse_applied_rotation")),
        rotated_at__lte=settled,
    ).select_related("album")
    done = 0
    for photo in waiting:
        try:
            bake(photo, reverse=False, heartbeat=True)
            if photo.has_reverse:
                bake(photo, reverse=True, heartbeat=True)
            done += 1
        except Exception:
            logger.exception("Obrót: nie udało się obrócić plików %s", photo)
    return done
