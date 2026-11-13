"""ETAP 50–52: widok kafelki/lista, „Moje albumy” i edycja albumu."""

# ruff: noqa: F811
import pytest
from django.urls import reverse

from albums.models import Album, Favorite, UserAlbum, UserAlbumPhoto
from tests.test_favorites import FETCH, family, karolina  # noqa: F401


def test_view_switch_remembers_choice(karolina, family):
    page = karolina.get(reverse("archive"))
    assert "album-grid--kafelki" in page.content.decode()
    response = karolina.get(reverse("archive") + "?widok=lista")
    assert "album-grid--lista" in response.content.decode()
    assert response.cookies["albumy_widok"].value == "lista"
    assert "album-grid--lista" in karolina.get(reverse("archive")).content.decode()
    # Zła wartość nic nie psuje: zostaje zapamiętany widok.
    assert "album-grid--lista" in karolina.get(reverse("archive") + "?widok=zle").content.decode()


def test_sidebar_offers_creating_own_album(karolina, family):
    page = karolina.get(reverse("archive")).content.decode()
    assert "Utwórz swój album" in page and "own-item--favorites" in page
    response = karolina.post(reverse("albums:own_album_create"), {"name": "  Babcia   Zosia "})
    album = UserAlbum.objects.get()
    assert album.name == "Babcia Zosia" and album.user == family["user"]
    assert response.url == reverse("albums:own_album", args=[album.pk])
    page = karolina.get(reverse("archive")).content.decode()
    assert "Babcia Zosia" in page and "Nowy album" in page


def test_star_without_own_albums_stays_plain_favorite(karolina, family):
    page = karolina.get(reverse("albums:gallery", args=[family["album"].pk])).content.decode()
    assert "data-own-albums" not in page
    UserAlbum.objects.create(user=family["user"], name="Babcia")
    page = karolina.get(reverse("albums:gallery", args=[family["album"].pk])).content.decode()
    assert "data-own-albums" in page


def test_collections_menu_adds_and_removes(karolina, family):
    photo = family["first"]
    own = UserAlbum.objects.create(user=family["user"], name="Babcia")
    url = reverse("albums:photo_collections", args=[photo.pk])
    state = karolina.get(url, **FETCH).json()
    assert state == {
        "favorite": False,
        "albums": [{"id": own.pk, "name": "Babcia", "on": False}],
        "collected": False,
    }
    state = karolina.post(url, {"album": own.pk, "on": "1"}, **FETCH).json()
    assert state["albums"][0]["on"] and state["collected"]
    karolina.post(url, {"album": own.pk, "on": "1"}, **FETCH)  # drugi raz nic nie psuje
    assert UserAlbumPhoto.objects.count() == 1
    state = karolina.post(url, {"album": "ulubione", "on": "1"}, **FETCH).json()
    assert state["favorite"] and Favorite.objects.filter(photo=photo).exists()
    state = karolina.post(url, {"nowy": "Wesele"}, **FETCH).json()
    assert [a["name"] for a in state["albums"] if a["on"]] == ["Babcia", "Wesele"]
    state = karolina.post(url, {"album": own.pk, "on": "0"}, **FETCH).json()
    assert not state["albums"][0]["on"]
    # Gwiazdka w galerii jest pełna, gdy zdjęcie jest w Ulubionych albo w którymś albumie.
    page = karolina.get(reverse("albums:gallery", args=[family["album"].pk])).content.decode()
    assert 'data-favorite="1"' in page


def test_cannot_touch_someone_elses_album_or_hidden_photo(client, family, make_user):
    stranger = make_user("Obcy")
    theirs = UserAlbum.objects.create(user=stranger, name="Cudzy")
    client.force_login(family["user"])
    url = reverse("albums:photo_collections", args=[family["first"].pk])
    assert client.post(url, {"album": theirs.pk, "on": "1"}, **FETCH).status_code == 404
    assert client.get(reverse("albums:own_album", args=[theirs.pk])).status_code == 404
    hidden = reverse("albums:photo_collections", args=[family["stranger"].pk])
    assert client.get(hidden, **FETCH).status_code == 404


def test_own_album_page_rename_download_delete(karolina, family):
    own = UserAlbum.objects.create(user=family["user"], name="Babcia")
    UserAlbumPhoto.objects.create(album=own, photo=family["first"])
    UserAlbumPhoto.objects.create(album=own, photo=family["stranger"])  # już niewidoczne: pomijane
    page = karolina.get(reverse("albums:own_album", args=[own.pk]))
    assert page.context["photos"] == [family["first"]]
    response = karolina.get(reverse("albums:own_album_download", args=[own.pk]))
    assert response.status_code == 200 and response["Content-Type"] == "application/zip"
    karolina.post(reverse("albums:own_album", args=[own.pk]), {"name": "Babcia Zosia"})
    own.refresh_from_db()
    assert own.name == "Babcia Zosia"
    karolina.post(reverse("albums:own_album", args=[own.pk]), {"action": "delete"})
    assert not UserAlbum.objects.exists() and family["first"].pk


@pytest.fixture
def album(db):
    from tests.test_album_management import make_album

    return make_album("01_BrązowyZeZlotaObramowka97-04_Pocięte", photos=3)


def test_album_edit_prefills_readable_values(master_client, album):
    album.title = "01 BrązowyZeZlotaObramowka97-04 Pocięte"
    album.save()
    page = master_client.get(reverse("panel:album_edit", args=[album.pk]))
    form = page.context["form"]
    assert form.initial["title"] == "Brązowy ze Zlota Obramowka"
    assert (form.initial["year_from"], form.initial["year_to"]) == (1997, 2004)


def test_album_edit_saves_title_years_cover(master_client, album):
    third = album.photos.all()[2]
    url = reverse("panel:album_edit", args=[album.pk])
    data = {"title": "Brązowy album ze złotą obwódką", "description": "Od babci", "year_from": "1997"}
    response = master_client.post(url, {**data, "year_to": "2004", "cover": third.pk})
    assert response.url == reverse("albums:gallery", args=[album.pk])
    album.refresh_from_db()
    assert (album.title, album.year_from, album.year_to, album.cover) == (
        "Brązowy album ze złotą obwódką",
        1997,
        2004,
        third,
    )
    assert album.label.number == "01" and album.display_title == "Brązowy album ze złotą obwódką, 1997–2004"
    response = master_client.post(url, {**data, "year_to": "1990"})
    assert response.status_code == 200 and "Rok końcowy" in response.content.decode()


def test_album_edit_only_for_master(client, make_user, album):
    client.force_login(make_user("Karolina"))
    assert client.get(reverse("panel:album_edit", args=[album.pk])).status_code == 404


def test_edit_button_only_for_master(karolina, family):
    page = karolina.get(reverse("archive")).content.decode()
    assert "album-card__edit" not in page
    assert Album.objects.exists()
