"""Kalendarium (ETAP 63): jedna oś czasu całej rodziny, od najdawniejszych lat.

Na osi są urodzenia, śluby i śmierci z drzewa, zdarzenia z życia osób (:class:`LifeEvent`, te same co
na kartach osób) i wydarzenia rodzinne (:class:`FamilyEvent`). Każde da się opisać: opis urodzenia,
śmierci i ślubu trafia do osoby albo pary, więc widać go też w chronologii na karcie osoby.

Lata bez wydarzeń nie zajmują miejsca: między latami z wydarzeniami jest tylko odstęp zależny od
liczby pustych lat, a rok z wieloma wydarzeniami rośnie razem z nimi.
"""

from dataclasses import dataclass, field

from django.urls import reverse
from django.utils.html import escape
from django.utils.safestring import mark_safe

from albums.models import Person, Photo

from .anniversaries import full_date
from .models import FamilyEvent, LifeEvent, Partnership

# Co pokazać (?pokaz=): klucz, etykieta i rodzaje wpisów.
FILTERS = {
    "wszystko": ("Wszystko", None),
    "rodzina": ("Urodzenia, śluby, śmierci", {"urodzenie", "slub", "smierc"}),
    "zdarzenia": ("Zdarzenia z życia", {"zdarzenie"}),
    "rodzinne": ("Wydarzenia rodzinne", {"rodzinne"}),
}
# Kolejność w obrębie roku, gdy nie znamy dnia: urodzenia, zdarzenia, śluby, śmierci.
RANK = {"urodzenie": 0, "rodzinne": 1, "zdarzenie": 1, "slub": 2, "smierc": 3}


@dataclass
class Entry:
    kind: str  # urodzenie, slub, smierc, zdarzenie, rodzinne
    key: str  # cel opisu: u-<osoba>, s-<osoba>, p-<para>, z-<zdarzenie>, r-<wydarzenie rodzinne>
    year: int
    when: str
    icon: str
    label: str
    title: str
    place: str = ""
    note: str = ""
    people: list = field(default_factory=list)  # (imię i nazwisko, adres karty, id osoby)
    photo: object = None
    family_event: FamilyEvent | None = None
    day: tuple = (0, 0)
    side: str = "left"
    raw_note: str | None = None  # sam opis do edycji (przy śmierci bez pochówku)

    def __post_init__(self):
        if self.raw_note is None:
            self.raw_note = self.note

    @property
    def title_html(self):
        """Tytuł z imionami osób jako linkami do ich kart."""
        html = str(escape(self.title))
        for name, url, _ in self.people:
            shown = str(escape(name))
            html = html.replace(shown, f'<a href="{escape(url)}">{shown}</a>', 1)
        return mark_safe(html)  # noqa: S308 - tekst przeszedł przez escape

    @property
    def anchor(self):
        return f"k-{self.key}"


def _gendered(person, female, male, unknown):
    return {"K": female, "M": male}.get(person.gender, unknown)


def _link(person):
    return (person.name, reverse("family:person", args=[person.pk]), person.pk)


def _day(text):
    date = full_date(text)
    return (date[1], date[0]) if date else (0, 0)


def entries(user):
    """Wszystkie wpisy z rokiem, od najstarszych."""
    people = {p.pk: p for p in Person.objects.filter(in_tree=True)}
    found = []
    for person in people.values():
        if person.birth_year is not None:
            verb = _gendered(person, "Urodziła się", "Urodził się", "Urodziny:")
            found.append(
                Entry(
                    "urodzenie",
                    f"u-{person.pk}",
                    person.birth_year,
                    person.birth_date,
                    "✶",
                    "Urodzenie",
                    f"{verb} {person.name}",
                    person.birth_place,
                    person.birth_note,
                    [_link(person)],
                    day=_day(person.birth_date),
                )
            )
        if person.death_year is not None:
            verb = _gendered(person, "Zmarła", "Zmarł", "Śmierć:")
            note = "\n".join(
                t
                for t in (person.death_note, person.burial_place and f"Pochówek: {person.burial_place}")
                if t
            )
            found.append(
                Entry(
                    "smierc",
                    f"s-{person.pk}",
                    person.death_year,
                    person.death_date,
                    "✝",
                    "Śmierć",
                    f"{verb} {person.name}",
                    person.death_place,
                    note,
                    [_link(person)],
                    day=_day(person.death_date),
                    raw_note=person.death_note,
                )
            )
    for pair in Partnership.objects.filter(since_year__isnull=False):
        first, second = people.get(pair.person1_id), people.get(pair.person2_id)
        if first is None or second is None:
            continue
        found.append(
            Entry(
                "slub",
                f"p-{pair.pk}",
                pair.since_year,
                pair.since,
                "💍",
                "Ślub",
                f"Ślub: {first.name} i {second.name}",
                pair.place,
                pair.note,
                [_link(first), _link(second)],
                day=_day(pair.since),
            )
        )
    events = LifeEvent.objects.filter(year__isnull=False, person__in_tree=True).select_related("photo")
    visible = set()
    wanted = [e.photo_id for e in events if e.photo_id]
    if wanted:
        visible = set(Photo.objects.visible_to(user).filter(pk__in=wanted).values_list("pk", flat=True))
    for event in events:
        person = people[event.person_id]
        found.append(
            Entry(
                "zdarzenie",
                f"z-{event.pk}",
                event.year,
                event.when,
                event.icon,
                event.get_kind_display(),
                f"{person.name}: {event.heading}",
                event.shown_place,
                event.note,
                [_link(person)],
                photo=event.photo if event.photo_id in visible else None,
                day=_day(event.date),
            )
        )
    for event in FamilyEvent.objects.filter(year__isnull=False):
        found.append(
            Entry(
                "rodzinne",
                f"r-{event.pk}",
                event.year,
                event.date,
                event.icon,
                "Wydarzenie rodzinne",
                event.title,
                event.place,
                event.note,
                family_event=event,
                day=_day(event.date),
            )
        )
    found.sort(key=lambda e: (e.year, e.day, RANK[e.kind], e.title))
    return found


def years(found):
    """Wpisy pogrupowane według lat, z odstępem do poprzedniego roku z wydarzeniami.

    ``gap`` to liczba pustych lat przed tym rokiem; szablon zamienia ją na wysokość odstępu
    (``gap_size`` 0–4) i podpis „14 lat później” przy dłuższych przerwach.
    """
    result = []
    for entry in found:
        if not result or result[-1]["year"] != entry.year:
            gap = entry.year - result[-1]["year"] - 1 if result else 0
            size = 0 if gap <= 0 else 1 if gap <= 3 else 2 if gap <= 9 else 3 if gap <= 24 else 4
            result.append({"year": entry.year, "gap": gap, "gap_size": size, "entries": []})
        result[-1]["entries"].append(entry)
    side = 0
    for year in result:
        for entry in year["entries"]:
            entry.side = "left" if side % 2 == 0 else "right"
            side += 1
    return result


def decades(grouped):
    """Dziesięciolecia do szybkiego skoku: (dekada, kotwica pierwszego roku z tej dekady)."""
    seen = {}
    for year in grouped:
        seen.setdefault(year["year"] // 10 * 10, f"rok-{year['year']}")
    return list(seen.items())


def filtered(found, show=None, person=None):
    kinds = FILTERS.get(show, FILTERS["wszystko"])[1]
    if kinds is not None:
        found = [e for e in found if e.kind in kinds]
    if person is not None:
        found = [e for e in found if any(pk == person.pk for _, _, pk in e.people)]
    return found
