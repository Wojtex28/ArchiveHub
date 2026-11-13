"""ETAP 55: sprawdzanie drzewa i chowanie uwag „to się zgadza”."""

import json

import pytest
from django.urls import reverse

from albums.models import Person
from family import checks
from family.models import CheckDismissal, ParentChild, Partnership


def person(name, born=None, died=None, gender=""):
    p = Person.objects.create(name=name, key=f"{name}-{Person.objects.count()}", in_tree=True)
    Person.objects.filter(pk=p.pk).update(birth_year=born, death_year=died, gender=gender or p.gender)
    p.refresh_from_db()
    return p


def parent(child, *parents):
    for p in parents:
        ParentChild.objects.create(parent=p, child=child)


def couple(a, b):
    a, b = sorted((a, b), key=lambda p: p.pk)
    Partnership.objects.create(person1=a, person2=b)


def kinds():
    return sorted(issue.kind for issue in checks.find_issues())


def test_clean_family_has_no_issues(db):
    jan, anna = person("Jan Bereza", 1920, 1990), person("Anna Bereza", 1925)
    couple(jan, anna)
    parent(person("Piotr Bereza", 1950), jan, anna)
    assert kinds() == []


def test_dates_and_ages(db):
    jan, anna = person("Jan Bereza", 1920, 1940), person("Anna Bereza", 1945, 1930)
    parent(person("Piotr Bereza", 1950), jan, anna)
    found = kinds()
    assert "smierc" in found  # Anna zmarła przed urodzeniem
    assert "po-smierci" in found  # Piotr urodzony 10 lat po śmierci ojca
    assert found.count("wiek") == 1  # Anna miała 5 lat
    old = person("Józef Bereza", 1850)
    parent(person("Ewa Bereza", 1940), old)
    assert any(i.level == checks.WARNING and "90 lat" in i.text for i in checks.find_issues())


def test_structure_problems(db):
    grand, dad, mum, other = (person(n) for n in ("Józef A", "Jan A", "Anna A", "Ewa A"))
    parent(dad, grand)
    kid = person("Piotr A")
    parent(kid, dad, mum, grand)
    found = kinds()
    assert "rodzice" in found and "dziadek" in found
    sister = person("Maria A")
    parent(sister, dad, mum)
    couple(sister, other)
    couple(kid, sister)
    assert any(i.kind == "krewni" and "rodzeństwo" in i.text for i in checks.find_issues())


def test_duplicate_person(db):
    person("Jan Nowak", 1930)
    person("Jan Nowak", 1930)
    assert kinds() == ["dwa-razy"]


def test_dismissed_issue_hidden_until_data_changes(db, master_client):
    jan = person("Jan Bereza", 1920, 1910)
    issue = checks.issues_for()[0]
    data = master_client.get(reverse("family:data")).json()
    assert [i["key"] for i in data["issues"]] == [issue.key]
    url = reverse("family:api_check")
    body = json.dumps({"key": issue.key, "text": issue.text})
    assert master_client.post(url, body, content_type="application/json").status_code == 200
    assert checks.issues_for() == []
    assert issue.key in master_client.get(reverse("family:data")).json()["dismissed"]
    Person.objects.filter(pk=jan.pk).update(death_year=1905)
    assert len(checks.issues_for()) == 1  # inne dane, uwaga wraca
    Person.objects.filter(pk=jan.pk).update(death_year=1910)
    undo = json.dumps({"key": issue.key, "undo": True})
    master_client.post(url, undo, content_type="application/json")
    assert not CheckDismissal.objects.exists()


@pytest.mark.parametrize("access", ["view", "none"])
def test_only_editors_dismiss(client, make_user, access, db):
    client.force_login(make_user("Ola", tree_access=access))
    response = client.post(reverse("family:api_check"), "{}", content_type="application/json")
    assert response.status_code in (403, 404)


def test_panel_lists_issues(master_client, db):
    jan = person("Jan Bereza", 1920, 1910)
    page = master_client.get(reverse("panel:tree_history")).content.decode()
    assert "sprawdzenie" in page and f"osoba={jan.pk}" in page
