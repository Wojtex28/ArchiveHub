"""Formularze panelu zdjęcia: komentarz i opis."""

import re

from django import forms

from .dates import DateError, parse_date
from .models import Comment, NamedModel, Photo, name_key, namesake_keys, person_token, split_person_token

MAX_NAMES = 30


class CommentForm(forms.Form):
    text = forms.CharField(
        label="Twój komentarz",
        max_length=Comment.MAX_LENGTH,
        strip=True,
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "Kto jest na zdjęciu? Gdzie i kiedy je zrobiono?"}
        ),
    )


def split_names(value):
    """„Jan, babcia Helena; Jan” → ["Jan", "babcia Helena"]: przecinek albo średnik, bez powtórzeń."""
    names, seen = [], set()
    for part in re.split(r"[,;\n]", value or ""):
        name = " ".join(part.split())
        if name and name_key(name) not in seen:
            seen.add(name_key(name))
            names.append(name)
    return names


class NamesField(forms.CharField):
    def clean(self, value):
        names = split_names(super().clean(value))
        if len(names) > MAX_NAMES:
            raise forms.ValidationError(f"Najwyżej {MAX_NAMES} pozycji.")
        for name in names:
            if len(split_person_token(name)[0]) > NamedModel.MAX_LENGTH:
                raise forms.ValidationError(f"„{name[:30]}…” jest za długie (najwyżej 100 znaków).")
        return names


class MetadataForm(forms.Form):
    """Opis zdjęcia. ``part`` zostawia tylko pola jednej części panelu: „opis” albo „osoby”."""

    PARTS = {
        "opis": ("date", "place", "tags", "description"),
        "osoby": ("people",),
    }

    date = forms.CharField(
        label="Kiedy",
        required=False,
        max_length=60,
        help_text="Np. 1965, ok. 1965, lata 60., lato 1965, 12.06.1965. Wystarczy przybliżenie.",
        widget=forms.TextInput(attrs={"placeholder": "np. ok. 1965", "autocomplete": "off"}),
    )
    place = forms.CharField(
        label="Gdzie",
        required=False,
        max_length=Photo._meta.get_field("place").max_length,
        widget=forms.TextInput(
            attrs={
                "placeholder": "np. Berezów, ogród dziadków",
                "list": "miejsca-podpowiedzi",
                "autocomplete": "off",
            }
        ),
    )
    people = NamesField(
        label="Kto jest na zdjęciu",
        required=False,
        max_length=2000,
        help_text="Wpisz kilka liter i wybierz osobę z listy. Osoby z drzewa są na górze.",
        widget=forms.TextInput(
            attrs={
                "list": "osoby-podpowiedzi",
                "autocomplete": "off",
                "data-list-input": "",
                # Bez JavaScriptu zostaje pole tekstowe z nazwami po przecinku.
                "data-people-picker": "osoby-wybor",
            }
        ),
    )
    tags = NamesField(
        label="Tagi",
        required=False,
        max_length=1000,
        help_text="Np. wesele, komunia, wakacje. Oddziel przecinkami.",
        widget=forms.TextInput(
            attrs={"list": "tagi-podpowiedzi", "autocomplete": "off", "data-list-input": ""}
        ),
    )
    description = forms.CharField(
        label="Opis",
        required=False,
        max_length=Photo._meta.get_field("description").max_length,
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "Co się dzieje na zdjęciu, skąd jest, ciekawostki"}
        ),
    )

    def __init__(self, *args, part=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.part = part
        if part:
            for name in list(self.fields):
                if name not in self.PARTS[part]:
                    del self.fields[name]

    def clean_date(self):
        try:
            return parse_date(self.cleaned_data["date"])
        except DateError as error:
            raise forms.ValidationError(str(error)) from None

    @classmethod
    def for_photo(cls, photo, part=None):
        return cls(
            part=part,
            initial={
                "date": photo.date_text,
                "place": photo.place,
                "people": ", ".join(person_token(p, namesake_keys()) for p in photo.people.all()),
                "tags": ", ".join(tag.name for tag in photo.tags.all()),
                "description": photo.description,
            },
        )
