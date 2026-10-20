"""ETAP 6: kto widzi który album. Każda próba dostępu do pliku zdjęcia jest sprawdzana."""

import pytest
from django.urls import reverse
from PIL import Image

from accounts.models import FamilyGroup
from albums.models import Album, Photo


@pytest.fixture
def library(db, tmp_path, settings):
    settings.ARCHIVEHUB_ALBUMS_DIR = tmp_path / "albumy"
    return settings.ARCHIVEHUB_ALBUMS_DIR


def make_album(folder, *groups, reverse=False, **extra):
    album = Album.objects.create(folder=folder, title=folder, **extra)
    album.groups.add(*groups)
    photo = Photo.objects.create(
        album=album,
        name="001",
        source_name="001.png",
        position=1,
        width=10,
        height=10,
        checksum=folder,
        has_reverse=reverse,
    )
    for side in [False, True] if reverse else [False]:
        path = photo.thumb_path(reverse=side)
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (10, 10)).save(path, "WEBP")
    return album


@pytest.fixture
def family(library, make_user, group):
    """Bereza widzi swój album; Włodyka ma osobny; „Wszyscy” widzi każdy nieukryty."""
    wlodyka = FamilyGroup.objects.create(name="Włodyka")
    everyone = FamilyGroup.objects.create(name="Wszyscy", sees_all_albums=True)
    karolina = make_user("Karolina")
    karolina.family_groups.add(group)
    adam = make_user("Adam")
    adam.family_groups.add(wlodyka)
    babcia = make_user("Babcia")
    babcia.family_groups.add(everyone)
    return {
        "groups": {"bereza": group, "wlodyka": wlodyka, "wszyscy": everyone},
        "users": {"karolina": karolina, "adam": adam, "babcia": babcia},
        "albums": {
            "bereza": make_album("01_Bereza", group, reverse=True),
            "wlodyka": make_album("02_Wlodyka", wlodyka),
            "ukryty": make_album("03_Ukryty", group, is_hidden=True),
            "brak": make_album("04_Brak", group, folder_missing=True),
        },
    }


def thumb(album, reverse=False):
    name = "albums:thumb_reverse" if reverse else "albums:thumb"
    return reverse_url(name, album.photos.get().pk)


def reverse_url(name, pk):
    return reverse(name, args=[pk])


# --- Macierz prób dostępu ---------------------------------------------------


@pytest.mark.parametrize(
    ("person", "album", "allowed"),
    [
        ("karolina", "bereza", True),
        ("karolina", "wlodyka", False),
        ("karolina", "ukryty", False),
        ("karolina", "brak", False),
        ("adam", "bereza", False),
        ("adam", "wlodyka", True),
        ("babcia", "bereza", True),
        ("babcia", "wlodyka", True),
        ("babcia", "ukryty", False),
        ("babcia", "brak", False),
    ],
)
def test_thumbnail_access_matrix(client, family, person, album, allowed):
    client.force_login(family["users"][person])
    assert client.get(thumb(family["albums"][album])).status_code == (200 if allowed else 404)


def test_reverse_side_follows_the_same_rules(client, family):
    album = family["albums"]["bereza"]
    client.force_login(family["users"]["karolina"])
    assert client.get(thumb(album, reverse=True)).status_code == 200
    client.force_login(family["users"]["adam"])
    assert client.get(thumb(album, reverse=True)).status_code == 404


def test_logged_out_visitor_is_sent_to_login(client, family):
    response = client.get(thumb(family["albums"]["bereza"]))
    assert response.status_code == 302
    assert reverse("login") in response.url


def test_blocked_account_loses_access_immediately(client, family):
    karolina = family["users"]["karolina"]
    client.force_login(karolina)
    karolina.is_active = False
    karolina.save()
    assert client.get(thumb(family["albums"]["bereza"])).status_code != 200


def test_guessing_photo_numbers_reveals_nothing(client, family):
    client.force_login(family["users"]["adam"])
    codes = {client.get(reverse_url("albums:thumb", pk)).status_code for pk in range(1, 50)}
    # Adam widzi tylko zdjęcie z albumu Włodyka; reszta (też nieistniejące numery) to ten sam 404.
    assert codes == {200, 404}
    seen = [pk for pk in range(1, 50) if client.get(reverse_url("albums:thumb", pk)).status_code == 200]
    assert seen == [family["albums"]["wlodyka"].photos.get().pk]


def test_master_sees_everything(master_client, family):
    for album in family["albums"].values():
        assert master_client.get(thumb(album)).status_code == 200


def test_removing_group_from_album_cuts_access(client, family):
    album = family["albums"]["bereza"]
    client.force_login(family["users"]["karolina"])
    assert client.get(thumb(album)).status_code == 200
    album.groups.clear()
    assert client.get(thumb(album)).status_code == 404


# --- Panel: „Kto widzi ten album” -------------------------------------------


def test_album_page_saves_groups(master_client, family):
    album = family["albums"]["wlodyka"]
    g = family["groups"]
    response = master_client.post(
        reverse("panel:album_detail", args=[album.pk]),
        {"action": "groups", "groups": [g["bereza"].pk, g["wszyscy"].pk, "999", "abc"]},
    )
    assert response.status_code == 302
    # Grupa „widzi wszystkie” i śmieci są pomijane; Włodyka odznaczona.
    assert list(album.groups.all()) == [g["bereza"]]


def test_album_page_lists_who_sees_it(master_client, family):
    url = reverse("panel:album_detail", args=[family["albums"]["bereza"].pk])
    page = master_client.get(url).content.decode()
    viewers = page.split("Teraz widzi")[1]
    assert "Karolina" in viewers and "Babcia" in viewers
    assert "Adam" not in viewers


def test_hidden_album_has_no_viewers(family):
    assert not family["albums"]["ukryty"].viewers().exists()
    assert not family["albums"]["brak"].viewers().exists()


def test_inactive_people_are_not_listed_as_viewers(family):
    babcia = family["users"]["babcia"]
    babcia.is_active = False
    babcia.save()
    assert list(family["albums"]["bereza"].viewers()) == [family["users"]["karolina"]]


def test_person_page_lists_visible_albums(master_client, family):
    url = reverse("panel:user_detail", args=[family["users"]["karolina"].pk])
    page = master_client.get(url).content.decode()
    card = page.split("Widzi albumy")[1]
    assert "01_Bereza" in card
    assert "02_Wlodyka" not in card and "03_Ukryty" not in card


def test_only_master_changes_album_groups(client, family):
    album = family["albums"]["wlodyka"]
    client.force_login(family["users"]["adam"])
    data = {"action": "groups", "groups": [family["groups"]["bereza"].pk]}
    response = client.post(reverse("panel:album_detail", args=[album.pk]), data)
    assert response.status_code == 404
    assert list(album.groups.all()) == [family["groups"]["wlodyka"]]
