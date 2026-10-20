"""Komentarze pod zdjęciami.

Lista i formularz to jeden fragment HTML: podgląd w galerii wczytuje go i odświeża bez
przeładowania strony (nagłówek ``X-Requested-With: fetch``), a osobna strona zdjęcia pokazuje go
od razu i działa też bez JavaScriptu. Treść zawsze przechodzi przez autoescape szablonów.
"""

import logging
from datetime import timedelta

from django import forms
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from .models import Comment, Photo

logger = logging.getLogger(__name__)

# Ochrona przed zalaniem komentarzami (np. przez przejęte konto): tyle na minutę na osobę.
PER_MINUTE = 10


class CommentForm(forms.Form):
    text = forms.CharField(
        label="Twój komentarz",
        max_length=Comment.MAX_LENGTH,
        strip=True,
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "Kto jest na zdjęciu? Gdzie i kiedy je zrobiono?"}
        ),
    )


def _visible_photo(request, pk):
    return get_object_or_404(Photo.objects.visible_to(request.user).select_related("album"), pk=pk)


def _wants_fragment(request):
    return request.headers.get("X-Requested-With") == "fetch"


def photo_page_url(photo):
    return reverse("albums:photo", args=[photo.album_id, photo.pk]) + "?komentarze=1#komentarze"


def comments_context(request, photo, form=None):
    comments = list(photo.comments.select_related("author"))
    for comment in comments:
        comment.deletable = comment.can_delete(request.user)
    return {"photo": photo, "comments": comments, "comment_form": form or CommentForm()}


def _fragment(request, photo, form=None, status=200):
    context = comments_context(request, photo, form)
    response = render(request, "albums/includes/comments.html", context, status=status)
    response["X-Comment-Count"] = str(len(context["comments"]))
    response["Cache-Control"] = "private, no-store"
    return response


@require_http_methods(["GET", "HEAD", "POST"])
@login_required
def photo_comments(request, pk):
    """GET: lista z formularzem. POST: nowy komentarz. Może każdy, kto widzi album."""
    photo = _visible_photo(request, pk)
    if request.method != "POST":
        if not _wants_fragment(request):
            return redirect(photo_page_url(photo))
        return _fragment(request, photo)

    form = CommentForm(request.POST)
    recent = Comment.objects.filter(
        author=request.user, created_at__gte=timezone.now() - timedelta(minutes=1)
    ).count()
    if form.is_valid() and recent >= PER_MINUTE:
        form.add_error("text", "Za dużo komentarzy w krótkim czasie. Odczekaj chwilę.")
    if not form.is_valid():
        if _wants_fragment(request):
            return _fragment(request, photo, form, status=400)
        # Bez JavaScriptu: strona zdjęcia z błędem pod formularzem.
        # Import tutaj, bo views importuje ten moduł.
        from .views import render_photo_page

        return render_photo_page(request, photo.album_id, photo.pk, comment_form=form)
    Comment.objects.create(photo=photo, author=request.user, text=form.cleaned_data["text"])
    logger.info("%s skomentował(a) %s", request.user, photo)
    if _wants_fragment(request):
        return _fragment(request, photo)
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
    if _wants_fragment(request):
        return _fragment(request, photo)
    return redirect(photo_page_url(photo))
