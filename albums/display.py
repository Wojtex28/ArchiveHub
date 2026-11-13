"""Jak album wygląda na liście: ładna nazwa z nazwy folderu, numer i lata.

Nazwy albumów tworzy synchronizacja z nazw folderów („01_BrązowyZeZlotaObramowka97-04_Pocięte”).
Dopóki nikt nie wpisze nazwy w panelu, lista rozkłada ją na czytelne części. Dane w bazie
zostają bez zmian.
"""

import re
from dataclasses import dataclass

from .sync import title_from_folder

# Końcówki folderów, które mówią o stanie skanów, a nie o albumie.
TECHNICAL_WORDS = {"pocięte", "pociete", "skany", "scan", "scany", "gotowe", "nowe", "kopia"}
# Krótkie słowa, które w środku nazwy piszemy małą literą.
SMALL_WORDS = {"i", "a", "w", "we", "z", "ze", "na", "do", "od", "po", "za", "o", "u", "nad", "pod", "dla"}

YEAR_RANGE = re.compile(r"(?<!\d)(\d{2}|\d{4})\s*[-–]\s*(\d{2}|\d{4})(?!\d)")
YEAR_ONE = re.compile(r"(?<!\d)(1[89]\d{2}|20\d{2})(?!\d)")
CAMEL = re.compile(r"[a-ząćęłńóśźż][A-ZĄĆĘŁŃÓŚŹŻ]|[^\W\d_]\d|\d[^\W\d_]")
NUMBER = re.compile(r"^(\d{1,3})(?:\s+|$)")


@dataclass(frozen=True)
class AlbumLabel:
    number: str
    title: str
    years: str


def _full_year(text, after=None):
    year = int(text)
    if len(text) == 4:
        return year
    full = 1900 + year
    # „97-04”: drugi rok mniejszy od pierwszego, więc to już następne stulecie.
    if after is not None and full < after:
        full += 100
    return full


def _split_words(text):
    # „BrązowyZeZlotaObramowka” → „Brązowy Ze Zlota Obramowka”, „Wakacje1978” → „Wakacje 1978”.
    text = re.sub(r"(?<=[^\W\d_])(?=\d)|(?<=\d)(?=[^\W\d_])", " ", text)
    text = re.sub(r"(?<=[^\W\d_])(?<![A-ZĄĆĘŁŃÓŚŹŻ])(?=[A-ZĄĆĘŁŃÓŚŹŻ])", " ", text)
    # „IChrzciny” → „I Chrzciny”, ale „PRL” zostaje razem.
    text = re.sub(r"(?<=[A-ZĄĆĘŁŃÓŚŹŻ])(?=[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż])", " ", text)
    words = text.split()
    while words and words[-1].lower() in TECHNICAL_WORDS:
        words.pop()
    return [
        word.lower() if index and word.lower() in SMALL_WORDS else word for index, word in enumerate(words)
    ]


def album_label(album):
    """Numer, nazwa i lata albumu do pokazania na liście."""
    title = album.title.strip()
    if title != title_from_folder(album.folder) and not CAMEL.search(title):
        # Nazwa wpisana ręcznie w panelu (bez sklejonych słów jak w folderach): bez zmian.
        return AlbumLabel(number="", title=title, years="")
    number = ""
    match = NUMBER.match(title)
    if match and match.end() < len(title):
        number, title = match.group(1), title[match.end() :]
    years = ""
    match = YEAR_RANGE.search(title)
    if match:
        start = _full_year(match.group(1))
        end = _full_year(match.group(2), after=start)
        if 1800 <= start <= end <= 2100:
            years = f"{start}–{end}" if end != start else str(start)
            title = title[: match.start()] + " " + title[match.end() :]
    else:
        match = YEAR_ONE.search(title)
        if match:
            years = match.group(1)
            title = title[: match.start()] + " " + title[match.end() :]
    words = _split_words(title)
    if not words:
        return AlbumLabel(number="", title=album.title.strip(), years=years)
    words[0] = words[0][:1].upper() + words[0][1:]
    return AlbumLabel(number=number, title=" ".join(words), years=years)


PREVIEW_PHOTOS = 6  # miniatury na karcie: okładka, dwie w mozaice, reszta w podglądzie pod myszą


def photo_count_text(count):
    """1 zdjęcie, 3 zdjęcia, 5 zdjęć, 22 zdjęcia."""
    if count == 1:
        return "1 zdjęcie"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return f"{count} zdjęcia"
    return f"{count} zdjęć"


def people_count_text(count):
    if count == 1:
        return "1 osoba"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return f"{count} osoby"
    return f"{count} osób"


@dataclass
class AlbumCard:
    album: object
    label: AlbumLabel
    photos: list
    years: str
    people: int

    @property
    def cover(self):
        return self.photos[0] if self.photos else None

    @property
    def mosaic(self):
        return self.photos[1:3]

    @property
    def meta(self):
        """Np. ["212 zdjęć", "1962–1968", "14 osób"]; każda część w całości w jednej linijce."""
        parts = [photo_count_text(self.album.photo_count)]
        if self.years:
            parts.append(self.years)
        if self.people:
            parts.append(people_count_text(self.people))
        return parts


def album_cards(albums, user):
    """Karty albumów na liście: kilka miniatur, lata (z nazwy albo z dat zdjęć) i liczba osób.

    Stała liczba zapytań niezależnie od liczby albumów.
    """
    from django.db.models import Count, F, Max, Min, Window
    from django.db.models.functions import Coalesce, RowNumber

    from .models import Photo

    albums = list(albums)
    ids = [album.pk for album in albums]
    visible = Photo.objects.visible_to(user).filter(album_id__in=ids, file_missing=False)
    first = visible.annotate(
        row=Window(RowNumber(), partition_by=F("album_id"), order_by=[F("position").asc(), F("pk").asc()])
    ).filter(row__lte=PREVIEW_PHOTOS + 1)
    by_album = {}
    for photo in first:
        by_album.setdefault(photo.album_id, []).append(photo)
    covers = {
        photo.album_id: photo
        for photo in visible.filter(pk__in=[album.cover_id for album in albums if album.cover_id])
    }
    dated = {
        row["album_id"]: row
        for row in visible.filter(year_from__isnull=False)
        .values("album_id")
        .annotate(low=Min("year_from"), high=Max(Coalesce("year_to", "year_from")))
    }
    people = dict(
        Photo.people.through.objects.filter(photo__in=visible)
        .values("photo__album_id")
        .annotate(n=Count("person_id", distinct=True))
        .values_list("photo__album_id", "n")
    )
    cards = []
    for album in albums:
        photos = by_album.get(album.pk, [])
        cover = covers.get(album.pk)
        if cover:
            photos = [cover] + [photo for photo in photos if photo.pk != cover.pk]
        label = album_label(album)
        years = label.years
        if not years and album.pk in dated:
            low, high = dated[album.pk]["low"], dated[album.pk]["high"]
            years = f"{low}–{high}" if high and high != low else str(low)
        cards.append(AlbumCard(album, label, photos[:PREVIEW_PHOTOS], years, people.get(album.pk, 0)))
    return cards
