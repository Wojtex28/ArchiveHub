"""ETAP 46: płeć z imienia, chronologia życia i zdarzenia wpisywane ręcznie."""

import pytest
from django.urls import reverse

from albums.models import Person
from albums.names import guess_gender
from family import chronology, tree
from family.models import LifeEvent, TreeChange


@pytest.mark.parametrize(
    "name, gender",
    [
        ("Anna Bereza", "K"),
        ("Jan Bereza", "M"),
        ("Kuba Włodyka", "M"),
        ("Beatrycze Nowak", "K"),
        ("babcia Hela", "K"),
        ("dziadek Staszek", "M"),
        ("ks. Barnaba", "M"),
        ("J. K.", ""),
        ("???", ""),
    ],
)
def test_gender_guessed_from_name(name, gender):
    assert guess_gender(name) == gender


def test_new_person_gets_gender_and_it_can_be_corrected(master_client, db):
    anna = tree.add_person(None, "Anna Bereza")
    assert anna.gender == "K"
    url = reverse("family:api_person", args=[anna.pk])
    body = {"name": "Anna Bereza", "gender": "M"}
    assert master_client.post(url, body, content_type="application/json").status_code == 200
    anna.refresh_from_db()
    assert anna.gender == "M"
    # Strona otwarta przed aktualizacją nie wysyła płci i jej nie kasuje.
    master_client.post(url, {"name": "Anna Bereza"}, content_type="application/json")
    anna.refresh_from_db()
    assert anna.gender == "M"
    # Poprawiona ręcznie płeć nie wraca do podpowiedzi przy kolejnym zapisie.
    anna.save()
    assert Person.objects.get(pk=anna.pk).gender == "M"


@pytest.fixture
def jan(db):
    jan = tree.add_person(None, "Jan Bereza")
    Person.objects.filter(pk=jan.pk).update(
        birth_date="1920", birth_year=1920, death_date="1990", death_year=1990
    )
    jan.refresh_from_db()
    return jan


def test_timeline_builds_itself_from_the_tree(jan):
    anna = tree.add_person(None, "Anna Bereza")
    tree.add_relation(None, jan, anna, tree.PARTNER)
    tree.edit_couple(None, jan, anna, "1950", False)
    ewa = tree.add_person(None, "Ewa Bereza")
    Person.objects.filter(pk=ewa.pk).update(birth_date="1955", birth_year=1955)
    tree.add_relation(None, jan, ewa, tree.CHILD)
    ojciec = tree.add_person(None, "Stefan Bereza")
    Person.objects.filter(pk=ojciec.pk).update(death_date="1960", death_year=1960, deceased=True)
    tree.add_relation(None, jan, ojciec, tree.PARENT)
    tree.save_event(None, jan, {"kind": "wojsko", "date": "1939", "until": "1945", "place": "Lwów"})
    tree.save_event(None, jan, {"kind": "inne", "title": "Kupno domu"})
    rows = [(item.when, item.title, item.age) for item in chronology.timeline(jan)]
    assert rows == [
        ("1920", "Urodzenie", ""),
        ("1939 – 1945", "Wojsko, wojna, niewola", "19 lat"),
        ("1950", "Ślub: Anna Bereza", "30 lat"),
        ("1955", "Urodziła się córka Ewa Bereza", "35 lat"),
        ("1960", "Śmierć ojca: Stefan Bereza", "40 lat"),
        ("1990", "Śmierć", "70 lat"),
        ("", "Kupno domu", ""),
    ]


def test_event_add_edit_remove_and_undo(master_client, master, jan):
    page = reverse("family:person", args=[jan.pk])
    add = reverse("family:event_add", args=[jan.pk])
    bad = master_client.post(add, {"kind": "inne", "date": "kiedyś tam"})
    assert bad.status_code == 200 and not LifeEvent.objects.exists()
    response = master_client.post(add, {"kind": "mieszkanie", "date": "1950", "place": "Kraczkowa 12"})
    assert response.status_code == 302
    event = LifeEvent.objects.get()
    assert (event.person, event.year, event.place) == (jan, 1950, "Kraczkowa 12")
    assert "Kraczkowa 12" in master_client.get(page).content.decode()

    edit = reverse("family:event_edit", args=[event.pk])
    master_client.post(edit, {"kind": "mieszkanie", "date": "1950", "until": "1970", "place": "Kraczkowa 12"})
    event.refresh_from_db()
    assert event.until == "1970"
    changed = TreeChange.objects.filter(kind=TreeChange.EVENT_CHANGED).first()
    assert tree.edit_rows(changed) == [("do kiedy", "", "1970")]

    # Cofnięcie zmiany wraca poprzednią treść, cofnięcie dodania usuwa, cofnięcie usunięcia przywraca.
    tree.undo(master, changed)
    event.refresh_from_db()
    assert event.until == ""
    master_client.post(reverse("family:event_remove", args=[event.pk]))
    assert not LifeEvent.objects.exists()
    tree.undo(master, TreeChange.objects.filter(kind=TreeChange.EVENT_CHANGED).first())
    assert LifeEvent.objects.get().place == "Kraczkowa 12"


def test_viewer_sees_timeline_but_cannot_add(client, make_user, jan):
    viewer = make_user("Ola", tree_access="view")
    client.force_login(viewer)
    html = client.get(reverse("family:person", args=[jan.pk])).content.decode()
    assert "Chronologia" in html and "Dodaj zdarzenie" not in html
    assert (
        client.post(reverse("family:event_add", args=[jan.pk]), {"kind": "nauka", "date": "1930"}).status_code
        == 404
    )
    assert not LifeEvent.objects.exists()


def test_wedding_place_and_burial_show_in_timeline(master_client, jan):
    """ETAP 47: miejsce ślubu, pochówek i zdjęcie przy zdarzeniu."""
    anna = tree.add_person(None, "Anna Bereza")
    tree.add_relation(None, jan, anna, tree.PARTNER)
    master_client.post(
        reverse("family:couple_edit", args=[jan.pk, anna.pk]), {"since": "1950", "place": "Kraczkowa"}
    )
    # Kanwa sprzed aktualizacji nie wysyła miejsca: zostaje.
    api = reverse("family:api_couple")
    body = {"person": jan.pk, "other": anna.pk, "since": "1951", "ended": False}
    assert master_client.post(api, body, content_type="application/json").status_code == 200
    pair = tree.couple(jan, anna)
    assert (pair.since, pair.place) == ("1951", "Kraczkowa")
    url = reverse("family:api_person", args=[jan.pk])
    body = {"name": "Jan Bereza", "deceased": True, "death": "1990", "burial": "cmentarz w Kraczkowej, kw. 3"}
    assert master_client.post(url, body, content_type="application/json").status_code == 200
    rows = {
        item.title: (item.place, item.note) for item in chronology.timeline(Person.objects.get(pk=jan.pk))
    }
    assert rows["Ślub: Anna Bereza"] == ("Kraczkowa", "")
    assert rows["Śmierć"] == ("", "Pochówek: cmentarz w Kraczkowej, kw. 3")
    # Cofnięcie zmiany pary przywraca też miejsce.
    change = TreeChange.objects.filter(kind=TreeChange.COUPLE_EDITED).first()
    master_client.post(reverse("panel:tree_undo", args=[change.pk]))
    pair.refresh_from_db()
    assert (pair.since, pair.place) == ("1950", "Kraczkowa")


def test_event_photo_only_from_this_persons_visible_photos(master_client, jan, tmp_path, settings):
    from albums.models import Album, Photo

    settings.ARCHIVEHUB_ALBUMS_DIR = tmp_path
    album = Album.objects.create(folder="01", title="Brązowy")
    photo = Photo.objects.create(
        album=album, name="a", source_name="a.png", position=1, checksum="a", width=4, height=3
    )
    other = Photo.objects.create(
        album=album, name="b", source_name="b.png", position=2, checksum="b", width=4, height=3
    )
    photo.people.add(jan)
    add = reverse("family:event_add", args=[jan.pk])
    master_client.post(add, {"kind": "mieszkanie", "place": "Kraczkowa", "photo": other.pk})
    assert not LifeEvent.objects.exists()
    master_client.post(add, {"kind": "mieszkanie", "place": "Kraczkowa", "photo": photo.pk})
    event = LifeEvent.objects.get()
    assert event.photo == photo
    page = master_client.get(reverse("family:person", args=[jan.pk])).content.decode()
    assert "chronology__photo" in page
    change = TreeChange.objects.filter(kind=TreeChange.EVENT_CHANGED).first()
    assert ("zdjęcie", "", f"zdjęcie nr {photo.pk}") in tree.edit_rows(change)


def test_panel_lists_people_without_gender(master_client, db):
    unknown = tree.add_person(None, "J. K.")
    tree.add_person(None, "Anna Bereza")
    page = master_client.get(reverse("panel:tree_history")).content.decode()
    assert "Osoby bez płci (1)" in page
    master_client.post(reverse("panel:tree_gender", args=[unknown.pk]), {"plec": "M"})
    unknown.refresh_from_db()
    assert unknown.gender == "M"
    assert "Osoby bez płci" not in master_client.get(reverse("panel:tree_history")).content.decode()
