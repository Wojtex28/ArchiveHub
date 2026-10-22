"""ETAP 14: wyszukiwanie zdjęć."""

import pytest
from django.urls import reverse

from accounts.models import FamilyGroup
from albums.dates import parse_date
from albums.metadata import save_metadata
from albums.models import Album, Comment, Person, Photo
from albums.search import normalize

FETCH = {"HTTP_X_REQUESTED_WITH": "fetch"}


def make_photo(album, name, position):
    return Photo.objects.create(
        album=album,
        name=name,
        source_name=f"{name}.png",
        position=position,
        checksum=f"{album.folder}-{name}",
        width=40,
        height=30,
    )


def describe(photo, user, date="", place="", people=(), tags=(), description=""):
    data = {
        "date": parse_date(date),
        "place": place,
        "people": list(people),
        "tags": list(tags),
        "description": description,
    }
    save_metadata(photo, user, data)


@pytest.fixture
def family(db, tmp_path, settings, make_user, group):
    settings.ARCHIVEHUB_ALBUMS_DIR = tmp_path
    brown = Album.objects.create(folder="01_Brazowy", title="Brązowy album")
    brown.groups.add(group)
    green = Album.objects.create(folder="02_Zielony", title="Zielony z Krakowa")
    green.groups.add(group)
    other = Album.objects.create(folder="03_Obcy", title="Obcy")
    other.groups.add(FamilyGroup.objects.create(name="Włodyka"))
    karolina = make_user("Karolina")
    karolina.family_groups.add(group)
    photos = {
        "wesele": make_photo(brown, "img_1", 1),
        "lato": make_photo(brown, "img_2", 2),
        "pusty": make_photo(brown, "img_3", 3),
        "krakow": make_photo(green, "img_1", 1),
        "obce": make_photo(other, "img_1", 1),
    }
    describe(
        photos["wesele"], karolina, "ok. 1965", "Berezów", ["Łucja Bereza", "Jan"], ["wesele"], "Wesele wujka"
    )
    describe(photos["lato"], karolina, "lato 1958", "Berezów, ogród", ["Jan"], ["wakacje"])
    describe(photos["krakow"], karolina, "1972", "Kraków", ["Ola"])
    describe(photos["obce"], karolina, "1965", "Berezów", ["Łucja Bereza"], ["wesele"], "Wesele obce")
    return {"user": karolina, "albums": (brown, green, other), **photos}


@pytest.fixture
def karolina(client, family):
    client.force_login(family["user"])
    return client


def found(client, **params):
    response = client.get(reverse("albums:search"), params)
    assert response.status_code == 200
    page = response.context.get("page")
    return None if page is None else [photo.pk for photo in page.object_list]


def test_normalize_ignores_case_and_polish_letters():
    assert normalize("  Łucja  BEREZA, Kraków źdźbło ") == "lucja bereza, krakow zdzblo"


def test_text_search_without_polish_letters(karolina, family):
    assert found(karolina, q="berezow") == [family["lato"].pk, family["wesele"].pk]
    assert found(karolina, q="LUCJA wesele") == [family["wesele"].pk]
    assert found(karolina, q="lucja kraków") == []


def test_text_matches_album_title(karolina, family):
    assert found(karolina, q="zielony") == [family["krakow"].pk]
    assert found(karolina, q="brazowy jan") == [family["lato"].pk, family["wesele"].pk]


def test_comments_are_searchable(karolina, family):
    comment = Comment.objects.create(photo=family["pusty"], author=family["user"], text="Tu jest pies Burek")
    assert found(karolina, q="burek") == [family["pusty"].pk]
    comment.delete()
    assert found(karolina, q="burek") == []


def test_person_tag_and_place_filters(karolina, family):
    assert found(karolina, osoba="łucja bereza") == [family["wesele"].pk]
    assert found(karolina, osoba="Jan") == [family["lato"].pk, family["wesele"].pk]
    assert found(karolina, tag="#wesele") == [family["wesele"].pk]
    assert found(karolina, miejsce="berezow") == [family["lato"].pk, family["wesele"].pk]
    assert found(karolina, miejsce="ogród") == [family["lato"].pk]


def test_year_range_overlaps_approximate_dates(karolina, family):
    # „ok. 1965” to 1963–1967, więc mieści się w latach 60.
    assert found(karolina, od=1960, do=1969) == [family["wesele"].pk]
    assert found(karolina, od=1966) == [family["wesele"].pk, family["krakow"].pk]
    assert found(karolina, do=1960) == [family["lato"].pk]


def test_album_and_undescribed_filters(karolina, family):
    brown = family["albums"][0]
    assert found(karolina, album=brown.pk, bez_opisu="on") == [family["pusty"].pk]
    assert found(karolina, album=family["albums"][2].pk) is None  # album spoza listy to błąd formularza


def test_results_only_from_visible_albums(karolina, family):
    results = found(karolina, q="wesele")
    assert family["obce"].pk not in results
    page = karolina.get(reverse("albums:search"), {"q": "wesele"}).content.decode()
    assert "Wesele obce" not in page
    assert reverse("albums:thumb", args=[family["obce"].pk]) not in page


def test_sorted_from_oldest_with_undated_last(karolina, family):
    assert found(karolina, q="brazowy") == [family["lato"].pk, family["wesele"].pk, family["pusty"].pk]


def test_overview_without_filters(karolina, family):
    response = karolina.get(reverse("albums:search"))
    assert response.context.get("page") is None
    page = response.content.decode()
    assert "?osoba=Jan" in page
    assert "lata 60." in page
    assert "Zdjęcia bez opisu: 1" in page
    assert "Obcy" not in page


def test_results_page_works_with_viewer(karolina, family):
    page = karolina.get(reverse("albums:search"), {"q": "jan"}).content.decode()
    assert 'data-album-title="Brązowy album"' in page
    assert "js/gallery.js" in page
    assert 'class="gallery-select"' not in page


def test_pagination_keeps_filters(karolina, family, monkeypatch):
    monkeypatch.setattr("albums.search.PER_PAGE", 1)
    response = karolina.get(reverse("albums:search"), {"q": "berezow"})
    assert response.context["page"].paginator.num_pages == 2
    assert "q=berezow&amp;strona=2" in response.content.decode()
    second = karolina.get(reverse("albums:search"), {"q": "berezow", "strona": 2})
    assert [photo.pk for photo in second.context["page"].object_list] == [family["wesele"].pk]


def test_renaming_person_updates_search(client, master, family):
    client.force_login(master)
    person = Person.objects.get(name="Ola")
    client.post(
        reverse("panel:named_edit", args=["osoby", person.pk]), {"action": "rename", "name": "Aleksandra"}
    )
    client.force_login(family["user"])
    assert found(client, q="aleksandra") == [family["krakow"].pk]
    assert found(client, q="ola") == []


def test_metadata_chips_link_to_search(karolina, family):
    page = karolina.get(reverse("albums:comments", args=[family["wesele"].pk]), **FETCH).content.decode()
    assert "/szukaj/?osoba=%C5%81ucja%20Bereza" in page
    assert "/szukaj/?tag=wesele" in page
    assert "/szukaj/?od=1963&amp;do=1967" in page


def test_search_requires_login(client, family):
    response = client.get(reverse("albums:search"), {"q": "wesele"})
    assert response.status_code == 302
