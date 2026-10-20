import pytest
from django.urls import reverse

from albums.models import Album, Photo


def make_album(folder, photos=0, **extra):
    album = Album.objects.create(folder=folder, title=folder, **extra)
    for i in range(1, photos + 1):
        Photo.objects.create(
            album=album,
            name=f"{i:03}",
            source_name=f"{i:03}.png",
            position=i,
            width=10,
            height=10,
            checksum=f"{i}",
        )
    return album


def titles():
    return list(Album.objects.values_list("folder", flat=True))


# --- Kolejność ---------------------------------------------------------------


def test_new_albums_go_to_the_end(db):
    make_album("10_Wesele")
    make_album("02_Komunia")
    assert titles() == ["10_Wesele", "02_Komunia"]
    assert list(Album.objects.values_list("position", flat=True)) == [1, 2]


def test_move_up_and_down(master_client):
    a, b, c = make_album("01_A"), make_album("02_B"), make_album("03_C")

    response = master_client.post(reverse("panel:album_move_up", args=[c.pk]))
    assert response.status_code == 302
    assert response.url.endswith(f"#album-{c.pk}")
    assert titles() == ["01_A", "03_C", "02_B"]

    master_client.post(reverse("panel:album_move_down", args=[a.pk]))
    assert titles() == ["03_C", "01_A", "02_B"]

    # Pierwszy w górę i ostatni w dół: bez zmian.
    master_client.post(reverse("panel:album_move_up", args=[c.pk]))
    master_client.post(reverse("panel:album_move_down", args=[b.pk]))
    assert titles() == ["03_C", "01_A", "02_B"]
    assert list(Album.objects.values_list("position", flat=True)) == [1, 2, 3]


def test_sort_by_folder_uses_natural_order(master_client):
    for folder in ["10_Wesele", "2_Komunia", "01_Chrzest"]:
        make_album(folder)
    master_client.post(reverse("panel:album_sort_by_folder"))
    assert titles() == ["01_Chrzest", "2_Komunia", "10_Wesele"]


def test_archive_shows_albums_in_panel_order(client, make_user, group):
    first, second = make_album("01_A"), make_album("02_B")
    first.title, second.title = "Album pierwszy", "Album drugi"
    first.position, second.position = 2, 1
    first.save()
    second.save()
    group.sees_all_albums = True
    group.save()
    user = make_user("Karolina")
    user.family_groups.add(group)
    client.force_login(user)

    page = client.get(reverse("archive")).content.decode()

    assert page.index("Album drugi") < page.index("Album pierwszy")


# --- Opis, ukrywanie, okładka -----------------------------------------------


def test_edit_title_description_and_hidden(master_client):
    album = make_album("01_BrazowyZeZlotaObramowka_1997-2004")

    response = master_client.post(
        reverse("panel:album_detail", args=[album.pk]),
        {"title": "Brązowy album ze złotą obwódką", "description": "Lata 1997–2004.", "is_hidden": "on"},
    )

    assert response.status_code == 302
    album.refresh_from_db()
    assert album.title == "Brązowy album ze złotą obwódką"
    assert album.description == "Lata 1997–2004."
    assert album.is_hidden
    assert album.folder == "01_BrazowyZeZlotaObramowka_1997-2004"


def test_empty_title_is_rejected(master_client):
    album = make_album("Wesele")
    response = master_client.post(
        reverse("panel:album_detail", args=[album.pk]), {"title": "", "description": ""}
    )
    assert response.status_code == 200
    album.refresh_from_db()
    assert album.title == "Wesele"


def test_cover_defaults_to_first_photo_and_can_be_changed(master_client):
    album = make_album("Wesele", photos=3)
    first, _, third = album.photos.all()
    assert album.cover_photo == first

    response = master_client.post(reverse("panel:album_set_cover", args=[album.pk, third.pk]))

    assert response.status_code == 302
    album.refresh_from_db()
    assert album.cover_photo == third
    page = master_client.get(reverse("panel:album_detail", args=[album.pk])).content.decode()
    assert "Wybrana okładka: 003" in page


def test_cover_must_belong_to_album(master_client):
    album = make_album("Wesele", photos=1)
    other = make_album("Komunia", photos=1)
    photo = other.photos.get()
    response = master_client.post(reverse("panel:album_set_cover", args=[album.pk, photo.pk]))
    assert response.status_code == 404
    album.refresh_from_db()
    assert album.cover is None


def test_missing_cover_file_falls_back_to_first_photo(db):
    album = make_album("Wesele", photos=2)
    first, second = album.photos.all()
    album.cover = second
    album.save()
    second.file_missing = True
    second.save()
    assert album.cover_photo == first


def test_archive_card_shows_cover_and_description(client, make_user, group):
    album = make_album("Wesele", photos=2, description="Wesele dziadków w Ustce.")
    album.groups.add(group)
    user = make_user("Karolina")
    user.family_groups.add(group)
    client.force_login(user)

    page = client.get(reverse("archive")).content.decode()

    assert reverse("albums:thumb", args=[album.photos.first().pk]) in page
    assert "Wesele dziadków w Ustce." in page


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("panel:album_move_up", "album"),
        ("panel:album_move_down", "album"),
        ("panel:album_sort_by_folder", None),
        ("panel:album_set_cover", "cover"),
    ],
)
def test_only_master_can_manage_albums(client, make_user, name, args):
    album = make_album("Wesele", photos=1)
    kwargs = {"album": [album.pk], "cover": [album.pk, album.photos.get().pk], None: []}[args]
    client.force_login(make_user("Karolina"))
    assert client.post(reverse(name, args=kwargs)).status_code == 404
    assert client.post(reverse("panel:album_detail", args=[album.pk]), {"title": "X"}).status_code == 404
    album.refresh_from_db()
    assert album.title == "Wesele" and album.cover is None


def test_moving_requires_post(master_client):
    album = make_album("Wesele")
    assert master_client.get(reverse("panel:album_move_up", args=[album.pk])).status_code == 405
