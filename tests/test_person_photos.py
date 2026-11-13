"""ETAP 56: zdjęcia wgrane wprost do osoby (np. grób co roku)."""

import datetime
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from family import tree
from family.models import PersonPhoto


@pytest.fixture(autouse=True)
def photos_dir(tmp_path, settings):
    settings.ARCHIVEHUB_PERSON_PHOTOS_DIR = tmp_path / "osoby"
    return settings.ARCHIVEHUB_PERSON_PHOTOS_DIR


@pytest.fixture
def jan(db):
    return tree.add_person(None, "Jan Bereza")


def jpeg(name="IMG_0001.JPG", size=(4000, 3000), taken="2025:11:01 10:15:00"):
    image = Image.new("RGB", size, (120, 130, 140))
    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: (50.0, 1.0, 0.0)}  # GPS
    if taken:
        exif.get_ifd(0x8769)[0x9003] = taken
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", exif=exif)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


def upload(client, person, follow=False, **data):
    data.setdefault("photos", [jpeg()])
    data.setdefault("date", "")
    data.setdefault("caption", "")
    return client.post(reverse("family:person_photos_add", args=[person.pk]), data, follow=follow)


def test_upload_shrinks_strips_gps_and_takes_camera_date(master_client, master, jan, photos_dir):
    response = upload(master_client, jan, caption="Grób, Wszystkich Świętych")
    assert response.status_code == 302
    photo = PersonPhoto.objects.get()
    assert (photo.width, photo.height) == (2560, 1920)
    assert (photo.date, photo.year, photo.caption) == ("01.11.2025", 2025, "Grób, Wszystkich Świętych")
    assert photo.added_by == master
    with Image.open(photo.path) as saved:
        assert saved.size == (2560, 1920)
        assert not saved.getexif()
    with Image.open(photo.thumb_path) as thumb:
        assert max(thumb.size) == 640


def test_typed_date_wins_and_no_date_means_today(master_client, jan):
    upload(master_client, jan, date="listopad 2024")
    upload(master_client, jan, photos=[jpeg(taken=None)])
    dates = sorted(PersonPhoto.objects.values_list("date", flat=True))
    assert dates == sorted(["listopad 2024", datetime.date.today().strftime("%d.%m.%Y")])


def test_person_page_lists_newest_first_with_year_headings(master_client, jan):
    upload(master_client, jan, date="2023", caption="Grób 2023")
    upload(master_client, jan, date="2025", caption="Grób 2025")
    page = master_client.get(reverse("family:person", args=[jan.pk])).content.decode()
    assert "Zdjęcia dodane do osoby (2)" in page
    assert page.index("Grób 2025") < page.index("Grób 2023")
    assert 'own-photos__period">2025' in page


def test_bad_file_and_bad_date(master_client, jan):
    junk = SimpleUploadedFile("notatka.jpg", b"to nie jest zdjecie", content_type="image/jpeg")
    response = upload(master_client, jan, photos=[junk], follow=True)
    assert "nie jest obsługiwany plik zdjęcia" in response.content.decode()
    response = upload(master_client, jan, date="kiedyś tam")
    assert response.status_code == 200 and "Nie rozumiem tej daty" in response.content.decode()
    assert not PersonPhoto.objects.exists()


def test_file_needs_tree_access(client, make_user, master_client, jan):
    upload(master_client, jan)
    photo = PersonPhoto.objects.get()
    url = reverse("family:person_photo_file", args=[photo.key, "m"])
    assert master_client.get(url).status_code == 200
    assert master_client.get(reverse("family:person_photo_file", args=[photo.key, "x"])).status_code == 404
    client.force_login(make_user("Ola", tree_access="none"))
    assert client.get(url).status_code == 404
    client.force_login(make_user("Ela", tree_access="view"))
    assert client.get(url).status_code == 200
    assert upload(client, jan).status_code == 404


def test_edit_and_remove_only_by_uploader_or_master(make_user, master_client, jan):
    from django.test import Client

    client = Client()
    client.force_login(make_user("Ola", tree_access="edit"))
    upload(client, jan)
    upload(master_client, jan)
    mine, masters = PersonPhoto.objects.order_by("pk")
    client.post(reverse("family:person_photo_edit", args=[masters.pk]), {"date": "2020", "caption": "Grób"})
    masters.refresh_from_db()
    assert (masters.date, masters.year, masters.caption) == ("2020", 2020, "Grób")
    # Cudzego zdjęcia zwykły edytor nie usunie, swoje tak.
    assert client.post(reverse("family:person_photo_remove", args=[masters.pk])).status_code == 404
    client.post(reverse("family:person_photo_remove", args=[mine.pk]))
    assert list(PersonPhoto.objects.all()) == [masters]


@pytest.mark.django_db(transaction=True)
def test_files_removed_after_delete(photos_dir):
    from family.person_photos import delete_person_photo, save_person_photo

    jan = tree.add_person(None, "Jan Bereza")
    photo = save_person_photo(jan, jpeg())
    assert photo.path.exists() and photo.thumb_path.exists()
    delete_person_photo(photo)
    assert not photo.path.exists() and not photo.thumb_path.exists()
