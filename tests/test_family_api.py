import json

import pytest
from django.urls import reverse

from albums.models import Person
from family import tree
from family.models import ParentChild, Partnership, TreeChange


@pytest.fixture
def editor(client, make_user):
    client.force_login(make_user("Karolina"))
    return client


def post(client, name, body):
    return client.post(reverse(name), json.dumps(body), content_type="application/json")


@pytest.fixture
def couple(db):
    anna = tree.add_person(None, "Anna Bereza")
    jan = tree.add_person(None, "Jan Bereza")
    tree.add_relation(None, anna, jan, tree.PARTNER)
    return anna, jan


def test_data(editor, couple):
    anna, jan = couple
    Person.objects.create(name="Ze zdjęcia")  # bez zdjęć: nie ma jej na liście spoza drzewa
    data = editor.get(reverse("family:data")).json()
    assert [p["name"] for p in data["people"]] == ["Anna Bereza", "Jan Bereza"]
    assert data["partners"] == [[anna.pk, jan.pk]]
    assert data["canEdit"] is True
    assert data["people"][0]["url"] == reverse("family:person", args=[anna.pk])
    assert data["outside"] == []
    assert "Ze zdjęcia" in data["names"]


def test_add_with_relation_and_position(editor, couple):
    anna, _ = couple
    data = post(
        editor,
        "family:api_add",
        {"name": "Ewa Bereza", "x": 10, "y": 200, "relation": {"to": anna.pk, "kind": "dziecko"}},
    ).json()
    ewa = Person.objects.get(name="Ewa Bereza")
    assert [anna.pk, ewa.pk] in data["parents"]
    assert (ewa.tree_x, ewa.tree_y) == (10, 200)


def test_add_error_rolls_back(editor, couple):
    anna, _ = couple
    response = post(
        editor, "family:api_add", {"id": anna.pk, "relation": {"to": anna.pk, "kind": "rodzic"}}
    )
    assert response.status_code == 400
    assert "sama ze sobą" in response.json()["error"]
    response = post(editor, "family:api_add", {"name": "", "x": 0, "y": 0})
    assert response.status_code == 400


def test_add_person_from_photos_by_id(editor, db):
    zofia = Person.objects.create(name="Zofia")
    data = post(editor, "family:api_add", {"id": zofia.pk, "x": 5, "y": 6}).json()
    assert [p["id"] for p in data["people"]] == [zofia.pk]
    assert TreeChange.objects.get().summary == "Dodano do drzewa: Zofia"


def test_relation_add_and_remove(editor, couple):
    anna, jan = couple
    ewa = tree.add_person(None, "Ewa")
    post(editor, "family:api_relation", {"person": ewa.pk, "other": anna.pk, "kind": "rodzic"})
    assert ParentChild.objects.filter(parent=anna, child=ewa).exists()
    response = post(editor, "family:api_relation", {"person": anna.pk, "other": ewa.pk, "kind": "rodzic"})
    assert response.status_code == 400 and "pętlę" in response.json()["error"]
    post(
        editor, "family:api_relation", {"person": anna.pk, "other": jan.pk, "kind": "partner", "remove": True}
    )
    assert not Partnership.objects.exists()
    assert (
        post(editor, "family:api_relation", {"person": anna.pk, "other": 999, "kind": "partner"}).status_code
        == 404
    )


def test_positions_are_validated(editor, couple):
    anna, jan = couple
    post(
        editor,
        "family:api_positions",
        {"positions": {str(anna.pk): [12.345, -40], str(jan.pk): ["x", 1], "zle": [1, 2]}},
    )
    anna.refresh_from_db()
    jan.refresh_from_db()
    assert (anna.tree_x, anna.tree_y) == (12.3, -40)
    assert jan.tree_x is None
    post(editor, "family:api_positions", {"positions": {str(anna.pk): [1e9, 0]}})
    anna.refresh_from_db()
    assert anna.tree_x == 12.3


def test_remove(editor, couple):
    anna, _ = couple
    post(editor, "family:api_remove", {"id": anna.pk})
    anna.refresh_from_db()
    assert not anna.in_tree


def test_viewer_cannot_change(client, make_user, couple):
    client.force_login(make_user("Ola", tree_access="view"))
    assert client.get(reverse("family:data")).json()["canEdit"] is False
    for name in ("family:api_add", "family:api_relation", "family:api_remove", "family:api_positions"):
        assert post(client, name, {}).status_code == 404


def test_csrf_required(make_user, couple):
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    client.force_login(make_user("Ola"))
    assert post(client, "family:api_remove", {"id": couple[0].pk}).status_code == 403


def test_tree_page_has_canvas(editor, couple):
    page = editor.get(reverse("family:tree")).content.decode()
    assert "data-family-tree" in page and "family-tree.js" in page


# --- ETAP 25: dziecko od pary --------------------------------------------------------


def test_child_of_person_with_one_partner_gets_both_parents(editor, couple):
    anna, jan = couple
    post(editor, "family:api_add", {"name": "Ewa Bereza", "relation": {"to": anna.pk, "kind": "dziecko"}})
    ewa = Person.objects.get(name="Ewa Bereza")
    assert set(tree.parents(ewa)) == {anna, jan}
    # Dwa wpisy w historii, każdy do cofnięcia osobno.
    assert TreeChange.objects.filter(kind="relation_added", after__child=ewa.pk).count() == 2


def test_second_parent_can_be_chosen_or_left_out(editor, couple):
    anna, jan = couple
    zofia = tree.add_person(None, "Zofia Nowak")
    tree.add_relation(None, anna, zofia, tree.PARTNER)  # Anna ma dwoje partnerów

    def child(name, **second):
        relation = {"to": anna.pk, "kind": "dziecko", **second}
        return post(editor, "family:api_add", {"name": name, "relation": relation})

    child("Ewa", second=zofia.pk)
    child("Piotr", second=None)
    child("Adam")
    assert set(tree.parents(Person.objects.get(name="Ewa"))) == {anna, zofia}
    assert list(tree.parents(Person.objects.get(name="Piotr"))) == [anna]
    assert list(tree.parents(Person.objects.get(name="Adam"))) == [anna]  # kilku partnerów: bez zgadywania
    response = child("X", second=999)
    assert response.status_code == 404 and not Person.objects.filter(name="X").exists()


def test_second_parent_becomes_partner(editor, db):
    ewa = tree.add_person(None, "Ewa Bereza")
    anna = tree.add_person(None, "Anna Bereza")
    tree.add_relation(None, ewa, anna, tree.PARENT)
    post(editor, "family:api_add", {"name": "Jan Bereza", "relation": {"to": ewa.pk, "kind": "rodzic"}})
    jan = Person.objects.get(name="Jan Bereza")
    assert set(tree.partners(anna)) == {jan}
    change = TreeChange.objects.filter(kind="relation_added").order_by("-pk").first()
    assert change.summary == "Para: Anna Bereza i Jan Bereza (rodzice: Ewa Bereza)"


def test_dragging_child_onto_person_links_the_couple(editor, couple):
    anna, jan = couple
    ewa = tree.add_person(None, "Ewa Bereza")
    post(editor, "family:api_relation", {"person": jan.pk, "other": ewa.pk, "kind": "dziecko"})
    assert set(tree.parents(ewa)) == {anna, jan}


def test_undo_does_not_add_second_parent(couple, master):
    anna, jan = couple
    ewa = tree.add_person(None, "Ewa Bereza")
    tree.add_relation(None, anna, ewa, tree.CHILD, second_parent=None)
    removed = tree.remove_relation(None, anna, ewa, tree.CHILD)
    tree.undo(master, removed)
    assert list(tree.parents(ewa)) == [anna]


def test_migration_pairs_existing_co_parents(db):
    from importlib import import_module

    from django.apps import apps

    anna, jan, ewa = (Person.objects.create(name=n, in_tree=True) for n in ("Anna", "Jan", "Ewa"))
    ParentChild.objects.create(parent=anna, child=ewa)
    ParentChild.objects.create(parent=jan, child=ewa)
    import_module("family.migrations.0003_pary_rodzicow").pair_parents(apps, None)
    assert Partnership.objects.filter(person1=anna, person2=jan).exists()


def test_tree_page_is_full_width_with_tools_in_ribbon(editor, couple):
    page = editor.get(reverse("family:tree")).content.decode()
    assert "app-main--full" in page
    ribbon = page.split('class="tree-ribbon"')[1].split('class="tree-stage"')[0]
    assert "Drzewo rodzinne" in ribbon
    for action in ("add", "layout", "zoom-out", "fit", "zoom-in"):
        assert f'data-tree-action="{action}"' in ribbon


def test_tree_ribbon_for_viewer_has_no_edit_tools(client, make_user, couple):
    client.force_login(make_user("Ola", tree_access="view"))
    page = client.get(reverse("family:tree")).content.decode()
    assert 'class="tree-ribbon"' in page and 'data-tree-action="fit"' in page
    assert 'data-tree-action="add"' not in page
