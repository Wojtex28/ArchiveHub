"""„Moje albumy” (ETAP 51): prywatne zbiory zdjęć jednego konta, obok Ulubionych.

Gwiazdka ☆ przy zdjęciu: kto nie ma własnych albumów, ten dodaje do Ulubionych jak dawniej.
Kto ma, dostaje okienko z listą (Ulubione + jego albumy) i zaznacza, gdzie zdjęcie ma być.
"""

import logging

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST, require_safe

from .downloads import download_size, safe_name
from .models import Favorite, Photo, UserAlbum, UserAlbumPhoto, favorite_ids

logger = logging.getLogger(__name__)

MAX_ALBUMS = 50  # na konto; wystarczy z zapasem, a chroni przed przypadkowym zalewem


class UserAlbumForm(forms.ModelForm):
    class Meta:
        model = UserAlbum
        fields = ["name"]
        labels = {"name": "Nazwa albumu"}

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if not name:
            raise forms.ValidationError("Wpisz nazwę albumu.")
        return name


def own_albums(user):
    return UserAlbum.objects.filter(user=user).annotate(size=Count("entries"))


def own_album_cards(user):
    """„Moje albumy” na pasku obok listy albumów: nazwa, liczba zdjęć i okładka (ostatnio dodane)."""
    albums = list(own_albums(user))
    latest = {}
    entries = (
        UserAlbumPhoto.objects.filter(album__in=albums, photo__in=Photo.objects.visible_to(user))
        .filter(photo__file_missing=False)
        .select_related("photo")
        .order_by("album_id", "-added_at", "-pk")
    )
    for entry in entries:
        latest.setdefault(entry.album_id, entry.photo)
    for album in albums:
        album.cover = latest.get(album.pk)
    return albums


def album_photos(album, user):
    """Zdjęcia „mojego albumu” od ostatnio dodanych; tylko z albumów, które konto nadal widzi."""
    return (
        Photo.objects.visible_to(user)
        .filter(user_album_entries__album=album, file_missing=False)
        .select_related("album")
        .prefetch_related("people")
        .annotate(comment_count=Count("comments", distinct=True))
        .order_by("-user_album_entries__added_at", "-pk")
    )


def _safe_next(request, fallback):
    target = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(target, {request.get_host()}, require_https=request.is_secure()):
        return target
    return fallback


@require_POST
@login_required
def album_create(request):
    form = UserAlbumForm(request.POST)
    if UserAlbum.objects.filter(user=request.user).count() >= MAX_ALBUMS:
        messages.error(request, f"Masz już {MAX_ALBUMS} własnych albumów.")
        return redirect("archive")
    if not form.is_valid():
        messages.error(request, "Wpisz nazwę albumu.")
        return redirect(_safe_next(request, reverse("archive")))
    album = form.save(commit=False)
    album.user = request.user
    album.save()
    logger.info("%s utworzył własny album %s", request.user, album.pk)
    messages.success(
        request, f"Utworzono album „{album.name}”. Dodasz do niego zdjęcia gwiazdką ☆ w podglądzie."
    )
    return redirect("albums:own_album", album.pk)


@require_http_methods(["GET", "HEAD", "POST"])
@login_required
def album_page(request, pk):
    album = get_object_or_404(UserAlbum, pk=pk, user=request.user)
    form = UserAlbumForm(instance=album)
    if request.method == "POST":
        if request.POST.get("action") == "delete":
            name = album.name
            album.delete()
            messages.success(request, f"Usunięto album „{name}”. Zdjęcia zostały w swoich albumach.")
            return redirect("archive")
        form = UserAlbumForm(request.POST, instance=album)
        if form.is_valid():
            form.save()
            messages.success(request, "Zmieniono nazwę albumu.")
            return redirect("albums:own_album", album.pk)
    photos = list(album_photos(album, request.user))
    return render(
        request,
        "albums/own_album.html",
        {
            "own_album": album,
            "form": form,
            "photos": photos,
            "favorite_ids": favorite_ids(request.user),
            "album_size": download_size(photos),
        },
    )


@require_safe
@login_required
def album_download(request, pk):
    from .views import zip_response

    album = get_object_or_404(UserAlbum, pk=pk, user=request.user)
    photos = list(album_photos(album, request.user))
    if not photos:
        raise Http404
    root = safe_name(album.name) or "Mój album"

    def folder(photo):
        return f"{root}/{safe_name(photo.album.display_title)}"

    return zip_response(
        request,
        photos,
        folder,
        f"{root} ({len(photos)} zdj.).zip",
        reverse("albums:own_album", args=[album.pk]),
    )


def _state(user, photo):
    chosen = set(
        UserAlbumPhoto.objects.filter(album__user=user, photo=photo).values_list("album_id", flat=True)
    )
    favorite = Favorite.objects.filter(user=user, photo=photo).exists()
    return {
        "favorite": favorite,
        "albums": [
            {"id": album.pk, "name": album.name, "on": album.pk in chosen}
            for album in UserAlbum.objects.filter(user=user)
        ],
        "collected": favorite or bool(chosen),
    }


@require_http_methods(["GET", "HEAD", "POST"])
@login_required
def photo_collections(request, pk):
    """Okienko przy gwiazdce: GET mówi, gdzie zdjęcie jest; POST dodaje albo zabiera.

    POST: ``album`` = numer „mojego albumu” albo ``ulubione``, ``on`` = 1/0;
    albo ``nowy`` = nazwa: tworzy album i od razu dodaje do niego zdjęcie.
    """
    photo = get_object_or_404(Photo.objects.visible_to(request.user), pk=pk)
    if request.method == "POST":
        new_name = " ".join(request.POST.get("nowy", "").split())[:100]
        wanted = request.POST.get("on") == "1"
        target = request.POST.get("album", "")
        if new_name:
            if UserAlbum.objects.filter(user=request.user).count() >= MAX_ALBUMS:
                return JsonResponse({"error": f"Masz już {MAX_ALBUMS} własnych albumów."}, status=400)
            album = UserAlbum.objects.create(user=request.user, name=new_name)
            UserAlbumPhoto.objects.create(album=album, photo=photo)
        elif target == "ulubione":
            if wanted:
                Favorite.objects.get_or_create(user=request.user, photo=photo)
            else:
                Favorite.objects.filter(user=request.user, photo=photo).delete()
        elif target.isdigit():
            album = get_object_or_404(UserAlbum, pk=int(target), user=request.user)
            if wanted:
                try:
                    with transaction.atomic():
                        UserAlbumPhoto.objects.create(album=album, photo=photo)
                except IntegrityError:
                    pass  # już tam było
            else:
                UserAlbumPhoto.objects.filter(album=album, photo=photo).delete()
        else:
            return JsonResponse({"error": "Nie wiadomo, do którego albumu."}, status=400)
    response = JsonResponse(_state(request.user, photo))
    response["Cache-Control"] = "private, no-store"
    return response
