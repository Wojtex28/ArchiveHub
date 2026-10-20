"""Pobieranie zdjęć w pełnej rozdzielczości: pojedynczo albo zaznaczone jako ZIP.

ZIP powstaje w locie, kawałek po kawałku, bez plików tymczasowych: nawet cały album
(ponad 1 GB) nie zajmuje pamięci ani dysku serwera. Zdjęcia JPEG już są skompresowane,
więc archiwum ich nie kompresuje drugi raz (szybciej, ten sam rozmiar).
"""

import re
import unicodedata
import zipfile
from datetime import datetime
from urllib.parse import quote

from .rotation import bake

CHUNK = 1024 * 1024
UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def safe_name(text):
    """Nazwa pliku bez znaków, których nie lubi Windows. Polskie litery zostają."""
    return " ".join(UNSAFE.sub(" ", text).split()).strip(" .") or "zdjecie"


def attachment_header(name):
    """Content-Disposition z nazwą w UTF-8 i zapasową bez polskich liter (dla starszych przeglądarek)."""
    ascii_name = unicodedata.normalize("NFKD", name.replace("ł", "l").replace("Ł", "L"))
    ascii_name = ascii_name.encode("ascii", "ignore").decode().replace('"', "")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"


def file_name(photo, reverse=False):
    return f"{safe_name(photo.file_stem(reverse))}.jpg"


def ready_original(photo, reverse=False):
    """Plik do pobrania z obrotem z galerii (obraca go od razu, jeśli worker jeszcze nie zdążył)."""
    if photo.pending_rotation(reverse):
        bake(photo, reverse)
    path = photo.original_path(reverse)
    if not path.is_file():
        # Album sprzed pełnej rozdzielczości, jeszcze nie przetworzony ponownie.
        path = photo.legacy_path(reverse)
    return path if path.is_file() else None


class _Sink:
    """Plik „tylko do zapisu”: zipfile pisze tu, a generator oddaje zebrane bajty przeglądarce."""

    def __init__(self):
        self._parts = []

    def write(self, data):
        self._parts.append(bytes(data))
        return len(data)

    def flush(self):
        pass

    def drain(self):
        data = b"".join(self._parts)
        self._parts.clear()
        return data


def zip_stream(photos, folder):
    """Kolejne kawałki archiwum ZIP z oryginałami zdjęć (i rewersami) w folderze ``folder``."""
    sink = _Sink()
    with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        for photo in photos:
            sides = [False, True] if photo.has_reverse else [False]
            for reverse in sides:
                path = ready_original(photo, reverse)
                if path is None:
                    continue
                info = zipfile.ZipInfo(
                    f"{folder}/{file_name(photo, reverse)}",
                    date_time=datetime.fromtimestamp(path.stat().st_mtime).timetuple()[:6],
                )
                with path.open("rb") as source, archive.open(info, "w", force_zip64=True) as target:
                    while chunk := source.read(CHUNK):
                        target.write(chunk)
                        yield sink.drain()
                yield sink.drain()
    yield sink.drain()
