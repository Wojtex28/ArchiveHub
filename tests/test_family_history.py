"""ETAP 23: Panel → Drzewo → historia zmian i cofanie („Przywróć”)."""

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from albums.models import Person
from family import tree
from family.models import ParentChild, Partnership, TreeChange


@pytest.fixture
def family(db):
    names = ["Anna Bereza", "Jan Bereza", "Ewa Bereza", "Piotr Bereza"]
    return {name.split()[0].lower(): tree.add_person(None, name) for name in names}


def last():
    return TreeChange.objects.order_by("-pk").first()


def test_undo_added_relation_and_undo_the_undo(family, master):
    anna, ewa = family["anna"], family["ewa"]
    added = tree.add_relation(None, ewa, anna, tree.PARENT)
    undo = tree.undo(master, added)
    assert not ParentChild.objects.exists()
    assert undo.kind == TreeChange.RELATION_REMOVED and undo.reverts == added and undo.user == master
    with pytest.raises(ValidationError, match="już cofnięta"):
        tree.undo(master, added)
    tree.undo(master, undo)  # cofnięcie cofnięcia wraca relację
    assert list(tree.parents(ewa)) == [anna]


def test_undo_removed_relation_respects_rules(family, master):
    anna, jan, ewa, piotr = family["anna"], family["jan"], family["ewa"], family["piotr"]
    tree.add_relation(None, anna, jan, tree.PARTNER)
    tree.remove_relation(None, anna, jan, tree.PARTNER)
    tree.undo(master, last())
    assert Partnership.objects.filter(person1=anna, person2=jan).exists()

    tree.add_relation(None, ewa, anna, tree.PARENT)
    tree.remove_relation(None, ewa, anna, tree.PARENT)
    removed = last()
    tree.add_relation(None, ewa, jan, tree.PARENT)
    tree.add_relation(None, ewa, piotr, tree.PARENT)
    with pytest.raises(ValidationError, match="dwoje rodziców"):
        tree.undo(master, removed)  # w międzyczasie Ewa dostała dwoje innych rodziców


def test_undo_edit_restores_fields_and_years(family, master):
    anna = family["anna"]
    before = tree.snapshot(anna)
    anna.name, anna.birth_date, anna.birth_year, anna.bio = "Anna Nowak", "lata 30.", 1934, "Opis"
    anna.save()
    edit = tree.edit_person(None, anna, before)
    undo = tree.undo(master, edit)
    anna.refresh_from_db()
    assert (anna.name, anna.birth_date, anna.birth_year, anna.bio) == ("Anna Bereza", "", None, "")
    assert undo.kind == TreeChange.PERSON_EDITED and undo.after["name"] == "Anna Bereza"
    with pytest.raises(ValidationError, match="już cofnięta"):
        tree.undo(master, edit)

    tree.undo(master, undo)  # i z powrotem
    anna.refresh_from_db()
    assert (anna.name, anna.birth_year) == ("Anna Nowak", 1934)


def test_undo_edit_restores_name_taken_meanwhile_as_namesake(family, master):
    anna = family["anna"]
    before = tree.snapshot(anna)
    anna.name = "Anna Nowak"
    anna.save()
    edit = tree.edit_person(None, anna, before)
    other = Person.objects.create(name="Anna Bereza")  # ktoś nowy dostał starą nazwę
    tree.undo(master, edit)
    anna.refresh_from_db()
    assert anna.name == "Anna Bereza" and anna.pk != other.pk  # dwie osoby, imienniczki


def test_undo_removed_person_brings_back_links(family, master):
    anna, jan, ewa, piotr = family["anna"], family["jan"], family["ewa"], family["piotr"]
    tree.add_relation(None, ewa, anna, tree.PARENT)
    tree.add_relation(None, ewa, jan, tree.PARENT)
    tree.add_relation(None, ewa, piotr, tree.PARTNER)
    removed = tree.remove_from_tree(None, ewa)
    tree.remove_from_tree(None, piotr)  # partner też zniknął z drzewa
    undo = tree.undo(master, removed)
    ewa.refresh_from_db()
    piotr.refresh_from_db()
    assert ewa.in_tree and piotr.in_tree
    assert set(tree.parents(ewa)) == {anna, jan} and list(tree.partners(ewa)) == [piotr]
    assert undo.kind == TreeChange.PERSON_ADDED and undo.summary == "Przywrócono do drzewa: Ewa Bereza"
    assert sorted(undo.after["links"]["parents"]) == sorted([anna.pk, jan.pk])

    tree.undo(master, undo)  # cofnięcie przywrócenia znów zdejmuje Ewę z drzewa
    ewa.refresh_from_db()
    assert not ewa.in_tree and not ParentChild.objects.exists()


def test_undo_removed_person_skips_links_that_no_longer_fit(family, master):
    anna, jan, ewa, piotr = family["anna"], family["jan"], family["ewa"], family["piotr"]
    tree.add_relation(None, ewa, anna, tree.PARENT)
    removed = tree.remove_from_tree(None, anna)
    tree.add_relation(None, ewa, jan, tree.PARENT)
    tree.add_relation(None, ewa, piotr, tree.PARENT)
    undo = tree.undo(master, removed)
    anna.refresh_from_db()
    assert anna.in_tree and not tree.children(anna).exists()
    assert "bez połączeń z: Ewa Bereza" in undo.summary


def test_undo_added_person_and_missing_person(family, master):
    piotr = family["piotr"]
    added = TreeChange.objects.get(person=piotr, kind=TreeChange.PERSON_ADDED)
    tree.undo(master, added)
    piotr.refresh_from_db()
    assert not piotr.in_tree

    anna = family["anna"]
    added = TreeChange.objects.get(person=anna, kind=TreeChange.PERSON_ADDED)
    tree.remove_from_tree(None, anna)
    with pytest.raises(ValidationError, match="już nie jest w drzewie"):
        tree.undo(master, added)
    anna.delete()  # np. usunięta w Panel → Opisy
    added.refresh_from_db()
    with pytest.raises(ValidationError, match="nie ma już w archiwum"):
        tree.undo(master, added)


def test_history_page_lists_filters_and_undoes(master_client, master, make_user, family):
    karolina = make_user("Karolina")
    anna, ewa = family["anna"], family["ewa"]
    tree.add_relation(karolina, ewa, anna, tree.PARENT)
    before = tree.snapshot(anna)
    anna.birth_place = "Kraków"
    anna.save()
    edit = tree.edit_person(karolina, anna, before)

    url = reverse("panel:tree_history")
    page = master_client.get(url).content.decode()
    assert "Anna Bereza jest rodzicem: Ewa Bereza" in page and "Kraków" in page
    assert "Dodano do drzewa: Piotr Bereza" in page

    # Filtr po osobie łapie też relacje zapisane przy drugiej osobie.
    page = master_client.get(url, {"osoba": anna.pk}).content.decode()
    assert "Anna Bereza jest rodzicem: Ewa Bereza" in page and "Dodano do drzewa: Piotr" not in page
    page = master_client.get(url, {"konto": karolina.pk, "osoba": "x"}).content.decode()
    assert "miejsce urodzenia" in page and "Dodano do drzewa" not in page

    response = master_client.post(reverse("panel:tree_undo", args=[edit.pk]), {"osoba": anna.pk})
    assert response["Location"] == f"{url}?osoba={anna.pk}"
    anna.refresh_from_db()
    assert anna.birth_place == ""
    page = master_client.get(url).content.decode()
    assert "Cofnięte" in page and "cofnięcie" in page

    response = master_client.post(reverse("panel:tree_undo", args=[edit.pk]), follow=True)
    assert "Ta zmiana jest już cofnięta." in response.content.decode()


def test_history_is_for_master_only(client, make_user, family):
    client.force_login(make_user("Karolina"))
    assert client.get(reverse("panel:tree_history")).status_code == 404
    change = TreeChange.objects.first()
    assert client.post(reverse("panel:tree_undo", args=[change.pk])).status_code == 404
    assert TreeChange.objects.filter(reverts__isnull=False).count() == 0


def test_tree_access_for_all_accounts(master_client, master, make_user):
    karolina, marek = make_user("Karolina"), make_user("Marek", tree_access="view")
    response = master_client.post(reverse("panel:tree_access_all"), {"tree_access": "none"}, follow=True)
    assert "brak dostępu (zmienione konta: 2)" in response.content.decode()
    karolina.refresh_from_db()
    marek.refresh_from_db()
    master.refresh_from_db()
    assert karolina.tree_access == marek.tree_access == "none"
    assert master.can_edit_tree  # administrator zawsze
    master_client.post(reverse("panel:tree_access_all"), {"tree_access": "zle"})
    karolina.refresh_from_db()
    assert karolina.tree_access == "none"


def test_merge_keeps_history_on_target(family):
    anna = family["anna"]
    duplicate = Person.objects.create(name="Anna B.")
    tree.add_relation(None, duplicate, family["ewa"], tree.CHILD)
    tree.merge_into(duplicate, anna)
    duplicate.delete()
    assert TreeChange.objects.filter(person=anna, kind=TreeChange.RELATION_ADDED).exists()
