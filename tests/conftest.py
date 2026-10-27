import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts import totp
from accounts.models import FamilyGroup, InviteCode

PASSWORD = "stare-zdjecia-1964"


@pytest.fixture
def make_user(db):
    def _make(username="jan", password=PASSWORD, **extra):
        return get_user_model().objects.create_user(username=username, password=password, **extra)

    return _make


@pytest.fixture
def master(make_user):
    # Konto master w produkcji musi mieć logowanie dwuskładnikowe, więc w testach też je ma.
    return make_user(
        "wojtek",
        is_superuser=True,
        is_staff=True,
        totp_secret=totp.new_secret(),
        totp_enabled_at=timezone.now(),
    )


@pytest.fixture
def master_client(client, master):
    client.force_login(master)
    return client


@pytest.fixture
def group(db):
    return FamilyGroup.objects.create(name="Bereza")


@pytest.fixture
def invite(group):
    return InviteCode.objects.create(code="lipa-bocian-64", group=group)
