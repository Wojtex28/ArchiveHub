# ruff: noqa: F811  (fikstury dirs i imported z test_import)
import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from albums.models import Person
from family import tree
from family.models import ParentChild, Partnership, TreeChange

from .test_import import dirs, imported  # noqa: F401


@pytest.fixture
def family(db):
    names = ["Anna Bereza", "Jan Bereza", "Ewa Bereza", "Piotr Bereza"]
    return {name.split()[0].lower(): tree.add_person(None, name) for name in names}


# --- Relacje ------------------------------------------------------------------


def test_add_relations_and_relatives(family):
    anna, jan, ewa = family["anna"], family["jan"], family["ewa"]
    tree.add_relation(None, ewa, anna, tree.PARENT)
    tree.add_relation(None, anna, jan, tree.PARTNER)
    tree.add_relation(None, jan, ewa, tree.CHILD)
    assert set(tree.parents(ewa)) == {anna, jan}
    assert list(tree.children(anna)) == [ewa]
    assert list(tree.partners(jan)) == [anna]
    assert Partnership.objects.get().person1 == anna  # mniejsze id pierwsze


def test_relation_errors(family):
    anna, jan, ewa, piotr = family["anna"], family["jan"], family["ewa"], family["piotr"]
    with pytest.raises(ValidationError, match="sama ze sobą"):
        tree.add_relation(None, anna, anna, tree.PARENT)
    tree.add_relation(None, ewa, anna, tree.PARENT)
    with pytest.raises(ValidationError, match="już jest rodzicem"):
        tree.add_relation(None, anna, ewa, tree.CHILD)
    tree.add_relation(None, ewa, jan, tree.PARENT)
    with pytest.raises(ValidationError, match="dwoje rodziców"):
        tree.add_relation(None, ewa, piotr, tree.PARENT)
    with pytest.raises(ValidationError, match="pętlę"):
        tree.add_relation(None, anna, ewa, tree.PARENT)  # dziecko nie może być rodzicem swojego rodzica
    tree.add_relation(None, piotr, ewa, tree.PARENT)
    with pytest.raises(ValidationError, match="pętlę"):
        tree.add_relation(None, anna, piotr, tree.PARENT)  # wnuk jako rodzic babci
    # Anna i Jan są parą od chwili, gdy oboje zostali rodzicami Ewy.
    with pytest.raises(ValidationError, match="już jest partnerem"):
        tree.add_relation(None, jan, anna, tree.PARTNER)


def test_relation_puts_photo_person_in_tree_and_records_history(db, master):
    tagged = Person.objects.create(name="Zofia Włodyka")
    anna = tree.add_person(master, "Anna Bereza")
    tree.add_relation(master, anna, tagged, tree.CHILD)
    tagged.refresh_from_db()
    assert tagged.in_tree
    summaries = list(TreeChange.objects.order_by("pk").values_list("kind", "summary"))
    assert summaries == [
        ("person_added", "Dodano do drzewa: Anna Bereza"),
        ("person_added", "Dodano do drzewa: Zofia Włodyka"),
        ("relation_added", "Anna Bereza jest rodzicem: Zofia Włodyka"),
    ]
    assert TreeChange.objects.first().user == master


def test_remove_from_tree_keeps_person_and_snapshots_links(family):
    anna, jan, ewa = family["anna"], family["jan"], family["ewa"]
    tree.add_relation(None, ewa, anna, tree.PARENT)
    tree.add_relation(None, anna, jan, tree.PARTNER)
    change = tree.remove_from_tree(None, anna)
    anna.refresh_from_db()
    assert not anna.in_tree
    assert not ParentChild.objects.exists() and not Partnership.objects.exists()
    assert change.before["links"] == {"parents": [], "children": [ewa.pk], "partners": [jan.pk]}


def test_merge_moves_tree_data(family):
    anna, ewa = family["anna"], family["ewa"]
    tree.add_relation(None, ewa, anna, tree.PARENT)
    duplicate = Person.objects.create(name="Anna B.", birth_date="1921", birth_year=1921, in_tree=True)
    tree.add_relation(None, duplicate, family["jan"], tree.PARTNER)
    tree.merge_into(duplicate, anna)
    anna.refresh_from_db()
    assert (anna.birth_date, anna.birth_year) == ("1921", 1921)
    assert list(tree.partners(anna)) == [family["jan"]]


def test_years():
    assert (
        Person(birth_date="12.06.1921", birth_year=1921, death_date="1998", death_year=1998).years
        == "1921–1998"
    )
    assert Person(birth_date="lata 20.", birth_year=1924).years == "ur. lata 20."
    assert Person(death_date="03.1998", death_year=1998).years == "zm. 1998"
    assert Person().years == ""


# --- Strony -------------------------------------------------------------------


def test_tree_access_levels(client, make_user, family):
    viewer = make_user("Karolina", tree_access="view")
    client.force_login(viewer)
    page = client.get(reverse("family:tree")).content.decode()
    assert "Anna Bereza" in page and "Dodaj osobę do drzewa" not in page
    person_page = client.get(reverse("family:person", args=[family["anna"].pk])).content.decode()
    assert "Edytuj dane" not in person_page
    assert client.post(reverse("family:person_add"), {"name": "Ktoś"}).status_code == 404
    assert client.get(reverse("family:person_edit", args=[family["anna"].pk])).status_code == 404

    viewer.tree_access = "none"
    viewer.save()
    assert client.get(reverse("family:tree")).status_code == 404
    assert "Drzewo" not in client.get(reverse("archive")).content.decode().split("</nav>")[0]


def test_tree_requires_login(client, family):
    response = client.get(reverse("family:tree"))
    assert response.status_code == 302 and "/logowanie/" in response["Location"]


def test_editor_adds_person_relation_and_edits(client, make_user, db):
    client.force_login(make_user("Karolina"))  # domyślnie edycja
    response = client.post(reverse("family:person_add"), {"name": " Anna   Bereza "})
    anna = Person.objects.get(name="Anna Bereza")
    assert response["Location"] == reverse("family:person", args=[anna.pk])

    url = reverse("family:relation_add", args=[anna.pk])
    client.post(url, {"kind": "dziecko", "name": "Ewa Bereza"})
    client.post(url, {"kind": "dziecko", "name": "anna bereza"})  # sama ze sobą: błąd
    assert [p.name for p in tree.children(anna)] == ["Ewa Bereza"]

    response = client.post(
        reverse("family:person_edit", args=[anna.pk]),
        {
            "name": "Anna Bereza",
            "maiden_name": "Nowak",
            "birth_date": "ok. 1921",
            "birth_place": "Kraków",
            "death_date": "03.1998",
            "death_place": "",
            "bio": "Nauczycielka.",
            "portrait": "",
        },
    )
    assert response.status_code == 302
    anna.refresh_from_db()
    assert (anna.birth_date, anna.birth_year, anna.death_year) == ("ok. 1921", 1921, 1998)
    assert anna.years == "ok. 1921 – 1998"
    edit = TreeChange.objects.filter(kind="person_edited").get()
    assert edit.before["maiden_name"] == "" and edit.after["maiden_name"] == "Nowak"
    assert "nazwisko rodowe" in edit.summary

    page = client.get(reverse("family:person", args=[anna.pk])).content.decode()
    assert "z domu Nowak" in page and "Ewa Bereza" in page and "Nauczycielka." in page


def test_edit_rejects_bad_date(client, make_user, family):
    client.force_login(make_user("Karolina"))
    url = reverse("family:person_edit", args=[family["anna"].pk])
    data = {"name": "Anna Bereza", "birth_date": "kiedyś", "death_date": "", "portrait": ""}
    page = client.post(url, data).content.decode()
    assert "Nie rozumiem tej daty" in page
    assert not TreeChange.objects.filter(kind="person_edited").exists()


def test_edit_allows_namesake_name_with_reminder(client, make_user, family):
    """ETAP 26: imiennicy są dozwoleni, zapis tylko o nich przypomina."""
    client.force_login(make_user("Karolina"))
    url = reverse("family:person_edit", args=[family["anna"].pk])
    data = {"name": "Jan Bereza", "birth_date": "", "death_date": "", "portrait": ""}
    page = client.post(url, data, follow=True).content.decode()
    assert "W archiwum jest też inna osoba „Jan Bereza”" in page
    assert Person.objects.filter(name="Jan Bereza").count() == 2


def test_person_page_shows_only_visible_photos(client, make_user, group, imported):
    bereza, inny = imported["Bereza"], imported["Inny"]
    zofia = tree.add_person(None, "Zofia")
    bereza.people.add(zofia)
    inny.people.add(zofia)
    zofia.portrait = inny
    zofia.save()
    user = make_user("Karolina")
    user.family_groups.add(group)
    client.force_login(user)
    page = client.get(reverse("family:person", args=[zofia.pk])).content.decode()
    assert reverse("albums:thumb", args=[bereza.pk]) in page
    assert reverse("albums:thumb", args=[inny.pk]) not in page  # ani zdjęcie, ani portret z cudzego albumu
    assert "Zdjęcia (1)" in page


def test_remove_relation_and_person_views(client, make_user, family):
    client.force_login(make_user("Karolina"))
    anna, ewa = family["anna"], family["ewa"]
    tree.add_relation(None, anna, ewa, tree.CHILD)
    client.post(reverse("family:relation_remove", args=[anna.pk, ewa.pk, "dziecko"]))
    assert not ParentChild.objects.exists()
    client.post(reverse("family:person_remove", args=[anna.pk]))
    anna.refresh_from_db()
    assert not anna.in_tree
    assert Person.objects.filter(pk=anna.pk).exists()


def test_panel_tree_access_field_and_delete_guard(master_client, make_user, family):
    user = make_user("Karolina")
    page = master_client.get(reverse("panel:user_detail", args=[user.pk])).content.decode()
    assert "Drzewo rodzinne" in page
    master_client.post(
        reverse("panel:user_detail", args=[user.pk]),
        {"action": "edit", "display_name": "", "tree_access": "view"},
    )
    user.refresh_from_db()
    assert user.tree_access == "view"

    master_client.post(reverse("panel:named_edit", args=["osoby", family["anna"].pk]), {"action": "delete"})
    assert Person.objects.filter(pk=family["anna"].pk).exists()
