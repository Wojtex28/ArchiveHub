"""ETAP 29: ulubione zdjęcia konta i osobna sekcja „Kto jest na zdjęciu”."""

import pytest
from django.urls import reverse

from accounts.models import FamilyGroup
from albums.models import Album, Favorite, Person
from tests.test_downloads import make_photo, zip_of

FETCH = {"HTTP_X_REQUESTED_WITH": "fetch"}


@pytest.fixture
def family(db, tmp_path, settings, make_user, group):
    settings.ARCHIVEHUB_ALBUMS_DIR = tmp_path / "albumy"
    settings.DATA_DIR = tmp_path
    album = Album.objects.create(folder="01_Brazowy", title="Brązowy album: 1997/2004")
    album.groups.add(group)
    other = Album.objects.create(folder="02_Obcy", title="Obcy")
    other.groups.add(FamilyGroup.objects.create(name="Włodyka"))
    karolina = make_user("Karolina")
    karolina.family_groups.add(group)
    return {
        "user": karolina,
        "album": album,
        "first": make_photo(album, "img20250216_14475559_1", reverse=True),
        "second": make_photo(album, "img20250216_14475559_2"),
        "stranger": make_photo(other, "obce"),
    }


@pytest.fixture
def karolina(client, family):
    client.force_login(family["user"])
    return client


def star(client, photo, on=True, fetch=True, **extra):
    data = {"ulubione": "1" if on else "0", **extra}
    return client.post(reverse("albums:favorite", args=[photo.pk]), data, **(FETCH if fetch else {}))


def test_add_and_remove_favorite(karolina, family):
    photo = family["first"]
    response = star(karolina, photo)
    assert response.json() == {"favorite": True, "count": 1}
    star(karolina, photo)  # drugi raz nic nie psuje
    assert Favorite.objects.filter(user=family["user"]).count() == 1
    assert star(karolina, photo, on=False).json() == {"favorite": False, "count": 0}
    assert not Favorite.objects.exists()


def test_favorite_without_js_returns_to_page(karolina, family):
    photo = family["second"]
    page = reverse("albums:photo", args=[photo.album_id, photo.pk])
    response = star(karolina, photo, fetch=False, next=page)
    assert response.status_code == 302 and response.url == page
    response = star(karolina, photo, fetch=False, next="https://zly.example/")
    assert response.url == page


def test_cannot_favorite_photo_from_hidden_album(karolina, family):
    assert star(karolina, family["stranger"]).status_code == 404
    assert not Favorite.objects.exists()


def test_favorite_needs_post_and_login(client, family):
    url = reverse("albums:favorite", args=[family["first"].pk])
    assert client.post(url, {"ulubione": "1"}).status_code == 302
    client.force_login(family["user"])
    assert client.get(url).status_code == 405


def test_favorites_page_is_private_and_shows_stars(karolina, family, make_user):
    star(karolina, family["second"])
    page = karolina.get(reverse("albums:favorites")).content.decode()
    assert f'data-favorite-url="/zdjecia/{family["second"].pk}/ulubione/"' in page
    assert 'data-favorite="1"' in page
    assert "Pobierz wszystkie ulubione" in page
    karolina.force_login(make_user("Ola"))
    other = karolina.get(reverse("albums:favorites")).content.decode()
    assert "Nie masz jeszcze ulubionych" in other


def test_gallery_marks_favorites(karolina, family):
    star(karolina, family["first"])
    page = karolina.get(reverse("albums:gallery", args=[family["album"].pk])).content.decode()
    assert page.count('data-favorite="1"') == 1
    assert page.count('data-favorite="0"') == 1


def test_favorites_hide_photos_from_albums_no_longer_visible(karolina, family, group):
    star(karolina, family["first"])
    family["album"].groups.remove(group)
    assert "Nie masz jeszcze ulubionych" in karolina.get(reverse("albums:favorites")).content.decode()
    assert karolina.get(reverse("albums:favorites_download")).status_code == 404


def test_favorites_download_zip_in_album_folders(karolina, family, group):
    second_album = Album.objects.create(folder="03_Zielony", title="Zielony")
    second_album.groups.add(group)
    green = make_photo(second_album, "zielone")
    star(karolina, family["first"])
    star(karolina, green)
    response = karolina.get(reverse("albums:favorites_download"))
    assert response.status_code == 200
    assert "Ulubione%20%282%20zdj.%29.zip" in response["Content-Disposition"]
    archive = zip_of(response)
    response.close()
    assert sorted(archive.namelist()) == [
        "Ulubione/Brązowy album 1997 2004/img20250216_14475559_1.jpg",
        "Ulubione/Brązowy album 1997 2004/img20250216_14475559_1_r.jpg",
        "Ulubione/Zielony/zielone.jpg",
    ]


def test_archive_home_has_favorites_card(karolina, family):
    star(karolina, family["first"])
    page = karolina.get(reverse("archive")).content.decode()
    assert "★ Ulubione" in page and "1 zdj. · widzisz tylko Ty" in page


def test_photo_page_star_button(karolina, family):
    photo = family["first"]
    url = reverse("albums:photo", args=[photo.album_id, photo.pk])
    assert 'name="ulubione" value="1"' in karolina.get(url).content.decode()
    star(karolina, photo)
    assert 'name="ulubione" value="0"' in karolina.get(url).content.decode()


def test_deleting_account_removes_its_favorites(karolina, family):
    star(karolina, family["first"])
    family["user"].delete()
    assert not Favorite.objects.exists()


# Osoby na zdjęciu: osobna sekcja panelu z własnym formularzem.


def test_people_have_own_section_and_form(karolina, family):
    photo = family["first"]
    response = karolina.post(
        reverse("albums:metadata", args=[photo.pk]), {"czesc": "osoby", "people": "Jan Bereza"}, **FETCH
    )
    html = response.content.decode()
    assert response.status_code == 200
    assert 'id="osoby"' in html and "Kto jest na zdjęciu" in html
    assert html.index('id="osoby"') < html.index('id="opis"') < html.index('id="komentarze-lista"')
    assert [p.name for p in photo.people.all()] == ["Jan Bereza"]
    assert 'name="czesc" value="osoby"' in html and 'name="czesc" value="opis"' in html


def test_saving_description_keeps_people_and_vice_versa(karolina, family):
    photo = family["first"]
    url = reverse("albums:metadata", args=[photo.pk])
    karolina.post(url, {"czesc": "osoby", "people": "Jan Bereza"}, **FETCH)
    karolina.post(
        url, {"czesc": "opis", "date": "1965", "place": "Berezów", "tags": "", "description": ""}, **FETCH
    )
    photo.refresh_from_db()
    assert photo.date_text == "1965" and photo.place == "Berezów"
    assert [p.name for p in photo.people.all()] == ["Jan Bereza"]
    karolina.post(url, {"czesc": "osoby", "people": ""}, **FETCH)
    photo.refresh_from_db()
    assert photo.date_text == "1965" and not photo.people.exists()
    assert not Person.objects.exists()


def test_people_form_without_js_returns_to_people_section(karolina, family):
    photo = family["first"]
    response = karolina.post(reverse("albums:metadata", args=[photo.pk]), {"czesc": "osoby", "people": "Ola"})
    assert response.status_code == 302 and response.url.endswith("#osoby")


@pytest.mark.parametrize("can_view", [True, False])
def test_tree_link_only_with_tree_access(karolina, family, can_view):
    photo = family["first"]
    person = Person.objects.create(name="Jan Bereza", in_tree=True)
    photo.people.add(person)
    user = family["user"]
    user.tree_access = user.TREE_EDIT if can_view else user.TREE_NONE
    user.save()
    html = karolina.get(reverse("albums:comments", args=[photo.pk]), **FETCH).content.decode()
    assert (reverse("family:person", args=[person.pk]) in html) is can_view
