"""Ulubione (ETAP 29): każde konto zbiera swoje zdjęcia w prywatny album i może go pobrać w całości."""

import logging

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST, require_safe

from .comments import wants_fragment
from .downloads import download_size, safe_name
from .models import Favorite, Photo

logger = logging.getLogger(__name__)

FOLDER = "Ulubione"


def favorite_photos(user):
    """Ulubione zdjęcia konta, od ostatnio dodanych. Tylko z albumów, które to konto nadal widzi."""
    return (
        Photo.objects.visible_to(user)
        .filter(favorites__user=user, file_missing=False)
        .select_related("album")
        .prefetch_related("people")
        .annotate(comment_count=Count("comments", distinct=True))
        .order_by("-favorites__created_at", "-pk")
    )


@require_POST
@login_required
def favorite_toggle(request, pk):
    """☆/★ przy zdjęciu. ``ulubione=1`` dodaje, ``0`` usuwa; powtórzenie niczego nie psuje."""
    photo = get_object_or_404(Photo.objects.visible_to(request.user), pk=pk)
    wanted = request.POST.get("ulubione") == "1"
    if wanted:
        Favorite.objects.get_or_create(user=request.user, photo=photo)
    else:
        Favorite.objects.filter(user=request.user, photo=photo).delete()
    if wants_fragment(request):
        return JsonResponse({"favorite": wanted, "count": favorite_photos(request.user).count()})
    target = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(target, {request.get_host()}, require_https=request.is_secure()):
        target = reverse("albums:photo", args=[photo.album_id, photo.pk])
    return redirect(target)


@require_safe
@login_required
def favorites_page(request):
    photos = list(favorite_photos(request.user))
    return render(
        request,
        "albums/favorites.html",
        {
            "photos": photos,
            "favorite_ids": {photo.pk for photo in photos},
            "album_size": download_size(photos),
        },
    )


@require_safe
@login_required
def favorites_download(request):
    """Wszystkie ulubione jako jeden ZIP, w folderach albumów."""
    from .views import zip_response

    photos = list(favorite_photos(request.user))
    if not photos:
        raise Http404

    def folder(photo):
        return f"{FOLDER}/{safe_name(photo.album.title)}"

    return zip_response(
        request, photos, folder, f"{FOLDER} ({len(photos)} zdj.).zip", reverse("albums:favorites")
    )
