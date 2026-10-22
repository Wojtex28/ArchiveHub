"""Wyszukiwanie zdjęć (ETAP 14): po tekście, osobie, tagu, miejscu, latach i albumie.

SQLite porównuje bez wielkości liter tylko litery łacińskie, a rodzina często pisze bez ogonków
(„Berezow”). Dlatego każde zdjęcie ma pole ``search_text``: opis, data, miejsce, osoby, tagi
i komentarze małymi literami i bez polskich znaków. Szukany tekst przechodzi tę samą zamianę.
"""

import unicodedata

from django import forms
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from django.shortcuts import render
from django.views.decorators.http import require_safe

from .models import Album, Person, Photo, Tag, name_key
from .photo_panel import suggestions_for

PER_PAGE = 60
OVERVIEW_ITEMS = 40

# Litery, których NFKD nie rozkłada na literę i znak diakrytyczny.
EXTRA = str.maketrans({"ł": "l", "ø": "o", "ß": "ss", "đ": "d"})


def normalize(text):
    """„Łucja Bereza, Kraków” → „lucja bereza, krakow”."""
    text = unicodedata.normalize("NFKD", (text or "").casefold()).translate(EXTRA)
    return " ".join("".join(char for char in text if not unicodedata.combining(char)).split())


def build_search_text(photo):
    parts = [photo.date_text, photo.place, photo.description]
    parts += [person.name for person in photo.people.all()]
    parts += [tag.name for tag in photo.tags.all()]
    parts += [comment.text for comment in photo.comments.all()]
    return normalize("\n".join(part for part in parts if part))


def refresh_search_text(ids):
    """Przelicza ``search_text`` zdjęć o podanych numerach (lista albo QuerySet z ``values_list("pk")``)."""
    for photo in Photo.objects.filter(pk__in=ids).prefetch_related("people", "tags", "comments"):
        text = build_search_text(photo)
        if text != photo.search_text:
            Photo.objects.filter(pk=photo.pk).update(search_text=text)


def text_filter(query, albums):
    """Każde słowo musi wystąpić w opisie zdjęcia albo w nazwie jego albumu."""
    condition = Q()
    for word in normalize(query).split():
        album_ids = [album.pk for album in albums if word in normalize(album.title)]
        condition &= Q(search_text__contains=word) | Q(album_id__in=album_ids)
    return condition


class SearchForm(forms.Form):
    q = forms.CharField(
        label="Szukaj",
        required=False,
        max_length=200,
        widget=forms.SearchInput(attrs={"placeholder": "np. wesele, babcia Helena, Berezów"}),
    )
    osoba = forms.CharField(
        label="Osoba",
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={"list": "szukaj-osoby", "autocomplete": "off"}),
    )
    tag = forms.CharField(
        label="Tag",
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={"list": "szukaj-tagi", "autocomplete": "off"}),
    )
    miejsce = forms.CharField(
        label="Miejsce",
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs={"list": "szukaj-miejsca", "autocomplete": "off"}),
    )
    od = forms.IntegerField(
        label="Od roku",
        required=False,
        min_value=1800,
        max_value=2100,
        widget=forms.NumberInput(attrs={"placeholder": "1950"}),
    )
    do = forms.IntegerField(
        label="Do roku",
        required=False,
        min_value=1800,
        max_value=2100,
        widget=forms.NumberInput(attrs={"placeholder": "1969"}),
    )
    album = forms.TypedChoiceField(label="Album", required=False, coerce=int, empty_value=None)
    bez_opisu = forms.BooleanField(label="Tylko zdjęcia bez opisu", required=False)

    def __init__(self, *args, albums=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["album"].choices = [("", "Wszystkie albumy")] + [
            (album.pk, album.title) for album in albums
        ]

    def has_filters(self):
        return self.is_valid() and any(value not in (None, "", False) for value in self.cleaned_data.values())


def search_photos(user, data, albums):
    """Zdjęcia widoczne dla osoby, pasujące do wszystkich podanych warunków naraz."""
    photos = Photo.objects.visible_to(user).filter(file_missing=False)
    if data["q"]:
        photos = photos.filter(text_filter(data["q"], albums))
    if data["osoba"]:
        photos = photos.filter(people__key=name_key(data["osoba"]))
    if data["tag"]:
        photos = photos.filter(tags__key=name_key(data["tag"].lstrip("#")))
    if data["miejsce"]:
        wanted = normalize(data["miejsce"])
        places = {
            place
            for place in photos.exclude(place="").values_list("place", flat=True)
            if wanted in normalize(place)
        }
        photos = photos.filter(place__in=places)
    if data["od"] is not None:
        photos = photos.filter(year_to__gte=data["od"])
    if data["do"] is not None:
        photos = photos.filter(year_from__lte=data["do"])
    if data["album"]:
        photos = photos.filter(album_id=data["album"])
    if data["bez_opisu"]:
        photos = photos.filter(described_at__isnull=True)
    return photos.distinct().order_by(
        F("year_from").asc(nulls_last=True), "album__position", "position", "pk"
    )


def _overview(user):
    """Podpowiedzi na pustej stronie wyszukiwania: osoby, tagi i dziesięciolecia z widocznych zdjęć."""
    photos = Photo.objects.visible_to(user).filter(file_missing=False)
    people = (
        Person.objects.filter(photos__in=photos)
        .annotate(count=Count("photos", distinct=True))
        .order_by("-count", "key")
    )
    tags = (
        Tag.objects.filter(photos__in=photos)
        .annotate(count=Count("photos", distinct=True))
        .order_by("-count", "key")
    )
    decades = {}
    for year in photos.exclude(year_from=None).values_list("year_from", flat=True):
        decades[year // 10 * 10] = decades.get(year // 10 * 10, 0) + 1
    return {
        "top_people": people[:OVERVIEW_ITEMS],
        "top_tags": tags[:OVERVIEW_ITEMS],
        "decades": sorted(decades.items()),
        "undescribed": photos.filter(described_at__isnull=True).count(),
        "described": photos.filter(described_at__isnull=False).count(),
    }


@require_safe
@login_required
def search(request):
    albums = list(Album.objects.visible_to(request.user))
    form = SearchForm(request.GET or None, albums=albums)
    context = {"form": form, "suggestions": suggestions_for(request.user)}
    if form.has_filters():
        photos = search_photos(request.user, form.cleaned_data, albums)
        page = Paginator(
            photos.select_related("album")
            .prefetch_related("people")
            .annotate(comment_count=Count("comments")),
            PER_PAGE,
        ).get_page(request.GET.get("strona"))
        query = request.GET.copy()
        query.pop("strona", None)
        offset = max(page.start_index() - 1, 0)
        context.update({"searched": True, "page": page, "query": query.urlencode(), "offset": offset})
    else:
        context.update(_overview(request.user))
    return render(request, "albums/search.html", context)
