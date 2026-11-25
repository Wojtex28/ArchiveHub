"""Zdjęcia w tle strony logowania: zmniejszanie przy wgrywaniu."""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from PIL import Image, ImageOps, UnidentifiedImageError

from .models import LoginPhoto

# Zdjęcie w tle ma najwyżej ~300 px szerokości na ekranie; 900 px wystarcza z zapasem na ekrany retina.
MAX_SIDE = 900
MAX_UPLOAD_BYTES = 40 * 1024 * 1024


def save_login_photo(uploaded):
    """Zapisuje wgrany plik jako mały JPEG bez metadanych (EXIF, GPS)."""
    if uploaded.size > MAX_UPLOAD_BYTES:
        raise ValidationError(f"{uploaded.name}: plik jest większy niż 40 MB.")
    try:
        with Image.open(uploaded) as source:
            # draft() każe dekoderowi JPEG od razu czytać zmniejszony obraz, co oszczędza pamięć przy skanach.
            source.draft("RGB", (MAX_SIDE * 2, MAX_SIDE * 2))
            image = ImageOps.exif_transpose(source).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValidationError(f"{uploaded.name}: to nie jest obsługiwany plik zdjęcia.") from exc

    return _store(image)


def save_login_photo_from_album(source):
    """0.61.0: kopia zdjęcia z albumu (wersja do oglądania, z obrotem, którego nie ma jeszcze w pliku)."""
    path = source.preview_path() if source.preview_path().is_file() else source.legacy_path()
    try:
        with Image.open(path) as opened:
            opened.draft("RGB", (MAX_SIDE * 2, MAX_SIDE * 2))
            image = opened.convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError(f"{source}: brak pliku zdjęcia na dysku.") from exc
    if source.pending_front:
        image = image.rotate(-source.pending_front, expand=True)  # CSS obraca w prawo, Pillow w lewo
    return _store(image, source_photo=source)


def _store(image, source_photo=None):
    image.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    photo = LoginPhoto(key=uuid.uuid4(), width=image.width, height=image.height, source_photo=source_photo)
    settings.ARCHIVEHUB_LOGIN_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    # Pillow zapisuje EXIF tylko na wyraźne żądanie, więc plik nie niesie danych z aparatu (np. GPS).
    image.save(photo.path, "JPEG", quality=82, optimize=True, progressive=True)
    try:
        photo.save()
    except Exception:
        photo.path.unlink(missing_ok=True)
        raise
    return photo


def delete_login_photo(photo):
    path = photo.path
    photo.delete()
    transaction.on_commit(lambda: path.unlink(missing_ok=True))


def login_background():
    """Dane dla skryptu tła na stronie logowania."""
    return [
        {"src": reverse("login_photo", args=[p.key]), "w": p.width, "h": p.height}
        for p in LoginPhoto.objects.filter(is_active=True)
    ]
