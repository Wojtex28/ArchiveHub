from datetime import timedelta

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from albums.importer import folder_signature, queue_legacy_albums, reset_interrupted, scan_import_dir
from albums.models import Album, ImportJob, Photo
from albums.sync import sync_albums


@pytest.fixture
def dirs(db, tmp_path, settings):
    settings.DATA_DIR = tmp_path / "data"
    settings.DATA_DIR.mkdir()
    settings.ARCHIVEHUB_ALBUMS_DIR = tmp_path / "albumy"
    settings.ARCHIVEHUB_IMPORT_DIR = tmp_path / "import"
    settings.ARCHIVEHUB_IMPORT_DIR.mkdir()
    settings.ARCHIVEHUB_IMPORT_STABLE_MINUTES = 10
    settings.ARCHIVEHUB_ORIGINAL_MAX_SIDE = 0
    settings.ARCHIVEHUB_PREVIEW_MAX_SIDE = 400
    settings.ARCHIVEHUB_THUMB_MAX_SIDE = 100
    return settings


def scan(folder, name, size=(800, 600), color=(120, 90, 60), fmt=None):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    Image.new("RGB", size, color).save(path, fmt)
    return path


def import_now(dirs):
    """Pierwsze przejście zauważa foldery, kolejne (po czasie stabilności) importują po jednym."""
    start = timezone.now()
    scan_import_dir(now=start)
    finished = []
    while done := scan_import_dir(now=start + timedelta(minutes=dirs.ARCHIVEHUB_IMPORT_STABLE_MINUTES)):
        finished += done
    return finished


# --- Czekanie na koniec kopiowania ---------------------------------------------


def test_folder_waits_until_stable(dirs):
    folder = dirs.ARCHIVEHUB_IMPORT_DIR / "Wesele_1968"
    scan(folder, "001.jpg", color=(1, 1, 1))
    start = timezone.now()

    assert scan_import_dir(now=start) == []
    job = ImportJob.objects.get()
    assert job.status == ImportJob.WAITING
    assert not Album.objects.exists()

    # Kopiowanie trwa: doszedł plik, odliczanie zaczyna się od nowa.
    scan(folder, "002.jpg", color=(2, 2, 2))
    assert scan_import_dir(now=start + timedelta(minutes=8)) == []
    assert scan_import_dir(now=start + timedelta(minutes=12)) == []
    job.refresh_from_db()
    assert job.stable_since == start + timedelta(minutes=8)

    finished = scan_import_dir(now=start + timedelta(minutes=18))
    assert [j.status for j in finished] == [ImportJob.DONE]
    assert Album.objects.get().photo_count == 2


def test_empty_folders_and_other_files_are_ignored(dirs):
    (dirs.ARCHIVEHUB_IMPORT_DIR / "Pusty").mkdir()
    (dirs.ARCHIVEHUB_IMPORT_DIR / "Notatki").mkdir()
    (dirs.ARCHIVEHUB_IMPORT_DIR / "Notatki" / "opis.txt").write_text("x")
    (dirs.ARCHIVEHUB_IMPORT_DIR / ".Trash").mkdir()

    import_now(dirs)

    assert not ImportJob.objects.exists()


def test_missing_import_dir_does_nothing(dirs, tmp_path):
    dirs.ARCHIVEHUB_IMPORT_DIR = tmp_path / "nie-ma"
    assert scan_import_dir() == []


# --- Konwersja i rewersy --------------------------------------------------------


def test_import_creates_original_preview_thumbnail_and_pairs_reverses(dirs):
    folder = dirs.ARCHIVEHUB_IMPORT_DIR / "Album_03_1967"
    scan(folder, "10.jpg")
    scan(folder, "2.tif", size=(600, 900), fmt="TIFF")
    scan(folder, "2_r.jpg", color=(240, 240, 230))
    scan(folder, "1.png", fmt="PNG")

    [job] = import_now(dirs)

    assert job.status == ImportJob.DONE
    assert (job.photos_added, job.reverses_added, job.skipped) == (3, 1, [])
    album = Album.objects.get()
    assert album.title == "Album 03 1967"
    assert album.photo_count == 3
    photos = list(album.photos.order_by("position"))
    # Kolejność jak w Eksploratorze: 1, 2, 10.
    assert [p.name for p in photos] == ["1", "2", "10"]
    assert [p.has_reverse for p in photos] == [False, True, False]

    second = photos[1]
    # Oryginał w pełnej rozdzielczości skanu.
    assert (second.width, second.height) == (600, 900)
    assert second.source_name == "2.tif"
    with Image.open(second.original_path()) as original:
        assert original.format == "JPEG"
        assert original.size == (600, 900)
    with Image.open(second.preview_path()) as preview:
        assert preview.format == "JPEG"
        assert preview.size == (267, 400)
    with Image.open(second.thumb_path()) as thumb:
        assert thumb.format == "WEBP"
        assert max(thumb.size) == 100
    assert second.original_path(reverse=True).name == "2_r.jpg"
    assert second.preview_path(reverse=True).is_file()
    assert second.thumb_path(reverse=True).is_file()
    # Udział tylko czytany: oryginały zostają na miejscu.
    assert sorted(f.name for f in folder.iterdir()) == ["1.png", "10.jpg", "2.tif", "2_r.jpg"]


def test_exif_rotation_is_applied_and_metadata_dropped(dirs):
    folder = dirs.ARCHIVEHUB_IMPORT_DIR / "Obrocone"
    folder.mkdir()
    image = Image.new("RGB", (800, 600))
    exif = image.getexif()
    exif[0x0112] = 6  # obrót o 90°
    exif[0x010F] = "Skaner"
    image.save(folder / "001.jpg", exif=exif)

    import_now(dirs)

    photo = Photo.objects.get()
    assert (photo.width, photo.height) == (600, 800)
    with Image.open(photo.original_path()) as original:
        assert not original.getexif()


def test_sixteen_bit_grayscale_scan_is_converted(dirs):
    folder = dirs.ARCHIVEHUB_IMPORT_DIR / "Szary"
    folder.mkdir()
    Image.new("I;16", (500, 400), 30000).save(folder / "001.png")

    import_now(dirs)

    with Image.open(Photo.objects.get().original_path()) as original:
        assert original.mode == "L"


def test_broken_file_and_orphan_reverse_are_reported(dirs):
    folder = dirs.ARCHIVEHUB_IMPORT_DIR / "Uszkodzony"
    scan(folder, "001.jpg")
    (folder / "002.jpg").write_bytes(b"to nie jest jpeg")
    scan(folder, "007_r.jpg")

    [job] = import_now(dirs)

    assert job.status == ImportJob.DONE
    assert job.photos_added == 1
    assert len(job.skipped) == 2
    assert job.skipped[0].startswith("002.jpg: nie udało się odczytać")
    assert job.skipped[1] == "007_r.jpg: rewers bez zdjęcia głównego"
    assert not list((dirs.ARCHIVEHUB_ALBUMS_DIR / "Uszkodzony" / "zdjecia").glob("002*"))


def test_underscore_folder_becomes_hidden_album(dirs):
    scan(dirs.ARCHIVEHUB_IMPORT_DIR / "_Prywatne", "001.jpg")
    import_now(dirs)
    album = Album.objects.get()
    assert album.is_hidden
    assert album.title == "Prywatne"


# --- Ponowny import -------------------------------------------------------------


def test_added_files_trigger_reimport_without_duplicates(dirs):
    folder = dirs.ARCHIVEHUB_IMPORT_DIR / "Komunia"
    scan(folder, "001.jpg", color=(10, 10, 10))
    scan(folder, "002.jpg", color=(20, 20, 20))
    import_now(dirs)

    # Bez zmian w folderze nic się nie dzieje.
    assert import_now(dirs) == []
    assert ImportJob.objects.count() == 1

    scan(folder, "003.jpg", color=(30, 30, 30))
    scan(folder, "kopia.jpg", color=(10, 10, 10))  # to samo co 001.jpg
    scan(folder, "001_r.jpg", color=(200, 200, 200))  # rewers dorzucony później
    [job] = import_now(dirs)

    assert ImportJob.objects.count() == 2
    assert (job.photos_added, job.reverses_added) == (1, 1)
    assert job.skipped == ["kopia.jpg: to samo zdjęcie jest już w albumie"]
    album = Album.objects.get()
    assert album.photo_count == 3
    assert [p.name for p in album.photos.order_by("position")] == ["001", "002", "003"]
    assert album.photos.get(name="001").has_reverse


def test_import_into_existing_album_keeps_settings(dirs, group):
    album = Album.objects.create(folder="Wesele", title="Wesele dziadków", folder_missing=True)
    album.groups.add(group)
    scan(dirs.ARCHIVEHUB_IMPORT_DIR / "Wesele", "001.jpg")

    import_now(dirs)

    album.refresh_from_db()
    assert album.title == "Wesele dziadków"
    assert not album.folder_missing
    assert list(album.groups.all()) == [group]
    assert album.photo_count == 1


def test_interrupted_import_restarts_and_skips_done_photos(dirs):
    folder = dirs.ARCHIVEHUB_IMPORT_DIR / "Przerwany"
    scan(folder, "001.jpg", color=(1, 2, 3))
    import_now(dirs)
    job = ImportJob.objects.get()
    scan(folder, "002.jpg", color=(4, 5, 6))
    # Worker padł w trakcie importu folderu z nowym plikiem.
    job = ImportJob.objects.create(
        folder="Przerwany",
        signature=folder_signature(sorted(folder.iterdir())),
        stable_since=timezone.now() - timedelta(hours=1),
        status=ImportJob.PROCESSING,
    )

    assert reset_interrupted() == 1
    [job] = scan_import_dir()

    assert job.status == ImportJob.DONE
    assert job.photos_added == 1
    assert Album.objects.get().photo_count == 2


def test_worker_command_runs_once_and_writes_heartbeat(dirs):
    scan(dirs.ARCHIVEHUB_IMPORT_DIR / "Album", "001.jpg")
    call_command("import_worker", "--once")
    assert ImportJob.objects.get().status == ImportJob.WAITING
    assert (dirs.DATA_DIR / "import-worker.heartbeat").is_file()


def test_original_can_be_capped_by_setting(dirs):
    dirs.ARCHIVEHUB_ORIGINAL_MAX_SIDE = 500
    scan(dirs.ARCHIVEHUB_IMPORT_DIR / "Duze", "001.png", size=(1000, 800), fmt="PNG")
    import_now(dirs)
    assert (Photo.objects.get().width, Photo.objects.get().height) == (500, 400)


# --- Ponowne przetworzenie --------------------------------------------------------


def make_legacy(photo):
    """Stan po pierwszym wydaniu importu: tylko zdjecia/ (5000 px) i miniatury/."""
    photo.legacy_path().parent.mkdir(parents=True, exist_ok=True)
    photo.original_path().rename(photo.legacy_path())
    photo.preview_path().unlink()
    if photo.has_reverse:
        photo.original_path(True).rename(photo.legacy_path(True))
        photo.preview_path(True).unlink()


def test_reprocess_rebuilds_files_from_share_and_keeps_settings(dirs, group):
    folder = dirs.ARCHIVEHUB_IMPORT_DIR / "Komunia"
    scan(folder, "001.png", size=(1200, 900), color=(1, 1, 1), fmt="PNG")
    scan(folder, "001_r.png", size=(1200, 900), color=(9, 9, 9), fmt="PNG")
    scan(folder, "002.png", size=(900, 1200), color=(2, 2, 2), fmt="PNG")
    import_now(dirs)
    album = Album.objects.get()
    album.title = "Komunia Janka"
    album.save()
    album.groups.add(group)
    for photo in album.photos.all():
        make_legacy(photo)
    # Jeden skan zniknął z udziału: jego zdjęcie zostaje w starej wersji.
    (folder / "002.png").unlink()

    assert queue_legacy_albums() == 1
    [job] = scan_import_dir()

    assert job.is_reprocess and job.status == ImportJob.DONE
    assert (job.photos_added, job.reverses_added) == (1, 1)
    assert job.skipped == ["002.png: brak skanu w udziale, zostaje dotychczasowa wersja"]
    album.refresh_from_db()
    assert not album.reprocess_requested
    assert album.title == "Komunia Janka"
    assert list(album.groups.all()) == [group]
    first = album.photos.get(name="001")
    assert (first.width, first.height) == (1200, 900)
    assert first.original_path().is_file() and first.preview_path(reverse=True).is_file()
    assert not first.legacy_path().exists() and not first.legacy_path(reverse=True).exists()
    second = album.photos.get(name="002")
    assert second.legacy_path().is_file()
    assert album.photos.count() == 2
    # Folder bez zmian: kolejne przejście nic nie robi.
    assert scan_import_dir() == []


def test_reprocess_without_folder_in_share_reports_error(dirs):
    album = Album.objects.create(folder="Zniknal", title="Zniknął", reprocess_requested=True)
    assert [j.status for j in scan_import_dir()] == []
    job = ImportJob.objects.get()
    assert job.is_reprocess and job.status == ImportJob.FAILED
    assert "Zniknal" in job.error
    album.refresh_from_db()
    assert not album.reprocess_requested


def test_reprocess_waits_while_folder_is_copied(dirs):
    folder = dirs.ARCHIVEHUB_IMPORT_DIR / "Wesele"
    scan(folder, "001.jpg")
    import_now(dirs)
    scan(folder, "002.jpg", color=(3, 3, 3))
    scan_import_dir()  # nowy plik: folder czeka na koniec kopiowania
    Album.objects.update(reprocess_requested=True)

    assert scan_import_dir() == []
    assert Album.objects.get().reprocess_requested


def test_panel_reprocess_button(master_client, dirs):
    scan(dirs.ARCHIVEHUB_IMPORT_DIR / "Wesele", "001.jpg")
    import_now(dirs)
    album = Album.objects.get()
    page = master_client.get(reverse("panel:album_detail", args=[album.pk])).content.decode()
    assert "Przetwórz ponownie" in page
    assert "na dysku" in page

    response = master_client.post(reverse("panel:album_reprocess", args=[album.pk]))

    assert response.status_code == 302
    album.refresh_from_db()
    assert album.reprocess_requested
    assert master_client.get(reverse("panel:album_reprocess", args=[album.pk])).status_code == 405


def test_regular_user_cannot_request_reprocess(client, make_user, dirs):
    album = Album.objects.create(folder="Wesele", title="Wesele")
    client.force_login(make_user("Karolina"))
    assert client.post(reverse("panel:album_reprocess", args=[album.pk])).status_code == 404
    album.refresh_from_db()
    assert not album.reprocess_requested


# --- Synchronizacja po imporcie ------------------------------------------------


def test_sync_flags_photos_with_missing_files(dirs):
    scan(dirs.ARCHIVEHUB_IMPORT_DIR / "Wesele", "001.jpg", color=(1, 1, 1))
    scan(dirs.ARCHIVEHUB_IMPORT_DIR / "Wesele", "002.jpg", color=(2, 2, 2))
    import_now(dirs)
    missing = Photo.objects.get(name="002")
    missing.preview_path().unlink()

    report = sync_albums()

    assert report.photos_total == 1
    assert report.missing_photos == ["Wesele/002"]
    missing.refresh_from_db()
    assert missing.file_missing
    assert Photo.objects.count() == 2


# --- Miniatury i uprawnienia ---------------------------------------------------


@pytest.fixture
def imported(dirs, group):
    scan(dirs.ARCHIVEHUB_IMPORT_DIR / "Bereza", "001.jpg")
    scan(dirs.ARCHIVEHUB_IMPORT_DIR / "Bereza", "001_r.jpg", color=(9, 9, 9))
    scan(dirs.ARCHIVEHUB_IMPORT_DIR / "Inny", "001.jpg", color=(50, 50, 50))
    import_now(dirs)
    Album.objects.get(folder="Bereza").groups.add(group)
    return {p.album.folder: p for p in Photo.objects.select_related("album")}


def test_thumbnail_served_only_for_visible_albums(client, make_user, group, imported):
    user = make_user("Karolina")
    user.family_groups.add(group)
    client.force_login(user)

    response = client.get(reverse("albums:thumb", args=[imported["Bereza"].pk]))
    assert response.status_code == 200
    assert response["Content-Type"] == "image/webp"
    assert "private" in response["Cache-Control"]
    assert client.get(reverse("albums:thumb_reverse", args=[imported["Bereza"].pk])).status_code == 200
    assert client.get(reverse("albums:thumb", args=[imported["Inny"].pk])).status_code == 404
    assert client.get(reverse("albums:thumb_reverse", args=[imported["Inny"].pk])).status_code == 404


def test_thumbnail_requires_login(client, imported):
    response = client.get(reverse("albums:thumb", args=[imported["Bereza"].pk]))
    assert response.status_code == 302


def test_missing_reverse_is_404(master_client, imported):
    assert master_client.get(reverse("albums:thumb_reverse", args=[imported["Inny"].pk])).status_code == 404


# --- Panel ----------------------------------------------------------------------


def test_panel_album_detail_and_sync_show_imports(master_client, imported):
    album = Album.objects.get(folder="Bereza")
    page = master_client.get(reverse("panel:album_detail", args=[album.pk])).content.decode()
    assert reverse("albums:thumb", args=[imported["Bereza"].pk]) in page
    assert "rewers" in page.lower()

    sync_page = master_client.get(reverse("panel:sync")).content.decode()
    assert "Import z udziału sieciowego" in sync_page
    assert "Bereza" in sync_page
    dashboard = master_client.get(reverse("panel:dashboard"))
    assert dashboard.status_code == 200


def test_regular_user_cannot_open_album_detail(client, make_user, imported):
    client.force_login(make_user("Karolina"))
    album = Album.objects.get(folder="Bereza")
    assert client.get(reverse("panel:album_detail", args=[album.pk])).status_code == 404
