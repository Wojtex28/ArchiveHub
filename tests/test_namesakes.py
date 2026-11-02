"""ETAP 26: imiennicy, czyli dwie różne osoby o tym samym imieniu i nazwisku (np. dziadek i wnuk)."""

import json

import pytest
from django.test import Client
from django.urls import reverse

from albums.metadata import change_rows
from albums.models import Album, Person, Photo, PhotoChange
from family import tree
from family.models import ParentChild, Partnership

FETCH = {"HTTP_X_REQUESTED_WITH": "fetch"}


def post(client, name, body):
    return client.post(reverse(name), json.dumps(body), content_type="application/json")


@pytest.fixture
def editor(client, make_user):
    client.force_login(make_user("Karolina"))
    return client


@pytest.fixture
def branches(db):
    """Dwie gałęzie rodziny, a w jednej już jest Jan Bereza z ojcem Józefem."""
    jozef = tree.add_person(None, "Józef Bereza")
    jan = tree.add_person(None, "Jan Bereza")
    tree.add_relation(None, jozef, jan, tree.CHILD)
    tadeusz = tree.add_person(None, "Tadeusz Nowak")
    return {"jozef": jozef, "jan": jan, "tadeusz": tadeusz}


def test_taken_name_asks_instead_of_linking_the_other_person(editor, branches):
    """Błąd z 0.25.0: drugi „Jan Bereza” podpinał istniejącego Jana pod obcą gałąź i parował rodziców."""
    response = post(
        editor,
        "family:api_add",
        {"name": "jan  bereza", "relation": {"to": branches["tadeusz"].pk, "kind": "dziecko"}},
    )
    assert response.status_code == 409
    data = response.json()
    assert [m["id"] for m in data["matches"]] == [branches["jan"].pk]
    facts = data["matches"][0]["facts"]
    assert "w drzewie" in facts and "rodzice: Józef Bereza" in facts
    assert Person.objects.filter(name="Jan Bereza").count() == 1
    assert not ParentChild.objects.filter(parent=branches["tadeusz"]).exists()
    assert not Partnership.objects.exists()


def test_new_namesake_is_a_separate_person(editor, branches):
    body = {"name": "Jan Bereza", "new": True, "relation": {"to": branches["tadeusz"].pk, "kind": "dziecko"}}
    data = post(editor, "family:api_add", body).json()
    young = Person.objects.get(pk=data["added"])
    assert young.pk != branches["jan"].pk and young.name == "Jan Bereza" and young.in_tree
    assert list(tree.parents(young)) == [branches["tadeusz"]]
    assert list(tree.parents(branches["jan"])) == [branches["jozef"]]  # starszy Jan bez zmian
    assert not Partnership.objects.exists()
    assert sum(p["name"] == "Jan Bereza" for p in data["people"]) == 2


def test_choosing_the_existing_person_links_it(editor, branches):
    anna = tree.add_person(None, "Anna Bereza")
    data = post(
        editor, "family:api_add", {"id": branches["jan"].pk, "relation": {"to": anna.pk, "kind": "partner"}}
    ).json()
    assert data["added"] == branches["jan"].pk
    assert Partnership.objects.count() == 1


def test_person_from_photos_is_also_asked_about(editor, db):
    on_photos = Person.objects.create(name="Helena Bereza")
    response = post(editor, "family:api_add", {"name": "Helena Bereza", "x": 0, "y": 0})
    assert response.status_code == 409
    assert response.json()["matches"][0]["facts"] == "spoza drzewa"
    data = post(editor, "family:api_add", {"id": on_photos.pk, "x": 0, "y": 0}).json()
    assert data["added"] == on_photos.pk
    on_photos.refresh_from_db()
    assert on_photos.in_tree


def test_tree_page_form_asks_and_then_adds_namesake(editor, branches):
    url = reverse("family:person_add")
    page = editor.post(url, {"name": "Jan Bereza"}).content.decode()
    assert "Kogo dodajesz?" in page and f'value="{branches["jan"].pk}"' in page
    assert Person.objects.filter(name="Jan Bereza").count() == 1
    response = editor.post(url, {"name": "Jan Bereza", "kto": "nowa"})
    young = Person.objects.filter(name="Jan Bereza").exclude(pk=branches["jan"].pk).get()
    assert response.url == reverse("family:person", args=[young.pk]) and young.in_tree


def test_person_page_form_asks_and_links_chosen_person(editor, branches):
    url = reverse("family:relation_add", args=[branches["tadeusz"].pk])
    page = editor.post(url, {"name": "Jan Bereza", "kind": "partner"}).content.decode()
    assert "Kogo dodajesz?" in page
    assert not Partnership.objects.exists()
    editor.post(url, {"name": "Jan Bereza", "kind": "partner", "kto": "nowa"})
    young = Person.objects.filter(name="Jan Bereza").exclude(pk=branches["jan"].pk).get()
    assert list(tree.partners(branches["tadeusz"])) == [young]
    # Wybór kogoś spoza listy imienników to błąd, nie nowa osoba.
    editor.post(url, {"name": "Jan Bereza", "kind": "dziecko", "kto": str(branches["tadeusz"].pk)})
    assert Person.objects.filter(name="Jan Bereza").count() == 2


# --- Opis zdjęcia -------------------------------------------------------------------------


@pytest.fixture
def photo(db, tmp_path, settings, group):
    settings.ARCHIVEHUB_ALBUMS_DIR = tmp_path
    album = Album.objects.create(folder="01_Brazowy", title="Brązowy")
    album.groups.add(group)
    return Photo.objects.create(
        album=album, name="img_1", source_name="img_1.png", position=1, checksum="x", width=40, height=30
    )


@pytest.fixture
def karolina(make_user, group):
    client = Client()
    user = make_user("Karolina")
    user.family_groups.add(group)
    client.force_login(user)
    return client


def describe(client, photo, people):
    data = {"date": "", "place": "", "people": people, "tags": "", "description": ""}
    return client.post(reverse("albums:metadata", args=[photo.pk]), data, **FETCH)


def test_photo_tags_the_chosen_namesake(karolina, photo, branches):
    young = Person.objects.create(name="Jan Bereza", in_tree=True, birth_date="1950", birth_year=1950)
    describe(karolina, photo, f"Jan Bereza #{young.pk}, Józef Bereza")
    assert set(photo.people.all()) == {young, branches["jozef"]}
    # Panel pokazuje imienników z numerem (dla formularza) i latami, a historia bez numeru.
    page = karolina.get(reverse("albums:comments", args=[photo.pk]), **FETCH).content.decode()
    assert f"Jan Bereza #{young.pk}" in page and "ur. 1950" in page
    rows = change_rows(PhotoChange.objects.get())
    assert rows[0][2] == "Jan Bereza, Józef Bereza"


def test_photo_keeps_tagged_namesake_and_tags_both(karolina, photo, branches):
    young = Person.objects.create(name="Jan Bereza", in_tree=True)
    describe(karolina, photo, f"Jan Bereza #{young.pk}")
    # Bez numeru (np. bez JavaScriptu) zostaje ten imiennik, który już jest na zdjęciu.
    describe(karolina, photo, "Jan Bereza, Józef Bereza")
    assert set(photo.people.all()) == {young, branches["jozef"]}
    describe(karolina, photo, f"Jan Bereza #{young.pk}, Jan Bereza #{branches['jan'].pk}")
    assert set(photo.people.all()) == {young, branches["jan"]}


def test_picker_choices_mark_namesakes(karolina, photo, branches):
    young = Person.objects.create(name="Jan Bereza", in_tree=True)
    page = karolina.get(reverse("albums:comments", args=[photo.pk]), **FETCH).content.decode()
    data = json.loads(page.split('id="osoby-wybor" type="application/json">')[1].split("</script>")[0])
    jans = [c for c in data if c["name"] == "Jan Bereza"]
    assert [c["token"] for c in jans] == [f"Jan Bereza #{branches['jan'].pk}", f"Jan Bereza #{young.pk}"]
    assert all(c["same"] for c in jans)
    assert next(c for c in data if c["name"] == "Józef Bereza")["token"] == "Józef Bereza"


# --- Panel → Opisy ------------------------------------------------------------------------


def test_panel_rename_does_not_merge_namesakes_in_tree(master_client, branches):
    young = tree.add_person(None, "Jan Bereza (wnuk)")
    url = reverse("panel:named_edit", args=["osoby", young.pk])
    page = master_client.post(url, {"action": "rename", "name": "Jan Bereza"}, follow=True).content.decode()
    assert "imiennicy" in page
    assert Person.objects.filter(name="Jan Bereza").count() == 2
    assert "imiennik:" in master_client.get(reverse("panel:descriptions")).content.decode()


def test_panel_rename_still_merges_photo_only_duplicate(master_client, branches):
    typo = Person.objects.create(name="Jan Berezaa")
    url = reverse("panel:named_edit", args=["osoby", typo.pk])
    master_client.post(url, {"action": "rename", "name": "Jan Bereza"})
    assert list(Person.objects.filter(key="jan bereza")) == [branches["jan"]]
