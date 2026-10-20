"""Komentarze pod zdjęciami.

Lista i formularz są częścią panelu zdjęcia (albums.photo_panel), jednego fragmentu HTML:
podgląd w galerii wczytuje go i odświeża bez przeładowania strony (nagłówek ``X-Requested-With: fetch``),
a osobna strona zdjęcia pokazuje go od razu i działa też bez JavaScriptu.
Treść zawsze przechodzi przez autoescape szablonów.
"""

import logging
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from .forms import CommentForm
from .models import Comment, Photo
from .photo_panel import fragment

logger = logging.getLogger(__name__)

# Ochrona przed zalaniem komentarzami (np. przez przejęte konto): tyle na minutę na osobę.
PER_MINUTE = 10


def _visible_photo(request, pk):
    return get_object_or_404(Photo.objects.visible_to(request.user).select_related("album"), pk=pk)


def wants_fragment(request):
    return request.headers.get("X-Requested-With") == "fetch"


def photo_page_url(photo, anchor="komentarze"):
    return reverse("albums:photo", args=[photo.album_id, photo.pk]) + f"?komentarze=1#{anchor}"


@require_http_methods(["GET", "HEAD", "POST"])
@login_required
def photo_comments(request, pk):
    """GET: lista z formularzem. POST: nowy komentarz. Może każdy, kto widzi album."""
    photo = _visible_photo(request, pk)
    if request.method != "POST":
        if not wants_fragment(request):
            return redirect(photo_page_url(photo))
        return fragment(request, photo)

    form = CommentForm(request.POST)
    recent = Comment.objects.filter(
        author=request.user, created_at__gte=timezone.now() - timedelta(minutes=1)
    ).count()
    if form.is_valid() and recent >= PER_MINUTE:
        form.add_error("text", "Za dużo komentarzy w krótkim czasie. Odczekaj chwilę.")
    if not form.is_valid():
        if wants_fragment(request):
            return fragment(request, photo, comment_form=form, status=400)
        # Bez JavaScriptu: strona zdjęcia z błędem pod formularzem.
        # Import tutaj, bo views importuje ten moduł.
        from .views import render_photo_page

        return render_photo_page(request, photo.album_id, photo.pk, comment_form=form)
    Comment.objects.create(photo=photo, author=request.user, text=form.cleaned_data["text"])
    logger.info("%s skomentował(a) %s", request.user, photo)
    if wants_fragment(request):
        return fragment(request, photo)
    return redirect(photo_page_url(photo))


@require_POST
@login_required
def comment_delete(request, pk):
    """Usuwa komentarz: autor swój, administrator każdy. Cudzy wygląda jak nieistniejący (404)."""
    comment = get_object_or_404(
        Comment.objects.select_related("photo__album", "author"),
        pk=pk,
        photo__in=Photo.objects.visible_to(request.user),
    )
    if not comment.can_delete(request.user):
        raise Http404
    photo = comment.photo
    logger.info("%s usunął(-ęła) komentarz %s: %r", request.user, comment.pk, comment.text[:200])
    comment.delete()
    if wants_fragment(request):
        return fragment(request, photo)
    return redirect(photo_page_url(photo))
