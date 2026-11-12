"""ETAP 44: punkt wskazujący osobę na zdjęciu."""

# ruff: noqa: F811 (fixtury z test_metadata są parametrami testów)

import pytest
from django.urls import reverse

from albums.models import Person, PersonMark, PhotoChange

from .test_metadata import FETCH, describe, family, karolina  # noqa: F401


def mark(client, photo, person, fetch=True, **values):
    data = {"osoba": person.pk, **values}
    return client.post(reverse("albums:mark", args=[photo.pk]), data, **(FETCH if fetch else {}))


@pytest.fixture
def tagged(karolina, family):
    describe(karolina, family["photo"], people="Jan Bereza, Anna Bereza")
    return family["photo"]


def test_old_tags_work_without_points(karolina, tagged):
    """Osoby oznaczone przed tą wersją nie mają punktu i nic się u nich nie zmienia."""
    assert tagged.people.count() == 2
    assert not tagged.marks.exists()
    html = karolina.get(reverse("albums:comments", args=[tagged.pk]), **FETCH).content.decode()
    assert "Jan Bereza" in html and "data-mark-person" in html
    assert "data-x=" not in html


def test_point_is_saved_moved_and_removed(karolina, tagged):
    jan = Person.objects.get(name="Jan Bereza")
    response = mark(karolina, tagged, jan, x="0.25", y="0.5")
    assert response.status_code == 200
    assert 'data-x="0.25"' in response.content.decode()
    mark(karolina, tagged, jan, x="0.75", y="0.1")
    saved = PersonMark.objects.get(photo=tagged, person=jan)
    assert (saved.x, saved.y) == (0.75, 0.1)
    assert tagged.people.count() == 2
    mark(karolina, tagged, jan, usun="1")
    assert not tagged.marks.exists()
    assert tagged.people.filter(pk=jan.pk).exists()
    notes = [change.changes["points"][1] for change in PhotoChange.objects.filter(changes__has_key="points")]
    assert sorted(notes) == ["Jan Bereza: bez punktu", "Jan Bereza: punkt", "Jan Bereza: punkt przesunięty"]


def test_point_without_javascript_returns_to_photo(karolina, tagged):
    jan = Person.objects.get(name="Jan Bereza")
    response = mark(karolina, tagged, jan, fetch=False, x="0.5", y="0.5")
    assert response.status_code == 302
    assert response.url.endswith("#osoby")


@pytest.mark.parametrize("values", [{"x": "1.5", "y": "0.5"}, {"x": "nan", "y": "0.5"}, {"x": "0.5"}, {}])
def test_bad_point_is_rejected(karolina, tagged, values):
    jan = Person.objects.get(name="Jan Bereza")
    assert mark(karolina, tagged, jan, **values).status_code == 400
    assert not tagged.marks.exists()


def test_only_people_tagged_on_this_photo_get_a_point(karolina, family, tagged):
    describe(karolina, family["second"], people="Stefan Włodyka")
    stefan = Person.objects.get(name="Stefan Włodyka")
    assert mark(karolina, tagged, stefan, x="0.5", y="0.5").status_code == 400


def test_point_needs_access_to_album(karolina, family, tagged):
    jan = Person.objects.get(name="Jan Bereza")
    assert mark(karolina, family["stranger"], jan, x="0.5", y="0.5").status_code == 404


def test_untagging_person_removes_the_point(karolina, tagged):
    jan = Person.objects.get(name="Jan Bereza")
    anna = Person.objects.get(name="Anna Bereza")
    mark(karolina, tagged, jan, x="0.2", y="0.2")
    mark(karolina, tagged, anna, x="0.8", y="0.2")
    describe(karolina, tagged, people="Anna Bereza")
    assert list(tagged.marks.values_list("person__name", flat=True)) == ["Anna Bereza"]


def test_points_turn_with_the_photo(karolina, tagged):
    jan = Person.objects.get(name="Jan Bereza")
    mark(karolina, tagged, jan, x="0.2", y="0.3")
    rotate = reverse("albums:rotate", args=[tagged.pk])
    karolina.post(rotate, {"side": "awers", "direction": "prawo"})
    saved = PersonMark.objects.get(person=jan)
    assert (round(saved.x, 4), round(saved.y, 4)) == (0.7, 0.2)
    karolina.post(rotate, {"side": "awers", "direction": "lewo"})
    saved.refresh_from_db()
    assert (round(saved.x, 4), round(saved.y, 4)) == (0.2, 0.3)
    # Rewers ma własny obrót: punkty awersu zostają.
    karolina.post(rotate, {"side": "rewers", "direction": "prawo"})
    saved.refresh_from_db()
    assert (round(saved.x, 4), round(saved.y, 4)) == (0.2, 0.3)
