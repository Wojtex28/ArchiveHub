"""Chronologia życia osoby (ETAP 46): oś czasu na karcie osoby.

Część zdarzeń bierze się sama z drzewa (urodzenie, śluby, dzieci, śmierć bliskich, śmierć),
resztę rodzina dopisuje ręcznie (:class:`family.models.LifeEvent`).
"""

from dataclasses import dataclass

from . import tree
from .models import LifeEvent

# Słowa zależne od płci krewnego: (kobieta, mężczyzna, nie wiadomo).
WORDS = {
    "child_born": ("Urodziła się córka", "Urodził się syn", "Urodziło się dziecko:"),
    "parent_died": ("Śmierć matki:", "Śmierć ojca:", "Śmierć rodzica:"),
    "partner_died": ("Śmierć żony:", "Śmierć męża:", "Śmierć partnera:"),
    "child_died": ("Śmierć córki:", "Śmierć syna:", "Śmierć dziecka:"),
}


@dataclass
class Item:
    year: int | None
    when: str
    icon: str
    title: str
    place: str = ""
    note: str = ""
    age: str = ""
    event: LifeEvent | None = None  # zdarzenie wpisane ręcznie (da się je poprawić i usunąć)


def _word(key, other):
    return WORDS[key][{"K": 0, "M": 1}.get(other.gender, 2)]


def years_text(n):
    if n == 1:
        return "1 rok"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} lata"
    return f"{n} lat"


def timeline(person):
    """Zdarzenia od najstarszych; te bez daty na końcu."""
    items = []
    if person.birth_date or person.birth_place:
        items.append(Item(person.birth_year, person.birth_date, "✶", "Urodzenie", person.birth_place))
    for other in tree.partners_in_order(person):
        couple = other.couple
        if couple.since:
            items.append(Item(couple.since_year, couple.since, "💍", f"Ślub: {other.name}"))
        if other.death_year and _within_life(person, other.death_year):
            items.append(
                Item(other.death_year, other.death_date, "✝", f"{_word('partner_died', other)} {other.name}")
            )
    for child in tree.children(person):
        if child.birth_year:
            title = f"{_word('child_born', child)} {child.name}"
            items.append(Item(child.birth_year, child.birth_date, "👶", title, child.birth_place))
        if child.death_year and _within_life(person, child.death_year):
            items.append(
                Item(child.death_year, child.death_date, "✝", f"{_word('child_died', child)} {child.name}")
            )
    for parent in tree.parents(person):
        if parent.death_year and _within_life(person, parent.death_year):
            items.append(
                Item(
                    parent.death_year, parent.death_date, "✝", f"{_word('parent_died', parent)} {parent.name}"
                )
            )
    for event in person.life_events.all():
        items.append(
            Item(event.year, event.when, event.icon, event.heading, event.place, event.note, event=event)
        )
    if person.death_date or person.death_place or person.deceased:
        items.append(Item(person.death_year, person.death_date, "✝", "Śmierć", person.death_place))
    for item in items:
        if item.year is not None and person.birth_year is not None and item.title != "Urodzenie":
            age = item.year - person.birth_year
            if 0 < age < 120:
                item.age = years_text(age)
    # Urodzenie zawsze pierwsze, śmierć ostatnia wśród zdarzeń z tego samego roku.
    rank = {"Urodzenie": 0, "Śmierć": 2}
    return sorted(items, key=lambda item: (item.year is None, item.year or 0, rank.get(item.title, 1)))


def _within_life(person, year):
    """Śmierć bliskich pokazujemy tylko za życia osoby (o ile znamy jej lata)."""
    if person.birth_year is not None and year < person.birth_year:
        return False
    return person.death_year is None or year <= person.death_year
