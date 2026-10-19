import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from accounts.models import FamilyGroup, InviteCode
from panel.codes import suggest_code

User = get_user_model()

PANEL_URLS = [
    ("panel:dashboard", []),
    ("panel:user_list", []),
    ("panel:user_create", []),
    ("panel:code_list", []),
    ("panel:group_list", []),
]


@pytest.mark.parametrize(("name", "args"), PANEL_URLS)
def test_anonymous_redirected_to_login(client, db, name, args):
    response = client.get(reverse(name, args=args))
    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


@pytest.mark.parametrize(("name", "args"), PANEL_URLS)
def test_regular_user_gets_404(client, make_user, name, args):
    client.force_login(make_user("Karolina"))
    assert client.get(reverse(name, args=args)).status_code == 404


def test_regular_user_cannot_post_to_panel(client, make_user):
    client.force_login(make_user("Karolina"))
    response = client.post(reverse("panel:user_create"), {"nick": "Hacker", "password": "dlugie-haslo-123"})
    assert response.status_code == 404
    assert not User.objects.filter(username="Hacker").exists()


@pytest.mark.parametrize(("name", "args"), PANEL_URLS)
def test_master_sees_panel(master_client, name, args):
    assert master_client.get(reverse(name, args=args)).status_code == 200


def test_panel_link_only_for_master(client, make_user, master):
    client.force_login(make_user("Karolina"))
    assert "Panel" not in client.get(reverse("archive")).content.decode()
    client.force_login(master)
    assert "Panel" in client.get(reverse("archive")).content.decode()


def test_master_creates_user_with_groups(master_client, group):
    response = master_client.post(
        reverse("panel:user_create"),
        {"nick": "Babcia Ela", "password": "ogrodek-za-domem", "groups": [group.pk]},
    )
    user = User.objects.get(username="Babcia Ela")
    assert response.url == reverse("panel:user_detail", args=[user.pk])
    assert list(user.family_groups.all()) == [group]
    assert user.check_password("ogrodek-za-domem")
    assert not user.is_superuser


def test_master_sets_new_password_and_old_sessions_end(master_client, make_user):
    person = make_user("Karolina")
    other = Client()
    other.force_login(person)
    master_client.post(
        reverse("panel:user_detail", args=[person.pk]),
        {"action": "password", "new_password": "nowe-haslo-od-wojtka"},
    )
    person.refresh_from_db()
    assert person.check_password("nowe-haslo-od-wojtka")
    assert other.get(reverse("archive")).status_code == 302


def test_master_edits_groups(master_client, make_user, group):
    person = make_user("Karolina")
    master_client.post(
        reverse("panel:user_detail", args=[person.pk]),
        {"action": "edit", "display_name": "Karolina B.", "family_groups": [group.pk]},
    )
    person.refresh_from_db()
    assert person.display_name == "Karolina B."
    assert list(person.family_groups.all()) == [group]


def test_master_deactivates_and_reactivates(master_client, make_user):
    person = make_user("Karolina")
    url = reverse("panel:user_toggle_active", args=[person.pk])
    master_client.post(url)
    person.refresh_from_db()
    assert not person.is_active
    master_client.post(url)
    person.refresh_from_db()
    assert person.is_active


def test_toggle_requires_post(master_client, make_user):
    person = make_user("Karolina")
    assert master_client.get(reverse("panel:user_toggle_active", args=[person.pk])).status_code == 405


def test_master_cannot_deactivate_self(master_client, master):
    master_client.post(reverse("panel:user_toggle_active", args=[master.pk]))
    master.refresh_from_db()
    assert master.is_active


def test_master_deletes_user_after_confirmation(master_client, make_user):
    person = make_user("Karolina")
    url = reverse("panel:user_delete", args=[person.pk])
    assert master_client.get(url).status_code == 200
    assert User.objects.filter(pk=person.pk).exists()
    master_client.post(url)
    assert not User.objects.filter(pk=person.pk).exists()


def test_master_cannot_delete_self(master_client, master):
    master_client.post(reverse("panel:user_delete", args=[master.pk]))
    assert User.objects.filter(pk=master.pk).exists()


def test_master_creates_group_and_code(master_client):
    master_client.post(reverse("panel:group_list"), {"name": "Włodyka", "description": ""})
    group = FamilyGroup.objects.get(name="Włodyka")
    master_client.post(
        reverse("panel:code_list"),
        {"code": "Kasztan-Mlyn-21", "group": group.pk, "max_uses": "", "expires_at": ""},
    )
    code = InviteCode.objects.get()
    assert code.code == "kasztan-mlyn-21"
    assert code.group == group


@pytest.mark.parametrize("bad_code", ["krotki", "bereza"])
def test_weak_codes_rejected(master_client, group, bad_code):
    master_client.post(reverse("panel:code_list"), {"code": bad_code, "group": group.pk})
    assert not InviteCode.objects.exists()


def test_code_cannot_be_group_name(master_client):
    group = FamilyGroup.objects.create(name="Najbliższa rodzina")
    master_client.post(reverse("panel:code_list"), {"code": "najbliższa rodzina", "group": group.pk})
    assert not InviteCode.objects.exists()


def test_master_disables_code(master_client, invite):
    master_client.post(reverse("panel:code_toggle_active", args=[invite.pk]))
    invite.refresh_from_db()
    assert not invite.is_active


def test_suggested_code_is_long_enough():
    for _ in range(50):
        code = suggest_code()
        assert len(code) >= 10
        assert code == code.lower()


def test_comment_like_text_is_escaped_in_panel(master_client):
    FamilyGroup.objects.create(name="<script>alert(1)</script>")
    body = master_client.get(reverse("panel:group_list")).content.decode()
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body
