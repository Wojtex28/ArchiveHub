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
    assert data["couples"] == [
        {
            "a": jan.pk,
            "b": maria.pk,
            "since": "1960",
            "year": 1960,
            "ended": True,
            "place": "",
            "widowed": False,
            "oa": None,
            "ob": None,
        }
    ]
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
    assert "Zmień ślub, koniec związku" in page

    editor.post(url, {"since": "kiedyś"})  # zła data: nic się nie zmienia
    assert Partnership.objects.get(person2=anna).since == "1950"


@pytest.fixture
def stefania(db):
    """Jak u Stefanii Berezy: dwóch mężów bez dat ślubu, pierwszy zmarł wcześniej."""
    stefania = tree.add_person(None, "Stefania Bereza")
    jozef = tree.add_person(None, "Józef Bereza")
    jan = tree.add_person(None, "Jan Szyndlar")
    for person, died in ((stefania, "1997"), (jozef, "1956"), (jan, "1925")):
        person.death_date, person.death_year = died, int(died)
        person.save()
    tree.add_relation(None, stefania, jozef, tree.PARTNER)  # dodany pierwszy, ale to drugi mąż
    tree.add_relation(None, stefania, jan, tree.PARTNER)
    return stefania, jozef, jan


def test_partners_without_wedding_year_ordered_by_partner_death(stefania):
    stefania, jozef, jan = stefania
    assert [p.name for p in tree.partners_in_order(stefania)] == ["Jan Szyndlar", "Józef Bereza"]


def test_widowed_text(stefania):
    stefania, jozef, jan = stefania
    tree.edit_couple(None, stefania, jan, "1920", False, widowed=True)
    tree.edit_couple(None, stefania, jozef, "", False, widowed=True)
    first, second = tree.partners_in_order(stefania)
    assert first.couple_text == "ślub 1920 · wdowa od 1925"
    assert second.couple_text == "wdowa od 1956"
    # z perspektywy męża, który zmarł pierwszy
    [wife] = tree.partners_in_order(jan)
    assert wife.couple_text == "ślub 1920 · do śmierci (1925)"
    # rozwód wyklucza owdowienie
    tree.edit_couple(None, stefania, jan, "1920", True)
    assert Partnership.objects.get(person2=jan).widowed is False


def test_manual_partner_order_and_undo(stefania, master):
    stefania, jozef, jan = stefania
    changes = tree.set_partner_order(None, stefania, [jozef.pk, jan.pk])
    assert [p.name for p in tree.partners_in_order(stefania)] == ["Józef Bereza", "Jan Szyndlar"]
    assert changes and all(c.kind == TreeChange.COUPLE_EDITED for c in changes)
    with pytest.raises(tree.ValidationError):
        tree.set_partner_order(None, stefania, [jozef.pk])
    for change in reversed(changes):
        tree.undo(master, change)
    assert [p.name for p in tree.partners_in_order(stefania)] == ["Jan Szyndlar", "Józef Bereza"]


def test_partner_order_view_and_end_radio(editor, stefania):
    stefania, jozef, jan = stefania
    url = reverse("family:partner_order", args=[stefania.pk, jozef.pk])
    assert editor.post(url, {"kierunek": "wczesniej"}).status_code == 302
    assert [p.name for p in tree.partners_in_order(stefania)] == ["Józef Bereza", "Jan Szyndlar"]
    editor.post(reverse("family:couple_edit", args=[stefania.pk, jan.pk]), {"since": "", "koniec": "smierc"})
    assert Partnership.objects.get(person2=jan).widowed is True
    page = editor.get(reverse("family:person", args=[stefania.pk])).content.decode()
    assert "wdowa od 1925" in page and "Śmierć męża lub żony" in page


def test_api_partner_order(editor, stefania):
    stefania, jozef, jan = stefania
    data = post(editor, "family:api_couple", {"person": stefania.pk, "order": [jozef.pk, jan.pk]}).json()
    orders = {(c["a"], c["b"]): (c["oa"], c["ob"]) for c in data["couples"]}
    assert orders[(stefania.pk, jozef.pk)] == (1, None)
    assert orders[(stefania.pk, jan.pk)] == (2, None)
    bad = post(editor, "family:api_couple", {"person": stefania.pk, "order": [jan.pk]})
    assert bad.status_code == 400
