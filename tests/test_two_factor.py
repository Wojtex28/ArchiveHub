import time

import pytest
from django.contrib.auth.base_user import AbstractBaseUser
from django.core.management import call_command
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts import totp
from accounts.models import FailedAttempt, RecoveryCode
from tests.conftest import PASSWORD

LOGIN = reverse("login")
SECOND = reverse("login_two_factor")
SETUP = reverse("two_factor")


def code_for(user, steps=0):
    return totp.code_at(user.totp_secret, totp.current_counter() + steps)


def wrong_code(secret):
    good = {totp.code_at(secret, totp.current_counter() + step) for step in (-1, 0, 1)}
    return next(code for code in ("000000", "111111", "222222", "333333") if code not in good)


def password_step(client, user, next_url=""):
    data = {"username": user.username, "password": PASSWORD}
    if next_url:
        data["next"] = next_url
    return client.post(LOGIN, data)


# --- TOTP -------------------------------------------------------------------


def test_totp_matches_rfc6238_vector():
    # RFC 6238, dodatek B: sekret "12345678901234567890", czas 59 s -> 94287082 (8 cyfr).
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert totp.code_at(secret, 59 // 30) == "287082"


def test_totp_accepts_neighbour_step_but_not_replay():
    secret = totp.new_secret()
    now = 1_700_000_000
    counter = totp.current_counter(now)
    assert totp.verify(secret, totp.code_at(secret, counter - 1), 0, now) == counter - 1
    assert totp.verify(secret, totp.code_at(secret, counter + 2), 0, now) is None
    assert totp.verify(secret, totp.code_at(secret, counter), counter, now) is None
    assert totp.verify(secret, "12 34", 0, now) is None


def test_provisioning_uri_and_qr():
    uri = totp.provisioning_uri("ABCDEFGH", "wojtek", "Skany Włodyka/Bereza")
    assert uri.startswith("otpauth://totp/Skany%20W%C5%82odyka%2FBereza%3Awojtek?secret=ABCDEFGH")
    assert totp.qr_data_uri(uri).startswith("data:image/svg+xml")


# --- Logowanie --------------------------------------------------------------


def test_master_login_asks_for_code(client, master):
    response = password_step(client, master, next_url="/panel/")
    assert response.status_code == 302
    assert response.url == SECOND + "?next=%2Fpanel%2F"
    # Samo hasło jeszcze nie loguje.
    assert "_auth_user_id" not in client.session

    response = client.post(SECOND, {"code": code_for(master), "next": "/panel/"})
    assert response.status_code == 302
    assert response.url == "/panel/"
    assert client.session["_auth_user_id"] == str(master.pk)
    assert client.get("/panel/").status_code == 200


def test_master_session_is_shorter(client, master):
    password_step(client, master)
    client.post(SECOND, {"code": code_for(master)})
    assert client.session.get_expiry_age() == 30 * 24 * 60 * 60


def test_wrong_code_is_refused_and_counted(client, master):
    password_step(client, master)
    response = client.post(SECOND, {"code": wrong_code(master.totp_secret)})
    assert response.status_code == 200
    assert "Ten kod nie pasuje" in response.content.decode()
    assert "_auth_user_id" not in client.session
    assert FailedAttempt.objects.filter(scope="totp:user", key=str(master.pk)).count() == 1


def test_code_cannot_be_used_twice(client, master):
    code = code_for(master)
    password_step(client, master)
    client.post(SECOND, {"code": code})
    client.post(reverse("logout"))

    password_step(client, master)
    response = client.post(SECOND, {"code": code})
    assert response.status_code == 200
    assert "_auth_user_id" not in client.session


def test_too_many_wrong_codes_block(client, master):
    password_step(client, master)
    for _ in range(5):
        client.post(SECOND, {"code": "abcdef"})
    response = client.post(SECOND, {"code": code_for(master)})
    assert response.status_code == 429
    assert "_auth_user_id" not in client.session


def test_pending_login_expires(client, master):
    password_step(client, master)
    session = client.session
    session["two_factor_pending"]["at"] = time.time() - 600
    session.save()
    response = client.post(SECOND, {"code": code_for(master)})
    assert response.status_code == 302
    assert response.url == LOGIN


def test_second_step_without_password_redirects(client, master):
    response = client.get(SECOND)
    assert response.status_code == 302
    assert response.url == LOGIN


def test_recovery_code_works_once(client, master):
    RecoveryCode.objects.create(user=master, code_hash=totp.hash_recovery_code("abcde-fghjk"))
    password_step(client, master)
    response = client.post(SECOND, {"code": "ABCDE FGHJK"})
    assert response.status_code == 302
    assert client.session["_auth_user_id"] == str(master.pk)
    client.post(reverse("logout"))

    password_step(client, master)
    client.post(SECOND, {"code": "abcde-fghjk"})
    assert "_auth_user_id" not in client.session


def test_family_member_without_2fa_logs_in_with_password(client, make_user):
    user = make_user("karolina")
    response = password_step(client, user)
    assert response.status_code == 302
    assert response.url == reverse("archive")
    assert client.session["_auth_user_id"] == str(user.pk)


# --- Wymóg dla konta master -------------------------------------------------


@pytest.fixture
def bare_master(make_user):
    return make_user("admin", is_superuser=True, is_staff=True)


def test_master_without_2fa_is_sent_to_setup(client, bare_master):
    response = password_step(client, bare_master)
    assert response.url == SETUP
    response = client.get(reverse("panel:dashboard"))
    assert response.status_code == 302
    assert response.url == SETUP


def test_django_admin_also_requires_2fa(client, bare_master, master):
    client.force_login(bare_master)
    response = client.get("/zaplecze/")
    assert response.status_code == 302
    assert client.get(response.url, follow=True).redirect_chain[-1][0] == SETUP

    client.force_login(master)
    assert client.get("/zaplecze/").status_code == 200


@override_settings(ARCHIVEHUB_MASTER_2FA=False)
def test_requirement_can_be_switched_off(client, bare_master):
    client.force_login(bare_master)
    assert client.get(reverse("panel:dashboard")).status_code == 200


# --- Włączanie i wyłączanie -------------------------------------------------


def test_enable_two_factor(client, bare_master):
    client.force_login(bare_master)
    response = client.get(SETUP)
    content = response.content.decode()
    assert "data:image/svg+xml" in content
    secret = client.session["two_factor_setup_secret"]

    response = client.post(SETUP, {"action": "enable", "code": wrong_code(secret)})
    assert "Ten kod nie pasuje" in response.content.decode()
    bare_master.refresh_from_db()
    assert not bare_master.has_two_factor

    response = client.post(SETUP, {"action": "enable", "code": totp.code_at(secret, totp.current_counter())})
    assert response.status_code == 200
    assert response.templates[0].name == "accounts/recovery_codes.html"
    codes = response.context["codes"]
    assert len(codes) == 10
    bare_master.refresh_from_db()
    assert bare_master.has_two_factor
    assert bare_master.totp_secret == secret
    assert RecoveryCode.objects.filter(user=bare_master, used_at=None).count() == 10
    # Ta sesja zostaje zalogowana, panel jest już dostępny.
    assert client.get(reverse("panel:dashboard")).status_code == 200


def test_enabling_logs_out_other_devices(client, bare_master):
    other = Client()
    other.force_login(bare_master)
    client.force_login(bare_master)
    client.get(SETUP)
    secret = client.session["two_factor_setup_secret"]
    client.post(SETUP, {"action": "enable", "code": totp.code_at(secret, totp.current_counter())})
    assert client.get(reverse("archive")).status_code == 200
    assert other.get(reverse("archive")).status_code == 302


def test_existing_sessions_survive_upgrade(client, make_user):
    # Bez sekretu skrót sesji jest taki sam jak w Django, więc aktualizacja nikogo nie wylogowuje.
    user = make_user("babcia")
    assert user.get_session_auth_hash() == AbstractBaseUser._get_session_auth_hash(user)


def test_new_recovery_codes_replace_old(master_client, master):
    RecoveryCode.objects.create(user=master, code_hash=totp.hash_recovery_code("old11-old22"))
    response = master_client.post(SETUP, {"action": "codes", "codes-code": code_for(master)})
    assert response.templates[0].name == "accounts/recovery_codes.html"
    assert not RecoveryCode.objects.filter(code_hash=totp.hash_recovery_code("old11-old22")).exists()
    assert RecoveryCode.objects.filter(user=master).count() == 10


def test_disable_needs_password_and_code(master_client, master):
    response = master_client.post(
        SETUP, {"action": "disable", "disable-password": "zle", "disable-code": code_for(master)}
    )
    assert "To nie jest Twoje hasło" in response.content.decode()
    master.refresh_from_db()
    assert master.has_two_factor

    response = master_client.post(
        SETUP, {"action": "disable", "disable-password": PASSWORD, "disable-code": code_for(master)}
    )
    assert response.status_code == 302
    master.refresh_from_db()
    assert not master.has_two_factor
    # Master bez 2FA wraca do ekranu włączania zamiast do panelu.
    assert master_client.get(reverse("panel:dashboard")).url == SETUP


def test_reset_command(master):
    RecoveryCode.objects.create(user=master, code_hash="x" * 64)
    call_command("wylacz_2fa", "WOJTEK")
    master.refresh_from_db()
    assert not master.has_two_factor
    assert not master.recovery_codes.exists()


def test_setup_page_needs_login(client):
    response = client.get(SETUP)
    assert response.status_code == 302
    assert response.url.startswith(LOGIN)


def test_enabled_at_shown(master_client, master):
    master.totp_enabled_at = timezone.now()
    master.save()
    response = master_client.get(SETUP)
    assert "Niewykorzystane kody zapasowe: 0 z 10" in response.content.decode()
