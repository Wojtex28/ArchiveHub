from django import forms
from django.contrib.auth import get_user_model, password_validation

from accounts.forms import validate_nick
from accounts.models import FamilyGroup, InviteCode


class GroupsField(forms.ModelMultipleChoiceField):
    widget = forms.CheckboxSelectMultiple

    def __init__(self, **kwargs):
        super().__init__(queryset=FamilyGroup.objects.all(), required=False, label="Grupy", **kwargs)


def _validate_new_password(form, field, user):
    password = form.cleaned_data.get(field)
    if password:
        try:
            password_validation.validate_password(password, user)
        except forms.ValidationError as exc:
            form.add_error(field, exc)


class UserCreateForm(forms.Form):
    nick = forms.CharField(label="Nick (login)", max_length=30)
    password = forms.CharField(label="Hasło", strip=False, widget=forms.PasswordInput(render_value=False))
    groups = GroupsField()

    def clean_nick(self):
        return validate_nick(self.cleaned_data["nick"])

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("nick"):
            _validate_new_password(self, "password", get_user_model()(username=cleaned["nick"]))
        return cleaned


class UserEditForm(forms.ModelForm):
    family_groups = GroupsField()

    class Meta:
        model = get_user_model()
        fields = ["display_name", "family_groups"]
        labels = {"display_name": "Imię wyświetlane"}


class SetPasswordForm(forms.Form):
    new_password = forms.CharField(label="Nowe hasło", strip=False, widget=forms.PasswordInput)

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        _validate_new_password(self, "new_password", self.user)
        return cleaned


class InviteCodeForm(forms.ModelForm):
    class Meta:
        model = InviteCode
        fields = ["code", "group", "max_uses", "expires_at", "note"]
        widgets = {
            "expires_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }
        help_texts = {
            "code": "Min. 10 znaków. Nie używaj samego nazwiska, bo łatwo je zgadnąć.",
            "max_uses": "Puste = bez limitu.",
            "expires_at": "Puste = bez daty ważności.",
        }

    def clean_code(self):
        code = InviteCode.normalize(self.cleaned_data["code"])
        if len(code) < 10:
            raise forms.ValidationError("Kod musi mieć co najmniej 10 znaków.")
        if InviteCode.objects.filter(code=code).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Taki kod już istnieje.")
        group_names = {g.name.lower() for g in FamilyGroup.objects.all()}
        if code in group_names:
            raise forms.ValidationError("Kod nie może być samą nazwą grupy.")
        return code


class FamilyGroupForm(forms.ModelForm):
    class Meta:
        model = FamilyGroup
        fields = ["name", "description"]
