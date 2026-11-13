"""Zdjęcia wgrane wprost do osoby (ETAP 56): zmniejszanie, data z aparatu, usuwanie plików."""

import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from PIL import Image, ImageOps, UnidentifiedImageError

from albums.dates import DateError, parse_date

from .models import PersonPhoto

MAX_SIDE = 2560
THUMB_SIDE = 640
MAX_UPLOAD_BYTES = 40 * 1024 * 1024
MAX_FILES = 20

# Znaczniki EXIF: data zrobienia zdjęcia (w części Exif) i data zapisu pliku (w głównej).
EXIF_IFD = 0x8769
DATE_TAKEN = 0x9003
DATE_SAVED = 0x0132


def year_of(text):
    """Rok do sortowania z tekstu daty („lata 20.” → 1924); zła data podnosi ValidationError."""
    try:
        date = parse_date(text)
    except DateError as exc:
        raise ValidationError(str(exc)) from None
    return (date.year_from + date.year_to) // 2 if date else None


def _camera_date(image):
    """Data zrobienia zdjęcia z aparatu albo telefonu, jako „dd.mm.rrrr”, albo None."""
    exif = image.getexif()
    raw = exif.get_ifd(EXIF_IFD).get(DATE_TAKEN) or exif.get(DATE_SAVED)
    try:
        taken = datetime.datetime.strptime(str(raw).strip()[:19], "%Y:%m:%d %H:%M:%S")
    except (TypeError, ValueError):
        return None
    if not 1900 <= taken.year <= datetime.date.today().year:
        return None
    return taken.strftime("%d.%m.%Y")


def save_person_photo(person, uploaded, user=None, date="", caption=""):
    """Zapisuje wgrany plik jako JPEG bez metadanych (EXIF, GPS) w dwóch rozmiarach.

    Bez wpisanej daty bierze datę z aparatu, a gdy jej nie ma, dzisiejszą.
    """
    if uploaded.size > MAX_UPLOAD_BYTES:
        raise ValidationError(f"{uploaded.name}: plik jest większy niż 40 MB.")
    try:
        with Image.open(uploaded) as source:
            taken = _camera_date(source)
            # draft(): dekoder JPEG od razu czyta zmniejszony obraz, mniej pamięci przy dużych plikach.
            source.draft("RGB", (MAX_SIDE, MAX_SIDE))
            image = ImageOps.exif_transpose(source).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValidationError(f"{uploaded.name}: to nie jest obsługiwany plik zdjęcia.") from exc

    date = " ".join((date or "").split()) or taken or datetime.date.today().strftime("%d.%m.%Y")
    image.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    photo = PersonPhoto(
        person=person,
        width=image.width,
        height=image.height,
        date=date,
        year=year_of(date),
        caption=(caption or "").strip()[:200],
        added_by=user if user is not None and user.is_authenticated else None,
    )
    settings.ARCHIVEHUB_PERSON_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    # Pillow zapisuje EXIF tylko na wyraźne żądanie, więc plik nie niesie danych z aparatu (np. GPS).
    image.save(photo.path, "JPEG", quality=85, optimize=True, progressive=True)
    image.thumbnail((THUMB_SIDE, THUMB_SIDE), Image.Resampling.LANCZOS)
    image.save(photo.thumb_path, "JPEG", quality=80, optimize=True)
    try:
        photo.save()
    except Exception:
        _unlink(photo)
        raise
    return photo


def _unlink(photo):
    photo.path.unlink(missing_ok=True)
    photo.thumb_path.unlink(missing_ok=True)


def can_remove(user, photo):
    """Usunąć może ten, kto wgrał zdjęcie, albo master. Inni mogą je tylko opisać."""
    return user.is_superuser or (photo.added_by_id is not None and photo.added_by_id == user.pk)


def delete_person_photo(photo):
    photo.delete()  # pliki usuwa sygnał po zapisie w bazie (family.models)
