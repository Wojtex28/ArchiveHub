from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class CaseInsensitiveModelBackend(ModelBackend):
    """Logowanie bez rozróżniania wielkości liter w nicku („karolina” = „Karolina”)."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        user_model = get_user_model()
        try:
            user = user_model.objects.get(username__iexact=username.strip())
        except user_model.DoesNotExist:
            # Haszujemy hasło mimo wszystko, żeby czas odpowiedzi nie zdradzał, czy konto istnieje.
            user_model().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
