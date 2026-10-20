import pytest
from django.urls import reverse

from accounts.models import FamilyGroup
from albums.models import Album, SyncReport
from albums.sync import sync_albums


@pytest.fixture
def library(tmp_path, settings):
    settings.ARCHIVEHUB_ALBUMS_DIR = tmp_path / "albumy"
    settings.ARCHIVEHUB_ALBUMS_DIR.mkdir()
    return settings.ARCHIVEHUB_ALBUMS_DIR


def make_album_folder(library, name, photos=2):
    folder = library / name
    folder.mkdir()
    for i in range(photos):
        (folder / f"{i:03}.jpg").write_bytes(b"x")
    (folder / "opis.txt").write_text("nie zdjęcie")
    return folder


# --- Synchronizacja ---------------------------------------------------------


def test_sync_creates_albums_from_folders(db, library):
    make_album_folder(library, "Album_01_lata_50", photos=3)
    make_album_folder(library, "_Prywatne", photos=1)
    (library / ".ukryty_system").mkdir()

    report = sync_albums()

    assert report.ok
    assert report.albums_total == 2
    # Zdjęcia liczą się dopiero po imporcie; luźne pliki w bibliotece nie są zdjęciami albumu.
    assert report.photos_total == 0
    assert sorted(report.new_albums) == ["Album_01_lata_50", "_Prywatne"]
    album = Album.objects.get(folder="Album_01_lata_50")
    assert album.title == "Album 01 lata 50"
    assert album.photo_count == 0
    assert not album.is_hidden
    assert Album.objects.get(folder="_Prywatne").is_hidden


def test_sync_twice_does_not_duplicate(db, library):
    make_album_folder(library, "Wesele", photos=2)
    sync_albums()

    report = sync_albums()

    assert Album.objects.count() == 1
    assert report.new_albums == []


def test_missing_folder_is_flagged_not_deleted(db, library, group):
    folder = make_album_folder(library, "Wesele")
    sync_albums()
    album = Album.objects.get()
    album.groups.add(group)
    folder.rename(library.parent / "gdzie-indziej")

    report = sync_albums()

    album.refresh_from_db()
    assert album.folder_missing
    assert report.missing_albums == ["Wesele"]
    assert list(album.groups.all()) == [group]

    (library.parent / "gdzie-indziej").rename(folder)
    sync_albums()
    album.refresh_from_db()
    assert not album.folder_missing


def test_sync_reports_unreadable_library(db, settings, tmp_path):
    blocker = tmp_path / "plik"
    blocker.write_text("to nie folder")
    settings.ARCHIVEHUB_ALBUMS_DIR = blocker

    report = sync_albums()

    assert not report.ok
    assert "Nie można odczytać" in report.error


# --- Widoczność -------------------------------------------------------------


@pytest.fixture
def albums(db):
    return {
        name: Album.objects.create(folder=name, title=name) for name in ["Bereza 1", "Włodyka 1", "Wspólny"]
    }


def visible(user):
    return sorted(a.folder for a in Album.objects.visible_to(user))


def test_user_sees_only_albums_of_own_groups(make_user, albums):
    bereza = FamilyGroup.objects.create(name="Bereza")
    wlodyka = FamilyGroup.objects.create(name="Włodyka")
    albums["Bereza 1"].groups.add(bereza)
    albums["Wspólny"].groups.add(bereza, wlodyka)
    albums["Włodyka 1"].groups.add(wlodyka)
    user = make_user("Karolina")
    user.family_groups.add(bereza)

    assert visible(user) == ["Bereza 1", "Wspólny"]

    user.family_groups.add(wlodyka)
    assert visible(user) == ["Bereza 1", "Wspólny", "Włodyka 1"]


def test_user_without_groups_sees_nothing(make_user, albums):
    assert visible(make_user("Karolina")) == []


def test_sees_all_group_sees_every_album_also_future(make_user, albums):
    everyone = FamilyGroup.objects.create(name="Wszyscy", sees_all_albums=True)
    user = make_user("Karolina")
    user.family_groups.add(everyone)

    assert visible(user) == ["Bereza 1", "Wspólny", "Włodyka 1"]
    Album.objects.create(folder="Nowy", title="Nowy")
    assert "Nowy" in visible(user)


def test_hidden_and_missing_albums_invisible_to_users(make_user, albums):
    everyone = FamilyGroup.objects.create(name="Wszyscy", sees_all_albums=True)
    user = make_user("Karolina")
    user.family_groups.add(everyone)
    Album.objects.filter(folder="Bereza 1").update(is_hidden=True)
    Album.objects.filter(folder="Włodyka 1").update(folder_missing=True)

    assert visible(user) == ["Wspólny"]


def test_master_sees_everything(master, albums):
    Album.objects.filter(folder="Bereza 1").update(is_hidden=True)
    assert visible(master) == ["Bereza 1", "Wspólny", "Włodyka 1"]


def test_inactive_user_sees_nothing(make_user, albums):
    everyone = FamilyGroup.objects.create(name="Wszyscy", sees_all_albums=True)
    user = make_user("Karolina", is_active=False)
    user.family_groups.add(everyone)
    assert visible(user) == []


def test_archive_page_lists_visible_albums(client, make_user, albums, group):
    albums["Bereza 1"].groups.add(group)
    user = make_user("Karolina")
    user.family_groups.add(group)
    client.force_login(user)

    page = client.get(reverse("archive")).content.decode()

    assert "Bereza 1" in page
    assert "Włodyka 1" not in page


# --- Panel: uprawnienia i synchronizacja ------------------------------------


def test_permissions_matrix_saves_checkboxes(master_client, albums):
    bereza = FamilyGroup.objects.create(name="Bereza")
    wlodyka = FamilyGroup.objects.create(name="Włodyka")
    albums["Wspólny"].groups.add(wlodyka)

    response = master_client.post(
        reverse("panel:permissions"),
        {
            f"album-{albums['Bereza 1'].pk}": [bereza.pk],
            f"album-{albums['Wspólny'].pk}": [bereza.pk, wlodyka.pk],
        },
    )

    assert response.status_code == 302
    assert list(albums["Bereza 1"].groups.all()) == [bereza]
    assert set(albums["Wspólny"].groups.all()) == {bereza, wlodyka}
    # Brak zaznaczeń = album nie jest przypisany do żadnej grupy.
    assert not albums["Włodyka 1"].groups.exists()


def test_permissions_ignore_sees_all_groups_and_garbage(master_client, albums):
    everyone = FamilyGroup.objects.create(name="Wszyscy", sees_all_albums=True)
    album = albums["Bereza 1"]

    master_client.post(reverse("panel:permissions"), {f"album-{album.pk}": [everyone.pk, "abc", "99999"]})

    assert not album.groups.exists()


def test_permissions_page_shows_matrix(master_client, albums):
    FamilyGroup.objects.create(name="Bereza")
    FamilyGroup.objects.create(name="Wszyscy", sees_all_albums=True)
    page = master_client.get(reverse("panel:permissions")).content.decode()
    assert f'name="album-{albums["Wspólny"].pk}"' in page
    assert "widzi wszystko" in page


def test_regular_user_cannot_change_permissions(client, make_user, albums, group):
    client.force_login(make_user("Karolina"))
    response = client.post(reverse("panel:permissions"), {f"album-{albums['Wspólny'].pk}": [group.pk]})
    assert response.status_code == 404
    assert not albums["Wspólny"].groups.exists()


def test_sync_button_runs_sync_and_records_history(master_client, master, library):
    make_album_folder(library, "Komunia")

    response = master_client.post(reverse("panel:sync"))

    assert response.status_code == 302
    report = SyncReport.objects.get()
    assert report.triggered_by == master
    assert report.new_albums == ["Komunia"]
    page = master_client.get(reverse("panel:sync")).content.decode()
    assert "Komunia" in page
    dashboard = master_client.get(reverse("panel:dashboard")).content.decode()
    assert "Synchronizacja" in dashboard


def test_group_can_be_marked_sees_all(master_client, group):
    master_client.post(
        reverse("panel:group_edit", args=[group.pk]),
        {"name": group.name, "description": "", "sees_all_albums": "on"},
    )
    group.refresh_from_db()
    assert group.sees_all_albums
