"""ETAP 8: pobieranie zdjęć w pełnej rozdzielczości, pojedynczo i jako ZIP."""

import io
import zipfile

import pytest
from django.urls import reverse
from PIL import Image

from accounts.models import FamilyGroup
from albums.models import Album, Photo


@pytest.fixture
def library(db, tmp_path, settings):
    settings.ARCHIVEHUB_ALBUMS_DIR = tmp_path / "albumy"
    return tmp_path


def make_photo(album, name, reverse=False, size=(40, 20)):
    photo = Photo.objects.create(
        album=album,
        name=name,
        source_name=f"{name}.png",
        position=album.photos.count() + 1,
        width=size[0],
        height=size[1],
        checksum=f"{album.folder}-{name}",
        has_reverse=reverse,
    )
    for side in [False, True] if reverse else [False]:
        for path, fmt in ((photo.original_path(side), "JPEG"), (photo.preview_path(side), "JPEG")):
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", size, "tan").save(path, fmt)
    return photo


@pytest.fixture
def family(library, make_user, group):
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


def zip_of(response):
    return zipfile.ZipFile(io.BytesIO(b"".join(response.streaming_content)))


# --- Pojedyncze zdjęcie -----------------------------------------------------


def test_download_full_resolution_original_as_attachment(karolina, family):
    photo = family["first"]
    response = karolina.get(reverse("albums:download", args=[photo.pk]))
    assert response.status_code == 200
    assert response["Content-Type"] == "image/jpeg"
    disposition = response["Content-Disposition"]
    assert disposition.startswith("attachment;")
    # Znaki niedozwolone w Windows (: /) zamienione, polskie litery zostają.
    assert (
        "filename*=UTF-8''Br%C4%85zowy%20album%201997%202004%20-%20img20250216_14475559_1.jpg" in disposition
    )
    assert b"".join(response.streaming_content) == photo.original_path().read_bytes()


def test_download_reverse(karolina, family):
    photo = family["first"]
    response = karolina.get(reverse("albums:download_reverse", args=[photo.pk]))
    assert response.status_code == 200
    assert "img20250216_14475559_1_r.jpg" in response["Content-Disposition"]
    assert karolina.get(reverse("albums:download_reverse", args=[family["second"].pk])).status_code == 404


def test_download_checks_permissions_every_time(karolina, family, group):
    assert karolina.get(reverse("albums:download", args=[family["stranger"].pk])).status_code == 404
    url = reverse("albums:download", args=[family["first"].pk])
    assert karolina.get(url).status_code == 200
    family["album"].groups.remove(group)
    assert karolina.get(url).status_code == 404


def test_download_after_logout_goes_to_login(client, family):
    response = client.get(reverse("albums:download", args=[family["first"].pk]))
    assert response.status_code == 302
    assert reverse("login") in response.url


def test_download_of_missing_file_is_404(karolina, family):
    family["second"].original_path().unlink()
    assert karolina.get(reverse("albums:download", args=[family["second"].pk])).status_code == 404


def test_download_rotates_file_if_worker_has_not_yet(karolina, family):
    photo = family["first"]
    karolina.post(reverse("albums:rotate", args=[photo.pk]), {"direction": "prawo"})
    response = karolina.get(reverse("albums:download", args=[photo.pk]))
    with Image.open(io.BytesIO(b"".join(response.streaming_content))) as image:
        assert image.size == (20, 40)
    photo.refresh_from_db()
    assert photo.applied_rotation == 90 and photo.pending_rotation() == 0


def test_viewer_has_download_links(karolina, family):
    album, photo = family["album"], family["first"]
    gallery = karolina.get(reverse("albums:gallery", args=[album.pk])).content.decode()
    assert f'data-download="{reverse("albums:download", args=[photo.pk])}"' in gallery
    assert f'data-reverse-download="{reverse("albums:download_reverse", args=[photo.pk])}"' in gallery
    page = karolina.get(reverse("albums:photo_reverse", args=[album.pk, photo.pk])).content.decode()
    assert reverse("albums:download_reverse", args=[photo.pk]) in page


# --- Zaznaczone jako ZIP ----------------------------------------------------


def test_selected_photos_download_as_zip_with_reverses(karolina, family):
    album = family["album"]
    response = karolina.post(
        reverse("albums:album_download", args=[album.pk]),
        {"photos": [family["first"].pk, family["second"].pk]},
    )
    assert response.status_code == 200
    assert response["Content-Type"] == "application/zip"
    assert "%282%20zdj.%29.zip" in response["Content-Disposition"]
    archive = zip_of(response)
    folder = "Brązowy album 1997 2004"
    assert sorted(archive.namelist()) == [
        f"{folder}/img20250216_14475559_1.jpg",
        f"{folder}/img20250216_14475559_1_r.jpg",
        f"{folder}/img20250216_14475559_2.jpg",
    ]
    assert (
        archive.read(f"{folder}/img20250216_14475559_2.jpg") == family["second"].original_path().read_bytes()
    )
    assert archive.testzip() is None


def test_zip_ignores_photos_from_other_albums_and_garbage(karolina, family):
    album = family["album"]
    response = karolina.post(
        reverse("albums:album_download", args=[album.pk]),
        {"photos": [family["second"].pk, family["stranger"].pk, "abc", "-1"]},
    )
    names = zip_of(response).namelist()
    assert len(names) == 1 and names[0].endswith("img20250216_14475559_2.jpg")


def test_zip_with_nothing_selected_returns_to_gallery(karolina, family):
    album = family["album"]
    response = karolina.post(reverse("albums:album_download", args=[album.pk]), {"photos": []})
    assert response.status_code == 302
    assert response.url == reverse("albums:gallery", args=[album.pk])


def test_zip_of_album_without_access_is_404(karolina, family):
    other = family["stranger"].album
    response = karolina.post(
        reverse("albums:album_download", args=[other.pk]), {"photos": [family["stranger"].pk]}
    )
    assert response.status_code == 404


def test_zip_needs_post_and_login(client, karolina, family):
    url = reverse("albums:album_download", args=[family["album"].pk])
    assert karolina.get(url).status_code == 405
    client.logout()
    response = client.post(url, {"photos": [family["first"].pk]})
    assert response.status_code == 302 and reverse("login") in response.url


def test_gallery_has_selection_form(karolina, family):
    page = karolina.get(reverse("albums:gallery", args=[family["album"].pk])).content.decode()
    assert f'action="{reverse("albums:album_download", args=[family["album"].pk])}"' in page
    assert f'name="photos" value="{family["first"].pk}"' in page
    assert "csrfmiddlewaretoken" in page
