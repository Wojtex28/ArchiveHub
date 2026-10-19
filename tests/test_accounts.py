import pytest
from django.contrib.auth import get_user_model


def test_custom_user_model_is_active():
    assert get_user_model()._meta.label == "accounts.User"


@pytest.mark.django_db
def test_passwords_are_hashed_with_argon2():
    user = get_user_model().objects.create_user("jan", password="dluga-fraza-testowa")
    assert user.password.startswith("argon2")
    assert user.check_password("dluga-fraza-testowa")


@pytest.mark.django_db
def test_display_name_used_as_label():
    user = get_user_model().objects.create_user("karolina", display_name="Karolina")
    assert str(user) == "Karolina"
