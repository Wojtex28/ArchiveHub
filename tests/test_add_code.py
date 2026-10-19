from django.urls import reverse

from accounts.models import FamilyGroup, InviteCode


def test_anonymous_redirected_to_login(client, db):
    response = client.get(reverse("add_code"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


def test_second_code_adds_group(client, make_user, group, invite):
    other = FamilyGroup.objects.create(name="Włodyka")
    InviteCode.objects.create(code="dab-nad-rzeka-71", group=other)
    user = make_user("Karolina")
    user.family_groups.add(group)
    client.force_login(user)

    response = client.post(reverse("add_code"), {"code": "  Dab-Nad-Rzeka-71 "})

    assert response.url == reverse("archive")
    assert set(user.family_groups.all()) == {group, other}


def test_code_of_own_group_changes_nothing(client, make_user, group, invite):
    user = make_user("Karolina")
    user.family_groups.add(group)
    client.force_login(user)

    response = client.post(reverse("add_code"), {"code": invite.code}, follow=True)

    assert "Już należysz" in response.content.decode()
    assert list(user.family_groups.all()) == [group]


def test_bad_or_disabled_code_rejected(client, make_user, invite):
    user = make_user("Karolina")
    client.force_login(user)
    invite.is_active = False
    invite.save()

    for code in ["nie-ma-takiego-kodu", invite.code]:
        response = client.post(reverse("add_code"), {"code": code})
        assert response.status_code == 200
        assert "Ten kod nie działa" in response.content.decode()
    assert not user.family_groups.exists()


def test_add_code_is_rate_limited(client, make_user, invite):
    user = make_user("Karolina")
    client.force_login(user)
    for _ in range(10):
        client.post(reverse("add_code"), {"code": "zly-kod-zly-kod"})

    response = client.post(reverse("add_code"), {"code": invite.code})

    assert response.status_code == 429
    assert not user.family_groups.exists()
