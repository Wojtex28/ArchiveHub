import pytest
from django.contrib.auth import get_user_model

from accounts.models import FamilyGroup, InviteCode

PASSWORD = "stare-zdjecia-1964"


@pytest.fixture
def make_user(db):
    def _make(username="jan", password=PASSWORD, **extra):
        return get_user_model().objects.create_user(username=username, password=password, **extra)

    return _make


@pytest.fixture
def master(make_user):
    return make_user("wojtek", is_superuser=True, is_staff=True)


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
