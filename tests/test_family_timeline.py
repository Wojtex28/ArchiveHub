"""ETAP 32: pasy pokoleń i oś czasu w drzewie."""

import pytest
from django.urls import reverse

from family import tree


@pytest.fixture
def viewer(client, make_user):
    client.force_login(make_user("Karolina"))
    return client


def test_tree_data_has_birth_and_death_years_for_timeline(viewer, db):
    anna = tree.add_person(None, "Anna Bereza")
    anna.birth_date, anna.death_date, anna.deceased = "12.03.1921", "1998", True
    anna.birth_year, anna.death_year = 1921, 1998
    anna.save()
    jan = tree.add_person(None, "Jan Bereza")
    data = viewer.get(reverse("family:data")).json()
    people = {p["name"]: p for p in data["people"]}
    assert people["Anna Bereza"]["born"] == 1921
    assert people["Anna Bereza"]["died"] == 1998
    assert people["Jan Bereza"]["born"] is None and people["Jan Bereza"]["died"] is None
    assert jan.pk in {p["id"] for p in data["people"]}


def test_tree_page_has_view_switch_and_timeline(viewer, db):
    html = viewer.get(reverse("family:tree")).content.decode()
    assert 'data-tree-mode="drzewo"' in html and 'data-tree-mode="os"' in html
    assert "Oś czasu" in html
    assert 'class="tree-timeline"' in html and 'class="tree-bands"' in html
