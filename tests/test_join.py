from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from accounts.models import InviteCode

User = get_user_model()


def enter_code(client, code, **extra):
    return client.post(reverse("join"), {"code": code}, **extra)


def create_profile(client, nick="Karolina", password="wakacje-nad-morzem"):
    return client.post(reverse("join_profile"), {"nick": nick, "password1": password, "password2": password})


def test_full_join_flow(client, invite, group):
    response = enter_code(client, "  LIPA-bocian-64 ")
    assert response.status_code == 302
    assert response.url == reverse("join_profile")

    page = client.get(reverse("join_profile"))
    assert "Bereza" in page.content.decode()

    response = create_profile(client)
    assert response.status_code == 302
    assert response.url == reverse("archive")

    user = User.objects.get(username="Karolina")
    assert list(user.family_groups.all()) == [group]
    assert user.joined_with_code == invite
    assert user.display_name == "Karolina"
    assert user.check_password("wakacje-nad-morzem")
    assert client.get(reverse("archive")).status_code == 200

    # Po dołączeniu loguje się nickiem i własnym hasłem.
    client.post(reverse("logout"))
    login = client.post(reverse("login"), {"username": "karolina", "password": "wakacje-nad-morzem"})
    assert login.status_code == 302


def test_wrong_code_rejected(client, invite):
    response = enter_code(client, "bereza")
    assert response.status_code == 200
    assert "Ten kod nie działa" in response.content.decode()


@pytest.mark.parametrize(
    "change",
    [
        {"is_active": False},
        {"expires_at": timezone.now() - timedelta(minutes=1)},
        {"max_uses": 0},
    ],
)
def test_unusable_codes_rejected_with_same_message(client, invite, change):
    InviteCode.objects.filter(pk=invite.pk).update(**change)
    response = enter_code(client, invite.code)
    assert "Ten kod nie działa" in response.content.decode()


def test_code_with_max_uses_stops_after_limit(client, invite):
    invite.max_uses = 1
    invite.save()
    enter_code(client, invite.code)
    create_profile(client, "Karolina")
    client.post(reverse("logout"))
    response = enter_code(client, invite.code)
    assert "Ten kod nie działa" in response.content.decode()


def test_code_disabled_between_steps_blocks_profile(client, invite):
    enter_code(client, invite.code)
    invite.is_active = False
    invite.save()
    response = create_profile(client)
    assert response.status_code == 302
    assert response.url == reverse("join")
    assert not User.objects.filter(username="Karolina").exists()


def test_profile_step_requires_code_first(client, db):
    response = client.get(reverse("join_profile"))
    assert response.status_code == 302
    assert response.url == reverse("join")


def test_nick_must_be_unique_case_insensitive(client, invite, make_user):
    make_user("Karolina")
    enter_code(client, invite.code)
    response = create_profile(client, "KAROLINA")
    assert "Ten nick jest już zajęty" in response.content.decode()


@pytest.mark.parametrize("nick", ["K", "<script>", "a" * 31, "_karolina"])
def test_invalid_nicks_rejected(client, invite, nick):
    enter_code(client, invite.code)
    response = create_profile(client, nick)
    assert response.status_code == 200
    assert not User.objects.exists()


def test_nick_with_polish_letters_and_space_allowed(client, invite):
    enter_code(client, invite.code)
    create_profile(client, "Ciocia Basia Łęcka")
    assert User.objects.filter(username="Ciocia Basia Łęcka").exists()


def test_weak_password_rejected(client, invite):
    enter_code(client, invite.code)
    response = create_profile(client, "Karolina", "12345678")
    assert response.status_code == 200
    assert not User.objects.exists()


def test_password_confirmation_must_match(client, invite):
    enter_code(client, invite.code)
    response = client.post(
        reverse("join_profile"),
        {"nick": "Karolina", "password1": "wakacje-nad-morzem", "password2": "inne-haslo-xyz"},
    )
    assert "Hasła nie są takie same" in response.content.decode()


def test_code_guessing_is_rate_limited(client, invite):
    for i in range(10):
        enter_code(client, f"zgadywanie-{i}")
    response = enter_code(client, invite.code)
    assert response.status_code == 429


def test_logged_in_user_skips_join(client, make_user):
    client.force_login(make_user())
    assert client.get(reverse("join")).status_code == 302
