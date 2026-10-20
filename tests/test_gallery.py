"""ETAP 7: galeria, podgląd na cały ekran, awers/rewers."""

import pytest
from django.urls import reverse
from django.utils.http import http_date
from PIL import Image

from accounts.models import FamilyGroup
from albums.models import Album, Photo


@pytest.fixture
def library(db, tmp_path, settings):
    settings.ARCHIVEHUB_ALBUMS_DIR = tmp_path / "albumy"
    return settings.ARCHIVEHUB_ALBUMS_DIR


def save(path, fmt):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 30), "tan").save(path, fmt)


def make_album(folder, *groups, photos=3, reverse_on=(), **extra):
    album = Album.objects.create(folder=folder, title=folder.replace("_", " "), **extra)
    album.groups.add(*groups)
    for i in range(1, photos + 1):
        photo = Photo.objects.create(
            album=album,
            name=f"img_{i}",
            source_name=f"img_{i}.png",
            position=i,
            width=4000,
            height=3000,
            checksum=f"{folder}-{i}",
            has_reverse=i in reverse_on,
        )
        for side in [False, True] if photo.has_reverse else [False]:
            save(photo.thumb_path(reverse=side), "WEBP")
            save(photo.preview_path(reverse=side), "JPEG")
    return album


@pytest.fixture
def karolina_client(client, make_user, group):
    user = make_user("Karolina")
    user.family_groups.add(group)
    client.force_login(user)
    return client


@pytest.fixture
def albums(library, group):
    other = FamilyGroup.objects.create(name="Włodyka")
    return {
        "mine": make_album("01_Bereza", group, reverse_on=(2,)),
        "other": make_album("02_Wlodyka", other, photos=1),
    }


def photos(album):
    return list(album.photos.all())


# --- Strona albumu ----------------------------------------------------------


def test_archive_card_links_to_gallery(karolina_client, albums):
    page = karolina_client.get(reverse("archive")).content.decode()
    assert reverse("albums:gallery", args=[albums["mine"].pk]) in page
    assert reverse("albums:gallery", args=[albums["other"].pk]) not in page


def test_gallery_shows_thumbnails_with_lazy_loading(karolina_client, albums):
    album = albums["mine"]
    response = karolina_client.get(reverse("albums:gallery", args=[album.pk]))
    assert response.status_code == 200
    page = response.content.decode()
    first, second, third = photos(album)
    for photo in (first, second, third):
        assert reverse("albums:thumb", args=[photo.pk]) in page
        assert reverse("albums:preview", args=[photo.pk]) in page
        assert reverse("albums:photo", args=[album.pk, photo.pk]) in page
    assert page.count('loading="lazy"') == 3
    assert page.count("z rewersem") == 1
    assert reverse("albums:preview_reverse", args=[second.pk]) in page
    assert reverse("albums:preview_reverse", args=[first.pk]) not in page
    # Siatka i podgląd nigdy nie sięgają po oryginał w pełnej rozdzielczości.
    assert "oryginal" not in page


def test_gallery_skips_photos_with_missing_files(karolina_client, albums):
    album = albums["mine"]
    gone = photos(album)[0]
    gone.file_missing = True
    gone.save()
    page = karolina_client.get(reverse("albums:gallery", args=[album.pk])).content.decode()
    assert reverse("albums:thumb", args=[gone.pk]) not in page
    assert "2 zdj." in page


@pytest.mark.parametrize("which", ["other", "hidden", "missing"])
def test_gallery_of_album_without_access_is_404(karolina_client, albums, group, which):
    if which == "other":
        album = albums["other"]
    else:
        flag = {"hidden": "is_hidden", "missing": "folder_missing"}[which]
        album = make_album(f"03_{which}", group, photos=1, **{flag: True})
    assert karolina_client.get(reverse("albums:gallery", args=[album.pk])).status_code == 404
    photo = photos(album)[0]
    assert karolina_client.get(reverse("albums:photo", args=[album.pk, photo.pk])).status_code == 404
    assert karolina_client.get(reverse("albums:preview", args=[photo.pk])).status_code == 404


def test_logged_out_visitor_goes_to_login(client, albums):
    album = albums["mine"]
    photo = photos(album)[0]
    for url in (
        reverse("albums:gallery", args=[album.pk]),
        reverse("albums:photo", args=[album.pk, photo.pk]),
        reverse("albums:preview", args=[photo.pk]),
    ):
        response = client.get(url)
        assert response.status_code == 302
        assert reverse("login") in response.url


def test_master_sees_hidden_album(master_client, library, group):
    album = make_album("Ukryty", group, photos=1, is_hidden=True)
    page = master_client.get(reverse("albums:gallery", args=[album.pk])).content.decode()
    assert "ukryty" in page


# --- Podgląd ----------------------------------------------------------------


def test_preview_is_jpeg_and_cached_privately(karolina_client, albums):
    photo = photos(albums["mine"])[0]
    response = karolina_client.get(reverse("albums:preview", args=[photo.pk]))
    assert response.status_code == 200
    assert response["Content-Type"] == "image/jpeg"
    assert response["Cache-Control"] == "private, max-age=86400"
    assert "Last-Modified" in response


def test_unchanged_preview_answers_304(karolina_client, albums):
    photo = photos(albums["mine"])[0]
    mtime = photo.preview_path().stat().st_mtime
    response = karolina_client.get(
        reverse("albums:preview", args=[photo.pk]), headers={"if-modified-since": http_date(mtime)}
    )
    assert response.status_code == 304
    stale = karolina_client.get(
        reverse("albums:preview", args=[photo.pk]), headers={"if-modified-since": http_date(mtime - 3600)}
    )
    assert stale.status_code == 200


def test_reverse_preview_only_for_photos_with_reverse(karolina_client, albums):
    first, second, _ = photos(albums["mine"])
    assert karolina_client.get(reverse("albums:preview_reverse", args=[second.pk])).status_code == 200
    assert karolina_client.get(reverse("albums:preview_reverse", args=[first.pk])).status_code == 404


def test_preview_falls_back_to_legacy_web_version(karolina_client, albums):
    photo = photos(albums["mine"])[0]
    photo.preview_path().unlink()
    assert karolina_client.get(reverse("albums:preview", args=[photo.pk])).status_code == 404
    save(photo.legacy_path(), "JPEG")
    assert karolina_client.get(reverse("albums:preview", args=[photo.pk])).status_code == 200


# --- Strona zdjęcia (bez JavaScriptu, link do wysłania) ------------------------


def test_photo_page_has_counter_and_neighbours(karolina_client, albums):
    album = albums["mine"]
    first, second, third = photos(album)
    page = karolina_client.get(reverse("albums:photo", args=[album.pk, second.pk])).content.decode()
    assert "2 / 3" in page
    assert reverse("albums:photo", args=[album.pk, first.pk]) in page
    assert reverse("albums:photo", args=[album.pk, third.pk]) in page
    assert reverse("albums:preview", args=[second.pk]) in page
    assert "Pokaż rewers" in page

    first_page = karolina_client.get(reverse("albums:photo", args=[album.pk, first.pk])).content.decode()
    assert 'rel="prev"' not in first_page and 'rel="next"' in first_page
    assert "Pokaż rewers" not in first_page


def test_photo_page_reverse_side(karolina_client, albums):
    album = albums["mine"]
    first, second, _ = photos(album)
    page = karolina_client.get(reverse("albums:photo_reverse", args=[album.pk, second.pk])).content.decode()
    assert reverse("albums:preview_reverse", args=[second.pk]) in page
    assert "Pokaż awers" in page
    assert karolina_client.get(reverse("albums:photo_reverse", args=[album.pk, first.pk])).status_code == 404


def test_photo_page_rejects_photo_from_another_album(karolina_client, albums):
    # Album, który widzę, i zdjęcie z cudzego: zamiana numeru w adresie nic nie da.
    stranger = photos(albums["other"])[0]
    url = reverse("albums:photo", args=[albums["mine"].pk, stranger.pk])
    assert karolina_client.get(url).status_code == 404


def test_viewer_pages_load_only_local_script(karolina_client, albums):
    album = albums["mine"]
    for url in (
        reverse("albums:gallery", args=[album.pk]),
        reverse("albums:photo", args=[album.pk, photos(album)[0].pk]),
    ):
        page = karolina_client.get(url).content.decode()
        assert "/static/js/gallery.js" in page
        assert "<script>" not in page
