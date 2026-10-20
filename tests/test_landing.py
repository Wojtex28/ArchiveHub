"""ETAP 11: strona główna."""

import pytest
from django.urls import reverse

from accounts.models import FamilyGroup
from albums.models import Album, Photo
from core.models import LoginPhoto
from core.views import plural


def make_photo(album, name, **extra):
    return Photo.objects.create(
        album=album,
        name=name,
        source_name=f"{name}.png",
        position=album.photos.count() + 1,
        checksum=f"{album.folder}-{name}",
        width=40,
        height=30,
        **extra,
    )


@pytest.fixture
def family(db, make_user, group):
    mine = Album.objects.create(folder="01_Brazowy", title="Brązowy")
    mine.groups.add(group)
    other = Album.objects.create(folder="02_Obcy", title="Obcy")
    other.groups.add(FamilyGroup.objects.create(name="Włodyka"))
    karolina = make_user("Karolina")
    karolina.family_groups.add(group)
    return {
        "user": karolina,
        "mine": [make_photo(mine, f"img_{n}") for n in range(7)],
        "missing": make_photo(mine, "brak", file_missing=True),
        "stranger": make_photo(other, "obce"),
    }


@pytest.mark.parametrize(
    ("number", "text"),
    [
        (1, "1 album"),
        (2, "2 albumy"),
        (4, "4 albumy"),
        (5, "5 albumów"),
        (12, "12 albumów"),
        (22, "22 albumy"),
    ],
)
def test_polish_plural(number, text):
    assert plural(number, "album", "albumy", "albumów") == text


def test_logged_in_landing_shows_own_photos_only(client, family):
    client.force_login(family["user"])
    response = client.get(reverse("landing"))
    cards = response.context["cards"]
    assert len(cards) == 5
    allowed = {reverse("albums:thumb", args=[photo.pk]) for photo in family["mine"]}
    assert all(card["src"].split("?")[0] in allowed for card in cards)
    page = response.content.decode()
    assert reverse("albums:thumb", args=[family["stranger"].pk]) not in page
    assert reverse("albums:thumb", args=[family["missing"].pk]) not in page
    assert "1 album · 7 zdjęć" in page
    assert "Zalogowano jako Karolina" in page


def test_landing_photos_link_to_photo_pages(client, family):
    client.force_login(family["user"])
    page = client.get(reverse("landing")).content.decode()
    photo = family["mine"][0]
    assert 'class="polaroid" href="/archiwum/' in page
    assert reverse("albums:photo", args=[photo.album_id, photo.pk]).startswith("/archiwum/")


def test_anonymous_landing_uses_only_public_login_photos(client, family):
    shown = LoginPhoto.objects.create(width=10, height=10)
    hidden = LoginPhoto.objects.create(width=10, height=10, is_active=False)
    page = client.get(reverse("landing")).content.decode()
    assert reverse("login_photo", args=[shown.key]) in page
    assert reverse("login_photo", args=[hidden.key]) not in page
    # Żadnych zdjęć z albumów ani liczb: strona jest publiczna.
    assert "/zdjecia/" not in page
    assert "zdjęć" not in page
    assert "Przejdź do archiwum" in page


def test_anonymous_landing_without_photos_is_plain(client, db):
    page = client.get(reverse("landing")).content.decode()
    assert "landing--photos" not in page
    assert "Przejdź do archiwum" in page
