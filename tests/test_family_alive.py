"""ETAP 30: przełącznik „Nie żyje” (†) w drzewie."""

import json

import pytest
from django.urls import reverse

from family import tree
from family.models import TreeChange


@pytest.fixture
def editor(client, make_user):
    client.force_login(make_user("Karolina"))
    return client


def post(client, name, body):
    return client.post(reverse(name), json.dumps(body), content_type="application/json")


def form_data(**extra):
    data = {
        "name": "Anna Bereza",
        "maiden_name": "",
        "birth_date": "1921",
        "birth_place": "",
        "death_date": "",
        "death_place": "",
        "bio": "",
        "portrait": "",
    }
    data.update(extra)
    return data


def test_toggle_on_canvas_records_history_and_undo(editor, db, master):
    anna = tree.add_person(None, "Anna Bereza")
    data = post(editor, "family:api_alive", {"id": anna.pk, "deceased": True}).json()
    assert data["people"][0]["deceased"] is True
    anna.refresh_from_db()
    assert anna.deceased
    change = TreeChange.objects.get(kind=TreeChange.PERSON_EDITED)
    assert change.before == {"deceased": False} and change.after == {"deceased": True}
    assert "czy żyje" in change.summary
    assert tree.edit_rows(change) == [("czy żyje", "żyje", "nie żyje")]

    tree.undo(master, change)
    anna.refresh_from_db()
    assert not anna.deceased


def test_toggle_validation(editor, db):
    anna = tree.add_person(None, "Anna Bereza")
    assert post(editor, "family:api_alive", {"id": anna.pk}).status_code == 400
    assert post(editor, "family:api_alive", {"id": 999999, "deceased": True}).status_code == 404
    anna.death_date, anna.deceased = "1998", True
    anna.save()
    response = post(editor, "family:api_alive", {"id": anna.pk, "deceased": False})
    assert response.status_code == 400 and "datę" in response.json()["error"]


def test_viewer_cannot_toggle(client, make_user, db):
    anna = tree.add_person(None, "Anna Bereza")
    client.force_login(make_user("Ola", tree_access="view"))
    assert post(client, "family:api_alive", {"id": anna.pk, "deceased": True}).status_code == 404


def test_form_checkbox_and_death_date_marks_deceased(editor, db):
    anna = tree.add_person(None, "Anna Bereza")
    url = reverse("family:person_edit", args=[anna.pk])
    page = editor.get(url).content.decode()
    assert 'name="deceased"' in page and "Nie żyje" in page

    editor.post(url, form_data(deceased="on"))
    anna.refresh_from_db()
    assert anna.deceased and not anna.death_date
    assert "† nie żyje" in editor.get(reverse("family:person", args=[anna.pk])).content.decode()

    editor.post(url, form_data())
    anna.refresh_from_db()
    assert not anna.deceased

    # Data śmierci zaznacza przełącznik sama.
    editor.post(url, form_data(death_date="1998"))
    anna.refresh_from_db()
    assert anna.deceased and anna.death_year == 1998


def test_life_text(db):
    from albums.models import Person

    def life(**fields):
        return Person(name="X", **fields).life

    assert life(birth_date="1921", birth_year=1921) == "ur. 1921"
    assert life(birth_date="1921", birth_year=1921, deceased=True) == "1921 – †"
    full = {"birth_date": "1921", "birth_year": 1921, "death_date": "1998", "death_year": 1998}
    assert life(deceased=True, **full) == "† 1921–1998"
    assert life(death_date="1998", death_year=1998, deceased=True) == "† 1998"
    assert life(deceased=True) == "† nie żyje"
    assert life() == ""


def test_death_fields_wait_for_the_switch(editor, db):
    """ETAP 42: data i miejsce śmierci są schowane, dopóki „Nie żyje” jest wyłączone."""
    anna = tree.add_person(None, "Anna Bereza")
    url = reverse("family:person_edit", args=[anna.pk])
    page = editor.get(url).content.decode()
    assert page.count("field--death") == 3
    assert "js/person-form.js" in page

    editor.post(url, form_data(deceased="on", death_date="1998", death_place="Kraków"))
    anna.refresh_from_db()
    assert anna.deceased and anna.death_place == "Kraków"

    # Wyłączony przełącznik wyłącza pola, więc przeglądarka ich nie wysyła: dane śmierci znikają.
    data = form_data()
    del data["death_date"], data["death_place"]
    editor.post(url, data)
    anna.refresh_from_db()
    assert not anna.deceased and anna.death_date == "" and anna.death_place == ""
