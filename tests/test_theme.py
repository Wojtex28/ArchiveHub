"""Tryb nocny (ETAP 40)."""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

CSS = Path(settings.BASE_DIR, "static", "css", "site.css").read_text()


@pytest.mark.django_db
def test_without_choice_page_follows_system(client):
    body = client.get(reverse("landing")).content.decode()
    assert "data-theme" not in body.split("<head>")[0]
    assert "js/theme.js" in body
    assert "prefers-color-scheme: dark" in CSS


@pytest.mark.django_db
def test_cookie_sets_theme_on_html(client):
    client.cookies["motyw"] = "ciemny"
    assert '<html lang="pl" data-theme="dark">' in client.get(reverse("landing")).content.decode()
    client.cookies["motyw"] = "jasny"
    assert '<html lang="pl" data-theme="light">' in client.get(reverse("landing")).content.decode()


@pytest.mark.django_db
def test_unknown_cookie_is_ignored(client):
    client.cookies["motyw"] = '"><script>'
    body = client.get(reverse("landing")).content.decode()
    assert '<html lang="pl">' in body


@pytest.mark.django_db
def test_toggle_in_menu_shows_opposite_mode(client, make_user):
    make_user("karolina")
    client.login(username="karolina", password="stare-zdjecia-1964")
    body = client.get(reverse("archive")).content.decode()
    assert 'name="motyw" value="ciemny"' in body
    assert "Tryb nocny" in body
    client.cookies["motyw"] = "ciemny"
    body = client.get(reverse("archive")).content.decode()
    assert 'name="motyw" value="jasny"' in body
    assert "Tryb dzienny" in body


@pytest.mark.django_db
def test_form_without_js_sets_cookie_and_returns(client):
    response = client.post(reverse("set_theme"), {"motyw": "ciemny", "next": "/szukaj/?q=Jan"})
    assert response.status_code == 302
    assert response.url == "/szukaj/?q=Jan"
    assert response.cookies["motyw"].value == "ciemny"
    assert response.cookies["motyw"]["samesite"] == "Lax"


@pytest.mark.django_db
def test_form_rejects_foreign_redirect_and_bad_value(client):
    response = client.post(reverse("set_theme"), {"motyw": "zielony", "next": "https://zla.example/"})
    assert response.url == reverse("archive")
    assert response.cookies["motyw"].value == ""  # bez wyboru: wraca ustawienie systemu


def test_theme_requires_post(client):
    assert client.get(reverse("set_theme")).status_code == 405


def test_dark_palette_covers_every_light_variable():
    root = re.search(r":root \{(.*?)\n\}", CSS, re.S).group(1)
    dark = re.search(r':root\[data-theme="dark"\] \{(.*?)\n\}', CSS, re.S).group(1)
    system = re.search(r':root:not\(\[data-theme="light"\]\) \{(.*?)\n  \}', CSS, re.S).group(1)
    names = lambda block: set(re.findall(r"(--[\w-]+):", block))  # noqa: E731
    colors = names(root) - {"--serif", "--sans"}
    assert colors <= names(dark)
    assert names(dark) == names(system)
