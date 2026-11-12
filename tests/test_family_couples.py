"""ETAP 31: kilku partnerów jednej osoby, rok ślubu i rozwód."""

import json

import pytest
from django.urls import reverse

from family import tree
from family.models import Partnership, TreeChange


@pytest.fixture
def editor(client, make_user):
    client.force_login(make_user("Karolina"))
    return client


def post(client, name, body):
    return client.post(reverse(name), json.dumps(body), content_type="application/json")


@pytest.fixture
def jan(db):
    jan = tree.add_person(None, "Jan Bereza")
    maria = tree.add_person(None, "Maria Nowak")
    anna = tree.add_person(None, "Anna Kowalska")
    tree.add_relation(None, jan, maria, tree.PARTNER)  # dodana pierwsza, ale to drugi związek
    tree.add_relation(None, jan, anna, tree.PARTNER)
    return jan, anna, maria


def test_edit_couple_orders_partners_and_records_history(jan, master):
    jan, anna, maria = jan
    assert [p.name for p in tree.partners_in_order(jan)] == ["Maria Nowak", "Anna Kowalska"]
    tree.edit_couple(None, jan, anna, "1950", False)
    change = tree.edit_couple(None, jan, maria, "ok. 1960", True)
    ordered = tree.partners_in_order(jan)
    assert [p.name for p in ordered] == ["Anna Kowalska", "Maria Nowak"]
    assert ordered[1].couple_text == "ślub ok. 1960 · rozwód"
    assert Partnership.objects.get(person2=maria).since_year == 1960
    assert change.kind == TreeChange.COUPLE_EDITED
    assert tree.edit_rows(change) == [("rok ślubu", "", "ok. 1960"), ("rozwód", "nie", "tak")]
    assert tree.edit_couple(None, jan, maria, "ok. 1960", True) is None

    tree.undo(master, change)
    pair = Partnership.objects.get(person2=maria)
    assert (pair.since, pair.since_year, pair.ended) == ("", None, False)


def test_edit_couple_errors(jan):
    jan, anna, maria = jan
    with pytest.raises(tree.ValidationError):
        tree.edit_couple(None, anna, maria, "1950", False)
    with pytest.raises(tree.ValidationError):
        tree.edit_couple(None, jan, anna, "kiedyś", False)


def test_remove_and_undo_keeps_couple_details(jan, master):
    jan, anna, maria = jan
    tree.edit_couple(None, jan, maria, "1960", True)
    change = tree.remove_relation(None, jan, maria, tree.PARTNER)
    assert change.before["since"] == "1960" and change.before["ended"] is True
    tree.undo(master, change)
    pair = Partnership.objects.get(person2=maria)
    assert (pair.since, pair.since_year, pair.ended) == ("1960", 1960, True)


def test_api_couple(editor, jan):
    jan, anna, maria = jan
    data = post(
        editor, "family:api_couple", {"person": jan.pk, "other": maria.pk, "since": "1960", "ended": True}
    ).json()
    assert data["couples"] == [{"a": jan.pk, "b": maria.pk, "since": "1960", "year": 1960, "ended": True}]
    response = post(editor, "family:api_couple", {"person": anna.pk, "other": maria.pk, "since": ""})
    assert response.status_code == 400
    assert post(editor, "family:api_couple", {"person": 999999, "other": maria.pk}).status_code == 404


def test_viewer_cannot_edit_couple(client, make_user, jan):
    jan, anna, maria = jan
    client.force_login(make_user("Ola", tree_access="view"))
    assert post(client, "family:api_couple", {"person": jan.pk, "other": anna.pk}).status_code == 404
    url = reverse("family:couple_edit", args=[jan.pk, anna.pk])
    assert client.post(url, {"since": "1950"}).status_code == 404


def test_person_page_shows_and_edits_couples(editor, jan):
    jan, anna, maria = jan
    url = reverse("family:couple_edit", args=[jan.pk, anna.pk])
    assert editor.post(url, {"since": "1950"}).status_code == 302
    editor.post(reverse("family:couple_edit", args=[jan.pk, maria.pk]), {"since": "1960", "ended": "on"})
    page = editor.get(reverse("family:person", args=[jan.pk])).content.decode()
    assert page.index("Anna Kowalska") < page.index("Maria Nowak")
    assert "1. ślub 1950" in page and "2. ślub 1960 · rozwód" in page
    assert "Zmień datę ślubu, rozwód" in page

    editor.post(url, {"since": "kiedyś"})  # zła data: nic się nie zmienia
    assert Partnership.objects.get(person2=anna).since == "1950"
