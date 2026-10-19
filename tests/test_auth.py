import pytest
from django.urls import reverse

from accounts.models import FailedAttempt

from .conftest import PASSWORD


def login(client, username, password, **extra):
    return client.post(reverse("login"), {"username": username, "password": password}, **extra)


def test_login_page_renders(client, db):
    response = client.get(reverse("login"))
    assert response.status_code == 200
    assert "Zaloguj" in response.content.decode()


def test_login_with_correct_password(client, make_user):
    make_user("Karolina")
    response = login(client, "Karolina", PASSWORD)
    assert response.status_code == 302
    assert response.url == reverse("archive")
    assert client.get(reverse("archive")).status_code == 200


def test_login_is_case_insensitive(client, make_user):
    make_user("Karolina")
    response = login(client, "  karolina ", PASSWORD)
    assert response.status_code == 302


def test_login_with_wrong_password(client, make_user):
    make_user("Karolina")
    response = login(client, "Karolina", "zle-haslo")
    assert response.status_code == 200
    assert "Nieprawidłowy nick lub hasło" in response.content.decode()
    assert "_auth_user_id" not in client.session


def test_unknown_user_gets_same_message(client, db):
    response = login(client, "nikt", "cokolwiek")
    assert "Nieprawidłowy nick lub hasło" in response.content.decode()


def test_inactive_user_cannot_log_in(client, make_user):
    make_user("Karolina", is_active=False)
    response = login(client, "Karolina", PASSWORD)
    assert response.status_code == 200
    assert "_auth_user_id" not in client.session


def test_deactivating_user_ends_existing_session(client, make_user):
    user = make_user("Karolina")
    client.force_login(user)
    user.is_active = False
    user.save()
    assert client.get(reverse("archive")).status_code == 302


def test_login_blocked_after_too_many_failures_for_user(client, make_user):
    make_user("Karolina")
    for i in range(8):
        # Różne adresy IP: limit na nick działa niezależnie od adresu.
        login(client, "Karolina", "zle", REMOTE_ADDR=f"10.0.0.{i}")
    response = login(client, "Karolina", PASSWORD, REMOTE_ADDR="10.0.1.1")
    assert response.status_code == 429
    assert "Za dużo nieudanych prób" in response.content.decode()
    assert "_auth_user_id" not in client.session


def test_login_blocked_after_too_many_failures_from_ip(client, make_user):
    make_user("Karolina")
    for i in range(20):
        login(client, f"ktos{i}", "zle")
    assert login(client, "Karolina", PASSWORD).status_code == 429


def test_client_ip_taken_from_cloudflare_header(client, make_user):
    make_user("Karolina")
    for i in range(20):
        login(client, f"ktos{i}", "zle", HTTP_CF_CONNECTING_IP="203.0.113.7")
    # Inny odwiedzający (inne IP od Cloudflare) nie jest blokowany.
    assert login(client, "Karolina", PASSWORD, HTTP_CF_CONNECTING_IP="198.51.100.9").status_code == 302


def test_successful_login_clears_user_failures(client, make_user):
    make_user("Karolina")
    for _ in range(3):
        login(client, "Karolina", "zle")
    login(client, "Karolina", PASSWORD)
    assert not FailedAttempt.objects.filter(scope="login:user").exists()


def test_login_redirects_to_safe_next_only(client, make_user):
    make_user("Karolina")
    response = client.post(
        reverse("login") + "?next=https://zly.example.com/",
        {"username": "Karolina", "password": PASSWORD, "next": "https://zly.example.com/"},
    )
    assert response.url == reverse("archive")


def test_login_requires_csrf_token(make_user):
    from django.test import Client

    make_user("Karolina")
    csrf_client = Client(enforce_csrf_checks=True)
    response = csrf_client.post(reverse("login"), {"username": "Karolina", "password": PASSWORD})
    assert response.status_code == 403


def test_logout_requires_post(client, make_user):
    client.force_login(make_user())
    assert client.get(reverse("logout")).status_code == 405
    response = client.post(reverse("logout"))
    assert response.status_code == 302
    assert client.get(reverse("archive")).status_code == 302


def test_user_can_change_own_password(client, make_user):
    user = make_user("Karolina")
    client.force_login(user)
    response = client.post(
        reverse("password_change"),
        {"old_password": PASSWORD, "new_password1": "nowe-haslo-babci", "new_password2": "nowe-haslo-babci"},
    )
    assert response.status_code == 302
    user.refresh_from_db()
    assert user.check_password("nowe-haslo-babci")
    # Sesja zostaje ważna po zmianie własnego hasła.
    assert client.get(reverse("archive")).status_code == 200


def test_password_change_requires_login(client, db):
    assert client.get(reverse("password_change")).status_code == 302


def test_session_lasts_a_year(client, make_user):
    make_user("Karolina")
    login(client, "Karolina", PASSWORD)
    assert client.session.get_expiry_age() >= 360 * 24 * 3600


@pytest.mark.parametrize("path", ["/zaplecze/login/", "/zaplecze/login/?next=/zaplecze/"])
def test_django_admin_login_goes_through_our_login(client, db, path):
    response = client.get(path)
    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))
