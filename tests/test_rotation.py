"""ETAP 7b: obracanie zdjęć przez każdego, kto je ogląda."""

from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from accounts.models import FamilyGroup
from albums.importer import convert_scan
from albums.models import Album, Photo
from albums.rotation import apply_rotations

RED, BLUE = (200, 0, 0), (0, 0, 200)


@pytest.fixture
def library(db, tmp_path, settings):
    settings.ARCHIVEHUB_ALBUMS_DIR = tmp_path / "albumy"
    settings.ARCHIVEHUB_ROTATION_DELAY_SECONDS = 30
    return tmp_path


def two_tone(size=(40, 20)):
    """Lewa połowa czerwona, prawa niebieska: po obrocie widać, w którą stronę."""
    image = Image.new("RGB", size, BLUE)
    image.paste(RED, (0, 0, size[0] // 2, size[1]))
    return image


def save(image, path, fmt):
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, fmt, quality=95)


def make_photo(album, name="img_1", reverse=False):
    photo = Photo.objects.create(
        album=album,
        name=name,
        source_name=f"{name}.png",
        position=1,
        width=40,
        height=20,
        checksum=name,
        has_reverse=reverse,
    )
    for side in [False, True] if reverse else [False]:
        save(two_tone(), photo.original_path(side), "JPEG")
        save(two_tone(), photo.preview_path(side), "JPEG")
        save(two_tone(), photo.thumb_path(side), "WEBP")
    return photo


@pytest.fixture
def family(library, make_user, group):
    album = Album.objects.create(folder="01_Bereza", title="Bereza")
    album.groups.add(group)
    other = Album.objects.create(folder="02_Wlodyka", title="Włodyka")
    other.groups.add(FamilyGroup.objects.create(name="Włodyka"))
    karolina = make_user("Karolina")
    karolina.family_groups.add(group)
    return {
        "user": karolina,
        "photo": make_photo(album, reverse=True),
        "stranger": make_photo(other, name="obce"),
    }


@pytest.fixture
def karolina(client, family):
    client.force_login(family["user"])
    return client


def turn(client, photo, direction="prawo", side="awers"):
    return client.post(reverse("albums:rotate", args=[photo.pk]), {"direction": direction, "side": side})


def color_at(path, xy):
    with Image.open(path) as image:
        return image.convert("RGB").getpixel(xy)


def is_red(rgb):
    return rgb[0] > 150 and rgb[2] < 80


# --- Zapis obrotu -----------------------------------------------------------


def test_anyone_who_sees_photo_can_rotate_it_immediately(karolina, family):
    photo = family["photo"]
    response = turn(karolina, photo)
    assert response.status_code == 200
    assert response.json() == {"rotation": 90, "pending": 90}
    photo.refresh_from_db()
    assert photo.rotation == 90 and photo.applied_rotation == 0
    assert photo.rotated_by == family["user"]
    assert photo.rotated_at is not None


def test_rotation_wraps_around_both_ways(karolina, family):
    photo = family["photo"]
    assert turn(karolina, photo, "lewo").json()["rotation"] == 270
    for expected in (0, 90, 180, 270, 0):
        assert turn(karolina, photo, "prawo").json()["rotation"] == expected


def test_reverse_side_rotates_separately(karolina, family):
    photo = family["photo"]
    turn(karolina, photo, "lewo", side="rewers")
    photo.refresh_from_db()
    assert (photo.rotation, photo.reverse_rotation) == (0, 270)


def test_reverse_of_photo_without_reverse_is_404(karolina, family, group):
    plain = make_photo(family["photo"].album, name="img_2")
    assert turn(karolina, plain, side="rewers").status_code == 404


def test_cannot_rotate_photo_from_album_without_access(karolina, family):
    response = turn(karolina, family["stranger"])
    assert response.status_code == 404
    family["stranger"].refresh_from_db()
    assert family["stranger"].rotation == 0


def test_logged_out_cannot_rotate(client, family):
    assert turn(client, family["photo"]).status_code == 302
    family["photo"].refresh_from_db()
    assert family["photo"].rotation == 0


def test_rotate_needs_post_and_known_direction(karolina, family):
    url = reverse("albums:rotate", args=[family["photo"].pk])
    assert karolina.get(url).status_code == 405
    assert karolina.post(url, {"direction": "dookoła"}).status_code == 400


def test_rotate_is_protected_by_csrf(family):
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(family["user"])
    photo = family["photo"]
    assert turn(strict, photo).status_code == 403
    page = strict.get(reverse("albums:gallery", args=[photo.album.pk])).content.decode()
    token = page.split('data-csrf="')[1].split('"')[0]
    response = strict.post(
        reverse("albums:rotate", args=[photo.pk]), {"direction": "prawo"}, headers={"x-csrftoken": token}
    )
    assert response.status_code == 200


def test_gallery_shows_rotation_before_files_are_rotated(karolina, family):
    photo = family["photo"]
    turn(karolina, photo)
    turn(karolina, photo, side="rewers")
    page = karolina.get(reverse("albums:gallery", args=[photo.album.pk])).content.decode()
    assert 'class="rot-90"' in page
    assert 'data-rotation="90"' in page and 'data-reverse-rotation="90"' in page
    viewer = karolina.get(reverse("albums:photo", args=[photo.album.pk, photo.pk])).content.decode()
    assert 'data-rotation="90"' in viewer
    assert "Obróć w prawo" in viewer


# --- Obracanie plików przez worker -------------------------------------------


def later(seconds=31):
    return timezone.now() + timedelta(seconds=seconds)


def test_worker_waits_until_people_stop_clicking(karolina, family):
    photo = family["photo"]
    turn(karolina, photo)
    assert apply_rotations(now=timezone.now()) == 0
    photo.refresh_from_db()
    assert photo.applied_rotation == 0


def test_worker_rotates_original_preview_and_thumbnail(karolina, family):
    photo = family["photo"]
    turn(karolina, photo)
    assert apply_rotations(now=later()) == 1
    photo.refresh_from_db()
    assert (photo.rotation, photo.applied_rotation, photo.pending_rotation()) == (90, 90, 0)
    assert (photo.width, photo.height) == (20, 40)
    for path in (photo.original_path(), photo.preview_path(), photo.thumb_path()):
        with Image.open(path) as image:
            assert image.size == (20, 40)
        # Lewa (czerwona) połowa po obrocie w prawo jest na górze.
        assert is_red(color_at(path, (10, 5)))
        assert not is_red(color_at(path, (10, 35)))
    # Pliki rewersu bez zmian.
    with Image.open(photo.original_path(reverse=True)) as image:
        assert image.size == (40, 20)
    assert not list(photo.original_path().parent.glob(".*"))


def test_file_urls_change_after_rotation_so_browser_does_not_show_old_file(karolina, family):
    photo = family["photo"]
    before = karolina.get(reverse("albums:gallery", args=[photo.album.pk])).content.decode()
    turn(karolina, photo)
    apply_rotations(now=later())
    after = karolina.get(reverse("albums:gallery", args=[photo.album.pk])).content.decode()
    thumb = reverse("albums:thumb", args=[photo.pk])
    assert f"{thumb}?v=0" in before
    assert f"{thumb}?v=90" in after
    assert 'class="rot-0"' in after


def test_worker_rotates_reverse_side(karolina, family):
    photo = family["photo"]
    turn(karolina, photo, "lewo", side="rewers")
    apply_rotations(now=later())
    photo.refresh_from_db()
    assert photo.reverse_applied_rotation == 270
    assert (photo.width, photo.height) == (40, 20)
    path = photo.original_path(reverse=True)
    # Obrót w lewo: lewa (czerwona) połowa ląduje na dole.
    assert is_red(color_at(path, (10, 35)))


def test_full_turn_needs_no_file_work(karolina, family):
    photo = family["photo"]
    for _ in range(4):
        turn(karolina, photo)
    mtime = photo.original_path().stat().st_mtime_ns
    assert apply_rotations(now=later()) == 0
    assert photo.original_path().stat().st_mtime_ns == mtime


def test_click_during_rotation_is_applied_on_next_pass(karolina, family):
    photo = family["photo"]
    turn(karolina, photo)
    apply_rotations(now=later())
    turn(karolina, photo)
    apply_rotations(now=later())
    photo.refresh_from_db()
    assert photo.applied_rotation == 180
    assert (photo.width, photo.height) == (40, 20)
    assert is_red(color_at(photo.original_path(), (35, 10)))


def test_reprocessing_from_scan_keeps_rotation(library, family):
    photo = family["photo"]
    photo.rotation = 90
    photo.save()
    scan = library / "skan.png"
    two_tone().save(scan)
    size = convert_scan(scan, photo)
    assert size == (20, 40)
    assert photo.applied_rotation == 90
    assert is_red(color_at(photo.original_path(), (10, 5)))
