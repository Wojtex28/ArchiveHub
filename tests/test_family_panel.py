"""ETAP 34: podgląd i edycja danych osoby w panelu bocznym drzewa, karta osoby w okienku."""

import json

import pytest
from django.urls import reverse

from albums.models import Person
from family import tree
from family.models import TreeChange


@pytest.fixture
def editor(client, make_user):
    client.force_login(make_user("Karolina"))
    return client


def save(client, person, **body):
    data = {"name": person.name, **body}
    return client.post(
        reverse("family:api_person", args=[person.pk]), json.dumps(data), content_type="application/json"
    )


def test_tree_data_has_facts_for_side_panel(editor, db):
    anna = tree.add_person(None, "Anna Bereza")
    anna.birth_date, anna.birth_place, anna.bio = "1921", "Kraków", "Nauczycielka."
    anna.save()
    person = editor.get(reverse("family:data")).json()["people"][0]
    assert person["birth"] == "1921" and person["birthPlace"] == "Kraków"
    assert person["bio"] == "Nauczycielka." and person["death"] == ""


def test_save_from_side_panel_updates_person_and_history(editor, db):
    anna = tree.add_person(None, "Anna Bereza")
    fields = {"maiden": "Nowak", "birth": "ok. 1920", "birthPlace": "Kraków", "death": "1990", "bio": "Opis"}
    response = save(editor, anna, **fields)
    assert response.status_code == 200
    anna.refresh_from_db()
    assert anna.maiden_name == "Nowak" and anna.birth_date == "ok. 1920" and anna.birth_year == 1920
    # Data śmierci zaznacza „Nie żyje” sama, jak na stronie „Edytuj dane”.
    assert anna.deceased and anna.death_year == 1990
    person = response.json()["people"][0]
    assert person["years"] == anna.life and person["birthPlace"] == "Kraków"
    change = TreeChange.objects.filter(kind=TreeChange.PERSON_EDITED).get()
    assert change.after["birth_date"] == "ok. 1920"


def test_side_panel_errors_are_per_field(editor, db):
    anna = tree.add_person(None, "Anna Bereza")
    response = save(editor, anna, name="  ", birth="trzydziesty luty")
    assert response.status_code == 400
    errors = response.json()["errors"]
    assert set(errors) == {"name", "birth"}
    anna.refresh_from_db()
    assert anna.name == "Anna Bereza"


def test_side_panel_rename_warns_about_namesake(editor, db):
    tree.add_person(None, "Jan Bereza")
    anna = tree.add_person(None, "Anna Bereza")
    data = save(editor, anna, name="Jan Bereza").json()
    assert "inna osoba" in data["notice"]


def test_portraits_listed_and_unknown_portrait_rejected(editor, db):
    anna = tree.add_person(None, "Anna Bereza")
    data = editor.get(reverse("family:api_person", args=[anna.pk])).json()
    assert data == {"portrait": None, "crop": {"x": 50, "y": 50, "zoom": 1}, "portraits": []}
    assert save(editor, anna, portrait=999).status_code == 400


def test_viewer_cannot_save(client, make_user, db):
    viewer = make_user("Ola")
    viewer.tree_access = viewer.TREE_VIEW
    viewer.save()
    client.force_login(viewer)
    anna = tree.add_person(None, "Anna Bereza")
    assert client.get(reverse("family:api_person", args=[anna.pk])).status_code == 200
    assert save(client, anna, name="Ktoś").status_code == 403


def test_card_in_window_can_be_framed_only_by_own_site(editor, db):
    anna = tree.add_person(None, "Anna Bereza")
    url = reverse("family:person", args=[anna.pk])
    page = editor.get(url)
    assert page["X-Frame-Options"] == "DENY"
    card = editor.get(url + "?okno=1")
    assert card["X-Frame-Options"] == "SAMEORIGIN"
    assert "frame-ancestors 'self'" in card["Content-Security-Policy"]
    html = card.content.decode()
    # Bez menu i edycji. Link do pełnej strony jest w pasku okienka na stronie drzewa (ETAP 42),
    # więc nic nie zasłania przewijanej karty.
    assert "app-header" not in html and "Edytuj dane" not in html
    assert f'href="{url}" target="_blank"' not in html
    tree_page = editor.get(reverse("family:tree")).content.decode()
    assert 'class="tree-card__bar"' in tree_page and 'class="tree-card__full"' in tree_page


def test_portrait_crop_is_saved_and_defaults_to_center(master_client, db):
    """ETAP 45: kadr portretu z okna wyboru; bez niego portret zostaje wyśrodkowany."""
    person = Person.objects.create(name="Jan Bereza", in_tree=True)
    url = reverse("family:api_person", args=[person.pk])
    assert master_client.get(url).json()["crop"] == {"x": 50, "y": 50, "zoom": 1}
    body = {"name": "Jan Bereza", "portraitX": 20, "portraitY": 80.5, "portraitZoom": 9}
    assert master_client.post(url, body, content_type="application/json").status_code == 200
    person.refresh_from_db()
    assert (person.portrait_x, person.portrait_y, person.portrait_zoom) == (20, 80.5, 4)
    # Zapis bez kadru (np. stara karta otwarta w przeglądarce) niczego nie przestawia.
    assert master_client.post(url, {"name": "Jan Bereza"}, content_type="application/json").status_code == 200
    person.refresh_from_db()
    assert (person.portrait_x, person.portrait_y, person.portrait_zoom) == (20, 80.5, 4)
