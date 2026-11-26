"""ETAP 63: Kalendarium, jedna oś czasu rodziny z opisami widocznymi też na kartach osób."""

import pytest
from django.test import Client
from django.urls import reverse

from albums.models import Person
from family import kalendarium, tree
from family.models import FamilyEvent, LifeEvent, Partnership, TreeChange


@pytest.fixture
def editor(client, make_user):
    user = make_user("Karolina")
    client.force_login(user)
    client.user = user
    return client


@pytest.fixture
def family(db):
    anna = Person.objects.create(
        name="Anna Bereza", in_tree=True, gender="K", birth_date="12.06.1921", death_date="1990"
    )
    jan = Person.objects.create(name="Jan Bereza", in_tree=True, gender="M", birth_date="1918")
    tree.add_relation(None, anna, jan, tree.PARTNER)
    tree.edit_couple(None, anna, jan, "1945", False)
    return anna, jan


def test_entries_years_and_gaps(family, make_user):
    anna, jan = family
    found = kalendarium.entries(make_user("Ola"))
    assert [(e.year, e.kind) for e in found] == [
        (1918, "urodzenie"),
        (1921, "urodzenie"),
        (1945, "slub"),
        (1990, "smierc"),
    ]
    assert found[1].title == "Urodziła się Anna Bereza"
    assert 'href="/drzewo/osoba/' in found[2].title_html
    years = kalendarium.years(found)
    assert [y["gap"] for y in years] == [0, 2, 23, 44]
    assert [y["gap_size"] for y in years] == [0, 1, 3, 4]
    assert [e.side for y in years for e in y["entries"]] == ["left", "right", "left", "right"]


def test_page_shows_timeline_and_filters(editor, family):
    page = editor.get(reverse("family:kalendarium")).content.decode()
    assert "Kalendarium" in page and 'id="rok-1945"' in page and "23 lat bez wpisów" in page
    assert "+ Dodaj wydarzenie" in page
    page = editor.get(reverse("family:kalendarium") + "?pokaz=rodzinne").content.decode()
    assert 'id="rok-1945"' not in page
    anna, _ = family
    page = editor.get(reverse("family:kalendarium") + f"?osoba={anna.pk}").content.decode()
    assert "Tylko: Anna Bereza" in page and 'id="rok-1918"' not in page


def test_notes_reach_person_card_with_history(editor, family):
    anna, jan = family
    pair = Partnership.objects.get()
    url = reverse("family:kalendarium_note")
    editor.post(url, {"klucz": f"u-{anna.pk}", "opis": "W domu przy Kościuszki."})
    editor.post(url, {"klucz": f"s-{anna.pk}", "opis": "Po długiej chorobie."})
    response = editor.post(url, {"klucz": f"p-{pair.pk}", "opis": "Ślub w Łańcucie."})
    assert response.status_code == 302 and response.url.endswith(f"#k-p-{pair.pk}")
    anna.refresh_from_db()
    assert (anna.birth_note, anna.death_note, anna.birth_year) == (
        "W domu przy Kościuszki.",
        "Po długiej chorobie.",
        1921,
    )
    card = editor.get(reverse("family:person", args=[jan.pk])).content.decode()
    assert "Ślub w Łańcucie." in card and "W Kalendarium" in card
    card = editor.get(reverse("family:person", args=[anna.pk])).content.decode()
    assert "W domu przy Kościuszki." in card and "Po długiej chorobie." in card
    # zmiany są w historii drzewa i da się je cofnąć
    change = TreeChange.objects.filter(kind=TreeChange.COUPLE_EDITED).first()
    tree.undo(None, change)
    assert Partnership.objects.get().note == ""


def test_add_person_event_goes_to_card(editor, family):
    anna, _ = family
    data = {
        "title": "Matura",
        "date": "czerwiec 1939",
        "person": anna.pk,
        "kind": "nauka",
        "place": "Rzeszów",
        "note": "Z wyróżnieniem.",
    }
    response = editor.post(reverse("family:kalendarium_add"), data)
    event = LifeEvent.objects.get()
    assert response.url.endswith(f"#k-z-{event.pk}") and event.year == 1939 and event.person == anna
    assert "Matura" in editor.get(reverse("family:person", args=[anna.pk])).content.decode()
    editor.post(reverse("family:kalendarium_note"), {"klucz": f"z-{event.pk}", "opis": "Nowy opis"})
    event.refresh_from_db()
    assert event.note == "Nowy opis"


def test_family_event_add_and_remove_only_by_author(editor, family, make_user):
    response = editor.post(
        reverse("family:kalendarium_add"), {"title": "Zjazd rodzinny", "date": "15.08.1995", "kind": "inne"}
    )
    event = FamilyEvent.objects.get()
    assert event.year == 1995 and event.created_by == editor.user and response.status_code == 302
    assert "Zjazd rodzinny" in editor.get(reverse("family:kalendarium")).content.decode()
    other = Client()
    other.force_login(make_user("Ola"))
    other.post(reverse("family:kalendarium_remove", args=[event.pk]))
    assert FamilyEvent.objects.exists()
    editor.post(reverse("family:kalendarium_remove", args=[event.pk]))
    assert not FamilyEvent.objects.exists()


def test_bad_date_shows_form_error(editor, family):
    response = editor.post(
        reverse("family:kalendarium_add"), {"title": "Coś", "date": "kiedyś", "kind": "inne"}
    )
    assert response.status_code == 400 and "Nie rozumiem tej daty" in response.content.decode()


def test_viewer_cannot_edit(client, make_user, family):
    viewer = make_user("Ola")
    viewer.tree_access = viewer.TREE_VIEW
    viewer.save()
    client.force_login(viewer)
    page = client.get(reverse("family:kalendarium")).content.decode()
    assert "Dodaj wydarzenie" not in page and "Opisz" not in page
    anna, _ = family
    assert (
        client.post(reverse("family:kalendarium_note"), {"klucz": f"u-{anna.pk}", "opis": "x"}).status_code
        == 404
    )
