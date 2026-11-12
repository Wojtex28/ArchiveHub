from django import forms

from albums.dates import DateError, parse_date
from albums.models import NamedModel, Person, Photo

from .tree import RELATION_KINDS


def _sort_year(date):
    """Rok do sortowania i układania pokoleń: środek zakresu („ok. 1920” → 1920, „lata 20.” → 1924)."""
    if not date:
        return None
    return (date.year_from + date.year_to) // 2


class PersonForm(forms.ModelForm):
    portrait = forms.ModelChoiceField(
        queryset=None, required=False, label="Portret", widget=forms.RadioSelect, empty_label="bez portretu"
    )

    class Meta:
        model = Person
        fields = [
            "name",
            "maiden_name",
            "birth_date",
            "birth_place",
            "deceased",
            "death_date",
            "death_place",
            "bio",
            "portrait",
        ]
        labels = {"name": "Imię i nazwisko", "deceased": "Nie żyje"}
        help_texts = {
            "birth_date": "Np. 12.06.1921, czerwiec 1921, 1921, ok. 1920 albo lata 20.",
            "deceased": "Na kafelku w drzewie pojawi się †. Włącz, żeby wpisać datę i miejsce śmierci.",
            "death_date": "Jak data urodzenia. Puste, jeśli osoba żyje albo nie wiadomo.",
            "bio": "Kim była, gdzie mieszkała, czym się zajmowała, rodzinne historie.",
        }
        widgets = {"bio": forms.Textarea(attrs={"rows": 6})}

    def __init__(self, *args, portraits=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._birth = self._death = None
        self.fields["portrait"].queryset = portraits if portraits is not None else Photo.objects.none()
        self.fields["portrait"].label_from_instance = lambda photo: photo.pk
        for name in ("birth_date", "death_date"):
            self.fields[name].widget.attrs["placeholder"] = "np. ok. 1920"

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if not name or len(name) > NamedModel.MAX_LENGTH:
            raise forms.ValidationError("Wpisz imię i nazwisko (najwyżej 100 znaków).")
        # Imiennicy są dozwoleni (dziadek i wnuk o tym samym imieniu), widok tylko o nich przypomina.
        return name

    def _clean_date(self, field):
        try:
            return parse_date(self.cleaned_data[field])
        except DateError as exc:
            raise forms.ValidationError(str(exc)) from None

    def clean_birth_date(self):
        self._birth = self._clean_date("birth_date")
        return self._birth.text

    def clean_death_date(self):
        self._death = self._clean_date("death_date")
        return self._death.text

    def clean(self):
        data = super().clean()
        # Data śmierci przesądza sprawę, nawet jeśli ktoś zapomniał o przełączniku.
        if data.get("death_date") or data.get("death_place"):
            data["deceased"] = True
        return data

    def save(self, commit=True):
        person = super().save(commit=False)
        person.birth_year = _sort_year(self._birth)
        person.death_year = _sort_year(self._death)
        if commit:
            person.save()
        return person


class RelationForm(forms.Form):
    kind = forms.ChoiceField(label="Kto to jest dla tej osoby", choices=list(RELATION_KINDS.items()))
    name = forms.CharField(
        label="Imię i nazwisko",
        max_length=NamedModel.MAX_LENGTH,
        help_text="Wpisz nową osobę albo wybierz z podpowiedzi kogoś, kto już jest w archiwum.",
        widget=forms.TextInput(attrs={"list": "osoby-podpowiedzi", "autocomplete": "off"}),
    )

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if not name:
            raise forms.ValidationError("Wpisz imię i nazwisko.")
        return name


class NewPersonForm(forms.Form):
    name = forms.CharField(
        label="Imię i nazwisko",
        max_length=NamedModel.MAX_LENGTH,
        help_text="Jeśli ta osoba jest już oznaczona na zdjęciach, wybierz ją z podpowiedzi.",
        widget=forms.TextInput(attrs={"list": "osoby-podpowiedzi", "autocomplete": "off"}),
    )

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if not name:
            raise forms.ValidationError("Wpisz imię i nazwisko.")
        return name
