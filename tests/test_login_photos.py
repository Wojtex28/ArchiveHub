import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from core.models import LoginPhoto


@pytest.fixture(autouse=True)
def photos_dir(tmp_path, settings):
    settings.ARCHIVEHUB_LOGIN_PHOTOS_DIR = tmp_path / "tlo"
    return settings.ARCHIVEHUB_LOGIN_PHOTOS_DIR


def jpeg_upload(name="P1080449.JPG", size=(2000, 1500), gps=True):
    image = Image.new("RGB", size, (200, 150, 100))
    exif = Image.Exif()
    exif[0x010F] = "Panasonic"  # producent aparatu
    if gps:
        exif[0x8825] = {1: "N", 2: (54.0, 30.0, 0.0)}
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", exif=exif)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


def test_upload_shrinks_and_strips_metadata(master_client, photos_dir):
    response = master_client.post(reverse("panel:login_photos"), {"photos": [jpeg_upload(), jpeg_upload()]})

    assert response.status_code == 302
    assert LoginPhoto.objects.count() == 2
    photo = LoginPhoto.objects.first()
    assert (photo.width, photo.height) == (900, 675)
    with Image.open(photo.path) as saved:
        assert saved.size == (900, 675)
        assert not saved.getexif()
        assert "exif" not in saved.info


def test_upload_rejects_non_images(master_client):
    fake = SimpleUploadedFile("wirus.jpg", b"to nie jest zdjecie", content_type="image/jpeg")

    response = master_client.post(reverse("panel:login_photos"), {"photos": [fake]}, follow=True)

    assert LoginPhoto.objects.count() == 0
    assert "to nie jest obsługiwany plik zdjęcia" in response.content.decode()


def test_regular_user_cannot_upload(client, make_user):
    client.force_login(make_user("Karolina"))
    response = client.post(reverse("panel:login_photos"), {"photos": [jpeg_upload()]})
    assert response.status_code == 404
    assert LoginPhoto.objects.count() == 0


def test_login_page_lists_active_photos_publicly(client, master_client):
    master_client.post(reverse("panel:login_photos"), {"photos": [jpeg_upload(), jpeg_upload()]})
    hidden = LoginPhoto.objects.last()
    master_client.post(reverse("panel:login_photo_toggle", args=[hidden.pk]))
    client.logout()

    page = client.get(reverse("login")).content.decode()

    shown = LoginPhoto.objects.first()
    assert reverse("login_photo", args=[shown.key]) in page
    assert str(hidden.key) not in page
    assert 'id="login-photos"' in page
    assert "js/login-background.js" in page

    image = client.get(reverse("login_photo", args=[shown.key]))
    assert image.status_code == 200
    assert image["Content-Type"] == "image/jpeg"
    assert client.get(reverse("login_photo", args=[hidden.key])).status_code == 404


def test_master_previews_hidden_photo(master_client):
    master_client.post(reverse("panel:login_photos"), {"photos": [jpeg_upload()]})
    photo = LoginPhoto.objects.get()
    master_client.post(reverse("panel:login_photo_toggle", args=[photo.pk]))

    assert master_client.get(reverse("panel:login_photo_preview", args=[photo.pk])).status_code == 200


def test_delete_removes_file(master_client, django_capture_on_commit_callbacks):
    master_client.post(reverse("panel:login_photos"), {"photos": [jpeg_upload()]})
    photo = LoginPhoto.objects.get()
    path = photo.path

    with django_capture_on_commit_callbacks(execute=True):
        master_client.post(reverse("panel:login_photo_delete", args=[photo.pk]))

    assert not LoginPhoto.objects.exists()
    assert not path.exists()


def test_login_page_works_without_photos(client, db):
    response = client.get(reverse("login"))
    assert response.status_code == 200
    assert 'id="login-photos"' in response.content.decode()
