from django import forms
from django.contrib.auth import get_user_model, password_validation

from accounts.forms import validate_nick
from accounts.models import FamilyGroup, InviteCode
from albums.models import Album


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
        fields = ["name", "description", "sees_all_albums"]


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        files = [f for f in (data if isinstance(data, (list, tuple)) else [data]) if f]
        if not files:
            raise forms.ValidationError(self.error_messages["required"], code="required")
        return [super(MultipleImageField, self).clean(f, initial) for f in files]


class LoginPhotoUploadForm(forms.Form):
    photos = MultipleImageField(
        label="Zdjęcia",
        help_text=(
            "Możesz zaznaczyć kilka plików naraz. Zostaną zmniejszone, a dane z aparatu (np. GPS) usunięte."
        ),
    )
    photos.widget.attrs.update(accept="image/jpeg,image/png,image/webp")


class AlbumForm(forms.ModelForm):
    originals_url = forms.URLField(
        label="Link do oryginałów PNG (Google Drive)",
        required=False,
        max_length=500,
        assume_scheme="https",
        help_text=(
            "Opcjonalnie: link do folderu ze skanami PNG. Rodzina zobaczy go w galerii albumu. "
            "Kto może otworzyć folder, ustawiasz w Google Drive."
        ),
    )

    class Meta:
        model = Album
        fields = ["title", "description", "originals_url", "is_hidden"]
        labels = {
            "title": "Nazwa wyświetlana",
            "description": "Opis",
            "is_hidden": "Ukryty",
        }
        help_texts = {
            "title": "Tak album widzi rodzina, np. „Brązowy album ze złotą obwódką, 1997–2004”.",
            "description": "Kilka zdań pod nazwą albumu (opcjonalnie).",
            "is_hidden": "Ukryty album widzisz tylko Ty, niezależnie od uprawnień grup.",
        }
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}

    def clean_originals_url(self):
        url = self.cleaned_data["originals_url"].strip()
        if url and not url.lower().startswith("https://"):
            raise forms.ValidationError("Link musi zaczynać się od https://")
        return url
