"""Pobieranie zdjęć w pełnej rozdzielczości: pojedynczo, zaznaczone albo cały album jako ZIP.

ZIP powstaje w locie, kawałek po kawałku, bez plików tymczasowych: nawet cały album
(ponad 1 GB) nie zajmuje pamięci ani dysku serwera. Zdjęcia JPEG już są skompresowane,
więc archiwum ich nie kompresuje drugi raz (szybciej, ten sam rozmiar).

Każdy pobierany ZIP zajmuje wątek serwera na cały czas pobierania (minuty przy dużym albumie),
więc naraz pobiera się najwyżej ``ARCHIVEHUB_MAX_ZIP_DOWNLOADS`` ZIP-ów; reszta strony działa dalej.
"""

import fcntl
import re
import unicodedata
import zipfile
from datetime import datetime
from urllib.parse import quote

from django.conf import settings

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


def original_file(photo, reverse=False):
    """Plik oryginału, który dostanie rodzina (bez obracania), albo None."""
    path = photo.original_path(reverse)
    if not path.is_file():
        # Album sprzed pełnej rozdzielczości, jeszcze nie przetworzony ponownie.
        path = photo.legacy_path(reverse)
    return path if path.is_file() else None


def download_size(photos):
    """Przybliżony rozmiar ZIP-a z tymi zdjęciami (i rewersami), w bajtach."""
    total = 0
    for photo in photos:
        for reverse in [False, True] if photo.has_reverse else [False]:
            path = original_file(photo, reverse)
            if path is not None:
                total += path.stat().st_size
    return total


def ready_original(photo, reverse=False):
    """Plik do pobrania z obrotem z galerii (obraca go od razu, jeśli worker jeszcze nie zdążył)."""
    if photo.pending_rotation(reverse):
        bake(photo, reverse)
    return original_file(photo, reverse)


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


def take_zip_slot():
    """Miejsce na jeden pobierany ZIP (blokada pliku, wspólna dla wszystkich procesów serwera).

    Zwraca otwarty plik, którego zamknięcie zwalnia miejsce, albo None, gdy wszystkie są zajęte.
    Po awarii procesu system sam zdejmuje blokadę, więc miejsce nie zostaje zajęte na zawsze.
    """
    folder = settings.DATA_DIR / "pobieranie"
    folder.mkdir(parents=True, exist_ok=True)
    for number in range(settings.ARCHIVEHUB_MAX_ZIP_DOWNLOADS):
        handle = open(folder / f"zip-{number}.lock", "w")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            continue
        return handle
    return None


class ZipDownload:
    """Treść odpowiedzi z ZIP-em. Serwer woła ``close()`` po wysłaniu albo przerwaniu pobierania."""

    def __init__(self, photos, folder, slot):
        self._stream = zip_stream(photos, folder)
        self._slot = slot

    def __iter__(self):
        return self._stream

    def close(self):
        self._stream.close()
        self._slot.close()
