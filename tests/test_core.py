import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_landing_page_renders(client):
    response = client.get(reverse("landing"))
    assert response.status_code == 200
    body = response.content.decode()
    assert "Przejdź do archiwum" in body
    assert 'lang="pl"' in body


@pytest.mark.django_db
def test_archive_requires_login(client):
    response = client.get(reverse("archive"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


@pytest.mark.django_db
def test_healthz_reports_ok(client):
    response = client.get(reverse("healthz"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_robots_txt_blocks_everything(client):
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert "Disallow: /" in response.content.decode()


@pytest.mark.django_db
def test_security_headers_present(client):
    response = client.get(reverse("landing"))
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "unsafe-inline" not in csp
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "same-origin"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert "camera=()" in response.headers["Permissions-Policy"]


def test_unknown_page_returns_404(client):
    assert client.get("/nie-ma-takiej-strony/").status_code == 404


def test_landing_rejects_post(client):
    assert client.post(reverse("landing")).status_code == 405
