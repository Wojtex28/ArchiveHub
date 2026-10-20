"""ETAP 13: opis zdjęcia (data, miejsce, osoby, tagi) i panel „Opisy”."""

import pytest
from django.urls import reverse

from accounts.models import FamilyGroup
from albums.forms import split_names
from albums.models import Album, Person, Photo, PhotoChange, Tag

FETCH = {"HTTP_X_REQUESTED_WITH": "fetch"}


def make_photo(album, name, position):
    return Photo.objects.create(
        album=album,
        name=name,
        source_name=f"{name}.png",
        position=position,
        checksum=f"{album.folder}-{name}",
        width=40,
        height=30,
    )


@pytest.fixture
def family(db, tmp_path, settings, make_user, group):
    settings.ARCHIVEHUB_ALBUMS_DIR = tmp_path
    album = Album.objects.create(folder="01_Brazowy", title="Brązowy")
    album.groups.add(group)
    other = Album.objects.create(folder="02_Obcy", title="Obcy")
    other.groups.add(FamilyGroup.objects.create(name="Włodyka"))
    karolina = make_user("Karolina")
    karolina.family_groups.add(group)
    return {
        "album": album,
        "photo": make_photo(album, "img_1", 1),
        "second": make_photo(album, "img_2", 2),
        "stranger": make_photo(other, "obce", 1),
        "karolina": karolina,
    }


@pytest.fixture
def karolina(client, family):
    client.force_login(family["karolina"])
    return client


def describe(client, photo, fetch=True, **values):
    data = {"date": "", "place": "", "people": "", "tags": "", "description": ""}
    data.update(values)
    return client.post(reverse("albums:metadata", args=[photo.pk]), data, **(FETCH if fetch else {}))


def test_split_names_removes_duplicates_and_spaces():
    assert split_names(" Jan ,babcia  Helena; jan,,\nŁucja ") == ["Jan", "babcia Helena", "Łucja"]


def test_save_description(karolina, family):
    photo = family["photo"]
    response = describe(
        karolina,
        photo,
        date="ok. 1965",
        place="Berezów, ogród",
        people="babcia Helena, Jan Bereza",
        tags="wesele",
        description="Wesele wujka Stefana.",
    )
    assert response.status_code == 200
    photo.refresh_from_db()
    assert (photo.date_text, photo.year_from, photo.year_to) == ("ok. 1965", 1963, 1967)
    assert photo.place == "Berezów, ogród"
    assert [p.name for p in photo.people.all()] == ["babcia Helena", "Jan Bereza"]
    assert [t.name for t in photo.tags.all()] == ["wesele"]
    assert photo.described_by == family["karolina"]
    page = response.content.decode()
    assert 'data-caption="ok. 1965 · Berezów, ogród · babcia Helena, Jan Bereza"' in page
    assert "#wesele" in page
    assert "Ostatnia zmiana: Karolina" in page
    change = PhotoChange.objects.get()
    assert change.changes["date"] == ["", "ok. 1965"]
    assert change.changes["people"] == [[], ["babcia Helena", "Jan Bereza"]]


def test_same_person_is_reused_regardless_of_case(karolina, family):
    describe(karolina, family["photo"], people="Łucja Bereza")
    describe(karolina, family["second"], people="łucja bereza")
    assert Person.objects.count() == 1
    assert family["second"].people.get().name == "Łucja Bereza"


def test_unchanged_form_adds_no_history(karolina, family):
    describe(karolina, family["photo"], date="1965", people="Jan")
    describe(karolina, family["photo"], date="1965", people="jan")
    assert PhotoChange.objects.count() == 1


def test_removed_names_disappear_when_unused(karolina, family):
    describe(karolina, family["photo"], people="Jan, Ola", tags="wakacje")
    describe(karolina, family["second"], people="Ola")
    describe(karolina, family["photo"], people="", tags="")
    assert list(Person.objects.values_list("name", flat=True)) == ["Ola"]
    assert not Tag.objects.exists()


def test_bad_date_returns_form_with_error(karolina, family):
    response = describe(karolina, family["photo"], date="dawno temu", place="Kraków")
    assert response.status_code == 400
    page = response.content.decode()
    assert "Nie rozumiem tej daty" in page
    assert 'value="Kraków"' in page
    assert '<details class="metadata__edit" open>' in page
    family["photo"].refresh_from_db()
    assert family["photo"].place == ""


def test_without_javascript_returns_to_photo_page(karolina, family):
    photo = family["photo"]
    response = describe(karolina, photo, fetch=False, place="Kraków")
    assert response.status_code == 302
    assert response["Location"].endswith(f"/{photo.pk}/?komentarze=1#opis")
    page = karolina.get(response["Location"]).content.decode()
    assert '<p class="viewer__caption">Kraków</p>' in page
    error = describe(karolina, photo, fetch=False, date="31.02.1965")
    assert error.status_code == 400
    assert "nie istnieje" in error.content.decode()


def test_description_is_escaped(karolina, family):
    photo = family["photo"]
    response = describe(karolina, photo, description="<script>alert(1)</script>", people="<b>Jan</b>")
    page = response.content.decode()
    assert "<script>alert" not in page
    assert "&lt;b&gt;Jan&lt;/b&gt;" in page


def test_cannot_describe_photo_from_other_album(karolina, family):
    response = describe(karolina, family["stranger"], place="Tu")
    assert response.status_code == 404
    assert not PhotoChange.objects.exists()


def test_anonymous_cannot_describe(client, family):
    response = describe(client, family["photo"], place="Tu")
    assert response.status_code == 302
    assert "/logowanie/" in response["Location"]


def test_suggestions_only_from_visible_albums(karolina, family):
    family["stranger"].people.add(Person.objects.create(name="Tajny Wujek"))
    family["second"].people.add(Person.objects.create(name="Ciocia Ala"))
    page = karolina.get(reverse("albums:comments", args=[family["photo"].pk]), **FETCH).content.decode()
    assert '<option value="Ciocia Ala">' in page
    assert "Tajny Wujek" not in page


def test_gallery_tile_has_caption(karolina, family):
    describe(karolina, family["photo"], date="lata 60.", people="Jan")
    page = karolina.get(reverse("albums:gallery", args=[family["album"].pk])).content.decode()
    assert 'data-caption="lata 60. · Jan"' in page


def test_panel_lists_people_and_changes(client, master, karolina, family):
    describe(karolina, family["photo"], people="Babcia Hela", tags="wesele", place="Berezów")
    client.force_login(master)
    page = client.get(reverse("panel:descriptions")).content.decode()
    assert 'value="Babcia Hela"' in page
    assert "1 zdj." in page
    assert "Berezów" in page
    assert "Karolina" in page


def test_panel_rename_and_merge(client, master, karolina, family):
    describe(karolina, family["photo"], people="Babcia Hela")
    describe(karolina, family["second"], people="babcia Helena")
    client.force_login(master)
    hela = Person.objects.get(name="Babcia Hela")
    url = reverse("panel:named_edit", args=["osoby", hela.pk])
    client.post(url, {"action": "rename", "name": "Babcia Helena"})
    assert list(Person.objects.values_list("name", flat=True)) == ["babcia Helena"]
    helena = Person.objects.get()
    assert set(helena.photos.all()) == {family["photo"], family["second"]}
    client.post(
        reverse("panel:named_edit", args=["osoby", helena.pk]), {"action": "rename", "name": "Helena Bereza"}
    )
    assert Person.objects.get().name == "Helena Bereza"


def test_panel_delete_tag(client, master, karolina, family):
    describe(karolina, family["photo"], tags="wesele")
    tag = Tag.objects.get()
    client.force_login(master)
    client.post(reverse("panel:named_edit", args=["tagi", tag.pk]), {"action": "delete"})
    assert not Tag.objects.exists()
    assert family["photo"].tags.count() == 0


def test_panel_descriptions_only_for_master(karolina, family):
    assert karolina.get(reverse("panel:descriptions")).status_code == 404
