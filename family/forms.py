from django import forms

from albums.dates import DateError, parse_date
from albums.models import NamedModel, Person, Photo

from .models import LifeEvent
from .tree import RELATION_KINDS


def _sort_year(date):
    """Rok do sortowania i układania pokoleń: środek zakresu („ok. 1920” → 1920, „lata 20.” → 1924)."""
    if not date:
        return None
    return (date.year_from + date.year_to) // 2


# Kadr portretu: (najmniej, najwięcej, domyślnie).
CROP_LIMITS = {"portrait_x": (0, 100, 50), "portrait_y": (0, 100, 50), "portrait_zoom": (1, 4, 1)}


class PersonForm(forms.ModelForm):
    portrait = forms.ModelChoiceField(
        queryset=None, required=False, label="Portret", widget=forms.RadioSelect, empty_label="bez portretu"
    )

    class Meta:
        model = Person
        fields = [
            "name",
            "maiden_name",
            "gender",
            "birth_date",
            "birth_place",
            "deceased",
            "death_date",
            "death_place",
            "burial_place",
            "bio",
            "portrait",
            "portrait_x",
            "portrait_y",
            "portrait_zoom",
        ]
        labels = {"name": "Imię i nazwisko", "deceased": "Nie żyje"}
        help_texts = {
            "gender": "Podpowiadana z imienia. Od niej zależą słowa w chronologii (córka/syn, matka/ojciec).",
            "birth_date": "Np. 12.06.1921, czerwiec 1921, 1921, ok. 1920 albo lata 20.",
            "deceased": "Na kafelku w drzewie pojawi się †. Włącz, żeby wpisać datę i miejsce śmierci.",
            "death_date": "Jak data urodzenia. Puste, jeśli osoba żyje albo nie wiadomo.",
            "burial_place": "Cmentarz, kwatera, numer grobu.",
            "bio": "Kim była, gdzie mieszkała, czym się zajmowała, rodzinne historie.",
        }
        widgets = {
            "bio": forms.Textarea(attrs={"rows": 6}),
            "portrait_x": forms.HiddenInput,
            "portrait_y": forms.HiddenInput,
            "portrait_zoom": forms.HiddenInput,
        }

    def __init__(self, *args, portraits=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._birth = self._death = None
        self.fields["portrait"].queryset = portraits if portraits is not None else Photo.objects.none()
        self.fields["portrait"].label_from_instance = lambda photo: photo.pk
        for name in ("birth_date", "death_date"):
            self.fields[name].widget.attrs["placeholder"] = "np. ok. 1920"
        for name in CROP_LIMITS:
            self.fields[name].required = False

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
        if data.get("death_date") or data.get("death_place") or data.get("burial_place"):
            data["deceased"] = True
        # Kadr portretu: brak wartości (stary formularz, nowe zdjęcie bez ustawiania) to środek zdjęcia.
        changed = data.get("portrait") != self.instance.portrait
        for name, (low, high, default) in CROP_LIMITS.items():
            value = data.get(name)
            if value is None or value != value:
                value = default if changed else getattr(self.instance, name)
            data[name] = min(high, max(low, value))
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


PLACEMENT = [("1", "Na osi czasu, według daty"), ("0", "Pod osią czasu, jako informacja")]


class LifeEventForm(forms.ModelForm):
    """Zdarzenie z życia wpisywane ręcznie (ETAP 46)."""

    # ETAP 54: gdzie pokazać na karcie osoby; adres domu nie musi być punktem na osi.
    on_timeline = forms.TypedChoiceField(
        label="Gdzie pokazać",
        choices=PLACEMENT,
        coerce=lambda value: value == "1",
        widget=forms.RadioSelect,
        required=False,
        empty_value=None,
    )

    class Meta:
        model = LifeEvent
        fields = ["kind", "title", "date", "until", "place", "note", "on_timeline", "photo"]
        labels = {"kind": "Co to za zdarzenie", "title": "Tytuł (opcjonalnie)", "date": "Kiedy albo od kiedy"}
        help_texts = {
            "title": "Np. „Kupno domu w Kraczkowej”. Bez tytułu zostanie nazwa rodzaju.",
            "date": "Np. 1950, czerwiec 1950, ok. 1950 albo lata 50.",
            "until": "Tylko gdy coś trwało dłużej, np. mieszkanie albo praca.",
        }
        widgets = {"note": forms.Textarea(attrs={"rows": 3}), "photo": forms.RadioSelect}

    def __init__(self, *args, photos=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Zdjęcie tylko spośród zdjęć tej osoby, które widzi konto (ETAP 47).
        self.fields["photo"].queryset = photos if photos is not None else Photo.objects.none()
        self.fields["photo"].required = False
        self.fields["photo"].empty_label = "bez zdjęcia"
        self.fields["photo"].label = "Zdjęcie z archiwum (opcjonalnie)"
        # Bez pustej pozycji na liście: najczęściej dopisuje się, gdzie ktoś mieszkał.
        self.fields["kind"].choices = LifeEvent.KINDS
        self.fields["kind"].initial = LifeEvent.KINDS[0][0]
        # Domyślne miejsce zależy od rodzaju; skrypt przestawia je przy zmianie rodzaju (life-events.js).
        self.fields["kind"].widget.attrs["data-event-kind"] = " ".join(LifeEvent.OFF_TIMELINE)
        kind = self.instance.kind if self.instance.pk else LifeEvent.KINDS[0][0]
        on = self.instance.on_timeline if self.instance.pk else kind not in LifeEvent.OFF_TIMELINE
        self.initial["on_timeline"] = "1" if on else "0"

    def _clean_date(self, field):
        try:
            return parse_date(self.cleaned_data[field]).text
        except DateError as exc:
            raise forms.ValidationError(str(exc)) from None

    def clean_date(self):
        return self._clean_date("date")

    def clean_until(self):
        return self._clean_date("until")

    def clean(self):
        data = super().clean()
        if data.get("kind") == "inne" and not data.get("title"):
            self.add_error("title", "Przy „Inne” wpisz tytuł zdarzenia.")
        elif not self.errors and not any(
            data.get(f) for f in ("title", "date", "until", "place", "note", "photo")
        ):
            raise forms.ValidationError("Wpisz przynajmniej datę, miejsce albo notatkę.")
        return data
