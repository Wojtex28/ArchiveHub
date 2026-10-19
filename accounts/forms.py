import re

from django import forms
from django.contrib.auth import get_user_model, password_validation

NICK_RE = re.compile(r"^[^\W_](?:[\w .-]*[^\W_])?$")


def validate_nick(value):
    value = " ".join(value.split())
    if not 2 <= len(value) <= 30:
        raise forms.ValidationError("Nick musi mieć od 2 do 30 znaków.")
    if not NICK_RE.match(value):
        raise forms.ValidationError("Nick może zawierać litery, cyfry, spacje, kropki i myślniki.")
    if get_user_model().objects.filter(username__iexact=value).exists():
        raise forms.ValidationError("Ten nick jest już zajęty. Wybierz inny.")
    return value


class LoginForm(forms.Form):
    username = forms.CharField(label="Nick", max_length=150)
    password = forms.CharField(label="Hasło", strip=False, widget=forms.PasswordInput)

    username.widget.attrs.update(autocomplete="username", autocapitalize="none", autofocus=True)
    password.widget.attrs.update(autocomplete="current-password")


class JoinCodeForm(forms.Form):
    code = forms.CharField(label="Kod rodzinny", max_length=60)
    code.widget.attrs.update(autocomplete="off", autocapitalize="none", autofocus=True)


class JoinProfileForm(forms.Form):
    nick = forms.CharField(
        label="Twój nick",
        max_length=30,
        help_text="Tym nickiem będziesz się logować i podpisywać komentarze, np. „Karolina”.",
    )
    password1 = forms.CharField(label="Hasło", strip=False, widget=forms.PasswordInput)
    password2 = forms.CharField(label="Powtórz hasło", strip=False, widget=forms.PasswordInput)

    nick.widget.attrs.update(autocomplete="username", autofocus=True)
    password1.widget.attrs.update(autocomplete="new-password")
    password2.widget.attrs.update(autocomplete="new-password")

    def clean_nick(self):
        return validate_nick(self.cleaned_data["nick"])

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Hasła nie są takie same.")
        if p1 and cleaned.get("nick"):
            user = get_user_model()(username=cleaned["nick"], display_name=cleaned["nick"])
            try:
                password_validation.validate_password(p1, user)
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned
