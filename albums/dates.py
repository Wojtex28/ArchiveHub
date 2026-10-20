"""Daty zdjęć wpisywane po ludzku: „1965”, „ok. 1965”, „lata 60.”, „czerwiec 1965”, „12.06.1965”.

Rodzina rzadko zna dokładny dzień, więc data to tekst do wyświetlenia plus zakres lat
(``year_from``–``year_to``), po którym ETAP 14 będzie szukał i sortował. Data przybliżona
(„ok.”, „około”, „~”) dostaje zakres ± ``APPROX_YEARS``, żeby „ok. 1965” znalazło się też
przy szukaniu 1964 albo 1966.
"""

import datetime
import re
from dataclasses import dataclass

APPROX_YEARS = 2
EARLIEST_YEAR = 1800

# Początki nazw miesięcy wystarczą na mianownik i dopełniacz („czerwiec”, „czerwca”).
MONTHS = [
    ("stycz", "styczeń"),
    ("lut", "luty"),
    ("mar", "marzec"),
    ("kwie", "kwiecień"),
    ("maj", "maj"),
    ("czerw", "czerwiec"),
    ("lip", "lipiec"),
    ("sierp", "sierpień"),
    ("wrze", "wrzesień"),
    ("paźdz", "październik"),
    ("pazdz", "październik"),
    ("listop", "listopad"),
    ("grud", "grudzień"),
]
MONTH_NUMBERS = {
    "styczeń": 1,
    "luty": 2,
    "marzec": 3,
    "kwiecień": 4,
    "maj": 5,
    "czerwiec": 6,
    "lipiec": 7,
    "sierpień": 8,
    "wrzesień": 9,
    "październik": 10,
    "listopad": 11,
    "grudzień": 12,
}
SEASONS = {
    "wiosna": "wiosna",
    "wiosną": "wiosna",
    "lato": "lato",
    "latem": "lato",
    "jesień": "jesień",
    "jesienią": "jesień",
    "zima": "zima",
    "zimą": "zima",
}

APPROX = re.compile(r"^(?:około|ok\.?|ca\.?|circa|~)(?=[\s\d]|$)\s*", re.IGNORECASE)
YEAR = r"(\d{4})"
DASH = r"\s*[-–—]\s*"


class DateError(ValueError):
    pass


@dataclass(frozen=True)
class PhotoDate:
    text: str = ""
    year_from: int | None = None
    year_to: int | None = None

    def __bool__(self):
        return bool(self.text)


def _year(value):
    year = int(value)
    if not EARLIEST_YEAR <= year <= datetime.date.today().year:
        raise DateError(f"Rok {year} wygląda na pomyłkę.")
    return year


def _month_name(word):
    word = word.lower()
    for prefix, name in MONTHS:
        if word.startswith(prefix):
            return name
    return None


def _exact(text):
    """Część bez „ok.”: zwraca (tekst do wyświetlenia, rok od, rok do) albo None."""
    if match := re.fullmatch(YEAR, text):
        year = _year(match[1])
        return str(year), year, year

    if match := re.fullmatch(YEAR + DASH + r"(\d{2}|\d{4})", text):
        start = _year(match[1])
        if len(match[2]) == 2 and int(match[1][2:]) > int(match[2]) and 1 <= int(match[2]) <= 12:
            # „1965-06” to czerwiec 1965, a nie zakres wstecz.
            return _month_year(int(match[2]), match[1])
        end = _year(match[2] if len(match[2]) == 4 else match[1][:2] + match[2])
        if end < start:
            raise DateError("Koniec zakresu jest wcześniejszy niż początek.")
        if end == start:
            return str(start), start, start
        return f"{start}–{end}", start, end

    # „lata 60.”, „lata 60-te”, „lata 1960.”; dwie cyfry to XX wiek.
    if match := re.fullmatch(r"lata\s+(\d{2}|\d{4})(?:\.|-te|te)?", text, re.IGNORECASE):
        decade = match[1]
        start = int(decade) if len(decade) == 4 else 1900 + int(decade)
        if start % 10:
            raise DateError("Przy „lata …” podaj dziesięciolecie, np. lata 60.")
        _year(start)
        end = min(start + 9, datetime.date.today().year)
        shown = f"lata {start % 100:02d}." if 1900 <= start < 2000 else f"lata {start}."
        return shown, start, end

    if match := re.fullmatch(r"(\w+)\s+" + YEAR, text):
        word = match[1].lower()
        year = _year(match[2])
        if word in SEASONS:
            return f"{SEASONS[word]} {year}", year, year
        if name := _month_name(word):
            return f"{name} {year}", year, year
        return None

    # Miesiąc i rok: 06.1965, 6/1965, 1965-06.
    if match := re.fullmatch(r"(\d{1,2})[./]" + YEAR, text):
        return _month_year(int(match[1]), match[2])
    if match := re.fullmatch(YEAR + r"-(\d{1,2})", text):
        return _month_year(int(match[2]), match[1])

    # Pełna data: 12.06.1965, 12/6/1965, 1965-06-12, „12 czerwca 1965”.
    if match := re.fullmatch(r"(\d{1,2})[./](\d{1,2})[./]" + YEAR, text):
        return _day(int(match[1]), int(match[2]), match[3])
    if match := re.fullmatch(YEAR + r"-(\d{1,2})-(\d{1,2})", text):
        return _day(int(match[3]), int(match[2]), match[1])
    if match := re.fullmatch(r"(\d{1,2})\s+(\w+)\s+" + YEAR, text):
        name = _month_name(match[2])
        if name:
            return _day(int(match[1]), MONTH_NUMBERS[name], match[3])
    return None


def _month_year(month, year):
    year = _year(year)
    if not 1 <= month <= 12:
        raise DateError(f"Miesiąc {month} nie istnieje.")
    return f"{month:02d}.{year}", year, year


def _day(day, month, year):
    year = _year(year)
    try:
        datetime.date(year, month, day)
    except ValueError:
        raise DateError(f"Dzień {day}.{month}.{year} nie istnieje.") from None
    return f"{day:02d}.{month:02d}.{year}", year, year


def parse_date(value):
    """Tekst z formularza na :class:`PhotoDate`. Pusty tekst to brak daty."""
    text = " ".join((value or "").split())
    if not text:
        return PhotoDate()
    rest = APPROX.sub("", text, count=1)
    approx = rest != text
    if approx and not rest:
        raise DateError("Po „ok.” wpisz rok, np. ok. 1965.")
    parsed = _exact(rest)
    if parsed is None:
        raise DateError("Nie rozumiem tej daty. Spróbuj np. ok. 1965, lata 60. albo 12.06.1965.")
    shown, start, end = parsed
    if approx:
        this_year = datetime.date.today().year
        return PhotoDate(f"ok. {shown}", start - APPROX_YEARS, min(end + APPROX_YEARS, this_year))
    return PhotoDate(shown, start, end)
