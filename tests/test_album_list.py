"""ETAP 49: lista albumów: czytelne nazwy z folderów, okładka-mozaika, lata i liczba osób."""
# ruff: noqa: F811

from types import SimpleNamespace

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from albums.display import album_label, people_count_text, photo_count_text
from albums.models import Album, Person
from albums.sync import title_from_folder
from tests.test_downloads import library, make_photo  # noqa: F401


def label(folder, title=None):
    return album_label(SimpleNamespace(folder=folder, title=title or title_from_folder(folder)))


@pytest.mark.parametrize(
    ("folder", "number", "title", "years"),
    [
        ("01_BrązowyZeZlotaObramowka97-04_Pocięte", "01", "Brązowy ze Zlota Obramowka", "1997–2004"),
        ("02_ZielonyKrakow1962-1968", "02", "Zielony Krakow", "1962–1968"),
        ("03_Wakacje1978Mielno", "03", "Wakacje Mielno", "1978"),
        ("05_SlubyIChrzciny", "05", "Sluby i Chrzciny", ""),
        ("09_MałyNiebieskiPRL", "09", "Mały Niebieski PRL", ""),
        ("Luzne", "", "Luzne", ""),
        ("12", "", "12", ""),
        ("49_95-96-97_Pociete", "49", "Album 49", "1995–1997"),
        ("54_SzaryAlbumWDzbanki_Pociety", "54", "Szary Album w Dzbanki", ""),
    ],
)
def test_label_from_folder_name(folder, number, title, years):
    result = label(folder)
    assert (result.number, result.title, result.years) == (number, title, years)


def test_title_typed_in_panel_stays_as_is():
    typed = "Brązowy album ze złotą obwódką, 1997–2004"
    result = label("01_BrązowyZeZlotaObramowka97-04_Pocięte", typed)
    assert (result.number, result.title, result.years) == ("01", typed, "")


def test_polish_plurals():
    assert [photo_count_text(n) for n in (1, 2, 5, 12, 22, 25, 104)] == [
        "1 zdjęcie",
        "2 zdjęcia",
        "5 zdjęć",
        "12 zdjęć",
        "22 zdjęcia",
        "25 zdjęć",
        "104 zdjęcia",
    ]
    assert [people_count_text(n) for n in (1, 3, 7)] == ["1 osoba", "3 osoby", "7 osób"]


@pytest.fixture
def albums(library, make_user, group):
    album = Album.objects.create(folder="01_BrązowyZeZlotaObramowka97-04_Pocięte", title="")
    album.title = title_from_folder(album.folder)
    album.save()
    album.groups.add(group)
    photos = [make_photo(album, f"img_{n}") for n in range(1, 10)]
    album.photo_count = len(photos)
    album.cover = photos[4]
    album.save()
    dated = Album.objects.create(folder="02_Zielony", title="Zielony album")
    dated.groups.add(group)
    first = make_photo(dated, "a")
    second = make_photo(dated, "b")
    first.year_from, second.year_from, second.year_to = 1950, 1958, 1962
    first.save()
    second.save()
    ania, jan = Person.objects.create(name="Ania"), Person.objects.create(name="Jan")
    first.people.add(ania, jan)
    second.people.add(ania)
    dated.photo_count = 2
    dated.save()
    hidden = Album.objects.create(folder="03_Obcy", title="Obcy")
    make_photo(hidden, "obce")
    user = make_user("Karolina")
    user.family_groups.add(group)
    return {"user": user, "album": album, "dated": dated, "photos": photos}


def test_archive_list_shows_cards(client, albums):
    client.force_login(albums["user"])
    page = client.get(reverse("archive")).content.decode()
    assert "Brązowy ze Zlota Obramowka" in page
    assert "<span>9 zdjęć</span> · <span>1997–2004</span></span>" in page
    assert 'class="album-card__number">01<' in page
    assert "<span>2 zdjęcia</span> · <span>1950–1962</span> · <span>2 osoby</span>" in page
    assert "Obcy" not in page
    # Okładka z panelu jest pierwsza, potem kolejne zdjęcia; w sumie najwyżej 6 miniatur.
    cover = reverse("albums:thumb", args=[albums["photos"][4].pk])
    first = reverse("albums:thumb", args=[albums["photos"][0].pk])
    assert page.index(cover) < page.index(first)
    assert reverse("albums:thumb", args=[albums["photos"][7].pk]) not in page
    assert "album-card__cover--mosaic" in page and "data-album-preview" in page


def test_archive_list_query_count_does_not_grow(client, albums, group):
    client.force_login(albums["user"])
    with CaptureQueriesContext(connection) as before:
        client.get(reverse("archive"))
    for n in range(5):
        extra = Album.objects.create(folder=f"1{n}_Dodatkowy", title=f"Dodatkowy {n}")
        extra.groups.add(group)
        make_photo(extra, "x")
    with CaptureQueriesContext(connection) as after:
        client.get(reverse("archive"))
    assert len(after) == len(before)


def test_gallery_uses_readable_title(client, albums):
    client.force_login(albums["user"])
    page = client.get(reverse("albums:gallery", args=[albums["album"].pk])).content.decode()
    assert "<h1>Brązowy ze Zlota Obramowka, 1997–2004" in page
