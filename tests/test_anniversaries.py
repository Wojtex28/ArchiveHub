"""ETAP 58: rocznice na stronie archiwum."""

import datetime

import pytest
from django.urls import reverse

from family import anniversaries, tree
from family.models import Partnership

TODAY = datetime.date(2026, 11, 15)


def person(name, born="", died="", gender=""):
    someone = tree.add_person(None, name)
    someone.birth_date, someone.death_date = born, died
    someone.deceased = bool(died)
    if gender:
        someone.gender = gender
    someone.save()
    return someone


@pytest.fixture
def family(db):
    hanna = person("Hanna Gargała", born="16.11.1962")
    stefania = person("Stefania Bereza", born="15.11.1902", died="10.03.1997")
    jozef = person("Józef Bereza", died="14.11.1956")
    person("Bez dnia", born="1950")
    person("Przybliżona", born="ok. 1950")
    tree.add_relation(None, hanna, stefania, tree.PARENT)
    jan = person("Jan Szyndlar", died="1925")
    tree.add_relation(None, stefania, jan, tree.PARTNER)
    tree.edit_couple(None, stefania, jan, "15.11.1920", False)
    return hanna, stefania, jozef


def test_yesterday_today_tomorrow(family):
    found = anniversaries.anniversaries(TODAY)
    rows = [(a.day_label, a.icon, [p.name for p in a.people], a.text) for a in found]
    assert rows == [
        ("Dziś", "🕯️", ["Stefania Bereza"], "urodziła się 124 lata temu"),
        ("Dziś", "💍", ["Stefania Bereza", "Jan Szyndlar"], "ślub 106 lat temu"),
        ("Jutro", "🎂", ["Hanna Gargała"], "kończy 64 lata"),
        ("Wczoraj", "🕊️", ["Józef Bereza"], "70. rocznica śmierci"),
    ]
    assert [a.is_round for a in found] == [False, False, False, True]


def test_living_couple_and_divorce(db):
    a, b = person("Anna Nowak"), person("Piotr Nowak")
    tree.add_relation(None, a, b, tree.PARTNER)
    tree.edit_couple(None, a, b, "15.11.1976", False)
    [item] = anniversaries.anniversaries(TODAY)
    assert item.text == "50. rocznica ślubu" and item.is_round
    Partnership.objects.update(ended=True)
    assert anniversaries.anniversaries(TODAY) == []


def test_next_anniversary_and_leap_day(db):
    person("Ola Leap", born="29.02.2000", gender="K")
    assert anniversaries.anniversaries(TODAY) == []
    upcoming = anniversaries.next_anniversary(datetime.date(2027, 2, 20))
    assert (upcoming.date, upcoming.day_label, upcoming.text) == (
        datetime.date(2027, 2, 28),
        "28 lutego",
        "kończy 27 lat",
    )
    assert anniversaries.next_anniversary(TODAY) is None
    [item] = anniversaries.anniversaries(datetime.date(2027, 3, 1))
    assert (item.day_label, item.text) == ("Wczoraj", "skończyła 27 lat")


def test_years_word():
    assert [anniversaries.years_word(n) for n in (1, 2, 5, 12, 22, 25, 104, 112)] == [
        "1 rok",
        "2 lata",
        "5 lat",
        "12 lat",
        "22 lata",
        "25 lat",
        "104 lata",
        "112 lat",
    ]


def test_archive_home_shows_section(client, make_user, family, monkeypatch):
    monkeypatch.setattr(anniversaries.timezone, "localdate", lambda: TODAY)
    monkeypatch.setattr("core.views.timezone.localdate", lambda: TODAY)
    client.force_login(make_user("Karolina"))
    page = client.get(reverse("archive")).content.decode()
    assert "Rocznice" in page and "kończy 64 lata" in page and "okrągła rocznica" in page
    assert page.index("Rocznice") < page.index("Albumy")


def test_hidden_without_tree_access(client, make_user, family, monkeypatch):
    monkeypatch.setattr(anniversaries.timezone, "localdate", lambda: TODAY)
    client.force_login(make_user("Ola", tree_access="none"))
    assert "Rocznice" not in client.get(reverse("archive")).content.decode()
