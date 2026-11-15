"""Rocznice na stronie archiwum (ETAP 58): urodziny, rocznice śmierci i ślubów.

Liczą się tylko pełne daty (dzień, miesiąc i rok, np. 12.06.1921), bo bez dnia nie wiadomo,
kiedy wypada rocznica. Data przybliżona („ok. …”) też się nie liczy. Pokazujemy wczoraj, dziś
i jutro, a gdy w tych dniach nic nie wypada, jedną najbliższą rocznicę z kolejnych tygodni.
"""

import datetime
import re
from dataclasses import dataclass

from django.db.models import Q
from django.utils import timezone

from albums.models import Person

from .models import Partnership

FULL_DATE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")
DAYS = {-1: "Wczoraj", 0: "Dziś", 1: "Jutro"}
LOOK_AHEAD = 60
MONTHS = [
    "stycznia",
    "lutego",
    "marca",
    "kwietnia",
    "maja",
    "czerwca",
    "lipca",
    "sierpnia",
    "września",
    "października",
    "listopada",
    "grudnia",
]


@dataclass
class Anniversary:
    kind: str  # urodziny, urodziny-pamiec, smierc, slub
    icon: str
    people: list
    years: int
    text: str
    date: datetime.date
    offset: int

    @property
    def day_label(self):
        return DAYS.get(self.offset) or day_month(self.date)

    @property
    def is_round(self):
        return self.years >= 10 and (self.years % 10 == 0 or self.years % 25 == 0)

    @property
    def person(self):
        return self.people[0]


def full_date(text):
    """(dzień, miesiąc, rok) z „12.06.1921”; ``None`` dla dat niepełnych i przybliżonych."""
    match = FULL_DATE.fullmatch((text or "").strip())
    if not match:
        return None
    return int(match[1]), int(match[2]), int(match[3])


def day_month(date):
    return f"{date.day} {MONTHS[date.month - 1]}"


def years_word(n):
    """1 rok, 2 lata, 5 lat, 22 lata, 112 lat."""
    if n == 1:
        return "1 rok"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} lata"
    return f"{n} lat"


def _gendered(person, female, male, unknown):
    return {"K": female, "M": male}.get(person.gender, unknown)


def _occurs(day, month, on):
    """Czy rocznica (dzień, miesiąc) wypada w dniu ``on``. 29 lutego obchodzimy 28 lutego."""
    if (day, month) == (29, 2) and not _leap(on.year):
        return (on.day, on.month) == (28, 2)
    return (on.day, on.month) == (day, month)


def _leap(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _alive(person):
    return not person.deceased and not person.death_date


def _events():
    """Wszystkie pełne daty: (rodzaj, osoby, dzień, miesiąc, rok)."""
    people = (
        Person.objects.filter(in_tree=True)
        .select_related("portrait")
        .filter(Q(birth_date__regex=FULL_DATE.pattern) | Q(death_date__regex=FULL_DATE.pattern))
    )
    for person in people:
        if born := full_date(person.birth_date):
            yield ("urodziny" if _alive(person) else "urodziny-pamiec", [person], *born)
        if died := full_date(person.death_date):
            yield ("smierc", [person], *died)
    couples = Partnership.objects.filter(ended=False, since__regex=FULL_DATE.pattern).select_related(
        "person1__portrait", "person2__portrait"
    )
    for couple in couples:
        if wedding := full_date(couple.since):
            yield ("slub", [couple.person1, couple.person2], *wedding)


def _describe(kind, people, years, offset=0):
    person = people[0]
    if kind == "urodziny":
        verb = _gendered(person, "skończyła", "skończył", "skończył(a)") if offset < 0 else "kończy"
        return "🎂", f"{verb} {years_word(years)}"
    if kind == "urodziny-pamiec":
        born = _gendered(person, "urodziła się", "urodził się", "urodziny")
        return "🕯️", f"{born} {years_word(years)} temu"
    if kind == "smierc":
        return "🕊️", f"{years}. rocznica śmierci"
    together = all(_alive(p) for p in people)
    return "💍", f"{years}. rocznica ślubu" if together else f"ślub {years_word(years)} temu"


def anniversaries(today=None):
    """Rocznice z wczoraj, dziś i jutro, od dzisiejszych. Pusta lista, gdy nic nie wypada."""
    return _collect(today, range(-1, 2))


def next_anniversary(today=None):
    """Najbliższa rocznica po jutrze (do ``LOOK_AHEAD`` dni) albo ``None``."""
    found = _collect(today, range(2, LOOK_AHEAD + 1))
    return found[0] if found else None


def _collect(today, offsets):
    today = today or timezone.localdate()
    events = list(_events())
    found = []
    for offset in offsets:
        on = today + datetime.timedelta(days=offset)
        for kind, people, day, month, year in events:
            years = on.year - year
            if years < 1 or not _occurs(day, month, on):
                continue
            icon, text = _describe(kind, people, years, offset)
            found.append(Anniversary(kind, icon, people, years, text, on, offset))
    order = {0: 0, 1: 1, -1: 2}
    found.sort(key=lambda a: (order.get(a.offset, a.offset), -a.is_round, a.person.name))
    return found
