"""ETAP 33: dodawanie rodzeństwa, także osobie bez rodziców w drzewie."""

import json

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from family import tree
from family.models import ParentChild, Sibling, TreeChange


@pytest.fixture
def editor(client, make_user):
    client.force_login(make_user("Karolina"))
    return client


def ids(qs):
    return {p.pk for p in qs}


def test_sibling_of_person_with_parents_gets_the_same_parents(db):
    jan = tree.add_person(None, "Jan Bereza")
    zofia = tree.add_person(None, "Zofia Bereza")
    anna = tree.add_person(None, "Anna Bereza")
    tree.add_relation(None, jan, anna, tree.CHILD, second_parent=zofia)
    piotr = tree.add_person(None, "Piotr Bereza")
    tree.add_relation(None, anna, piotr, tree.SIBLING)
    assert ids(tree.parents(piotr)) == {jan.pk, zofia.pk}
    assert not Sibling.objects.exists()
    assert [p.pk for p in tree.siblings(anna)] == [piotr.pk]
    assert tree.siblings(anna)[0].linked is False


def test_sibling_without_parents_is_linked_and_whole_group_joins(db):
    anna = tree.add_person(None, "Anna Bereza")
    piotr = tree.add_person(None, "Piotr Bereza")
    ewa = tree.add_person(None, "Ewa Bereza")
    tree.add_relation(None, anna, piotr, tree.SIBLING)
    tree.add_relation(None, piotr, ewa, tree.SIBLING)
    assert ids(tree.linked_siblings(anna)) == {piotr.pk, ewa.pk}
    assert ids(tree.linked_siblings(ewa)) == {anna.pk, piotr.pk}
    assert Sibling.objects.count() == 3
    with pytest.raises(ValidationError):
        tree.add_relation(None, ewa, anna, tree.SIBLING)


def test_parent_added_later_goes_to_all_siblings(db):
    anna = tree.add_person(None, "Anna Bereza")
    piotr = tree.add_person(None, "Piotr Bereza")
    tree.add_relation(None, anna, piotr, tree.SIBLING)
    jan = tree.add_person(None, "Jan Bereza")
    zofia = tree.add_person(None, "Zofia Bereza")
    tree.add_relation(None, jan, anna, tree.CHILD, second_parent=zofia)
    assert ids(tree.parents(piotr)) == {jan.pk, zofia.pk}
    # Rodzeństwo wynika teraz z rodziców; karta osoby nie pokazuje go podwójnie.
    assert [p.pk for p in tree.siblings(anna)] == [piotr.pk]
    assert tree.siblings(anna)[0].linked is False


def test_sibling_cannot_be_own_parent_or_partner(db):
    jan = tree.add_person(None, "Jan Bereza")
    anna = tree.add_person(None, "Anna Bereza")
    tree.add_relation(None, jan, anna, tree.PARTNER)
    with pytest.raises(ValidationError):
        tree.add_relation(None, jan, anna, tree.SIBLING)
    with pytest.raises(ValidationError):
        tree.add_relation(None, jan, jan, tree.SIBLING)


def test_undo_and_remove_from_tree_restore_sibling(db, master):
    anna = tree.add_person(None, "Anna Bereza")
    piotr = tree.add_person(None, "Piotr Bereza")
    change = tree.add_relation(None, anna, piotr, tree.SIBLING)
    tree.undo(master, change)
    assert not Sibling.objects.exists()
    tree.undo(master, TreeChange.objects.get(reverts=change))
    assert Sibling.objects.count() == 1

    removed = tree.remove_from_tree(None, piotr)
    assert not Sibling.objects.exists()
    assert ("rodzeństwo", "Anna Bereza") in tree.link_rows(removed, {anna.pk: anna.name})
    tree.undo(master, removed)
    assert ids(tree.linked_siblings(anna)) == {piotr.pk}


def test_api_add_sibling_and_data(editor, db):
    anna = tree.add_person(None, "Anna Bereza")
    body = {"name": "Piotr Bereza", "relation": {"to": anna.pk, "kind": "rodzenstwo"}}
    data = editor.post(reverse("family:api_add"), json.dumps(body), content_type="application/json").json()
    piotr = next(p for p in data["people"] if p["name"] == "Piotr Bereza")
    assert sorted(data["siblings"][0]) == sorted([anna.pk, piotr["id"]])
    response = editor.post(
        reverse("family:api_relation"),
        json.dumps({"person": anna.pk, "other": piotr["id"], "kind": "rodzenstwo", "remove": True}),
        content_type="application/json",
    )
    assert response.json()["siblings"] == []


def test_person_page_lists_and_adds_siblings(editor, db):
    anna = tree.add_person(None, "Anna Bereza")
    response = editor.post(
        reverse("family:relation_add", args=[anna.pk]), {"kind": "rodzenstwo", "name": "Piotr Bereza"}
    )
    assert response.status_code == 302
    html = editor.get(reverse("family:person", args=[anna.pk])).content.decode()
    assert "Rodzeństwo" in html and "Piotr Bereza" in html
    assert "brat / siostra" in html
    assert not ParentChild.objects.exists()
