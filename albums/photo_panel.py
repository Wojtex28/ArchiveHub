"""Panel zdjęcia: opis (ETAP 13) i komentarze (ETAP 10) jako jeden fragment HTML.

Podgląd w galerii wczytuje go obok zdjęcia, a osobna strona zdjęcia wstawia ten sam szablon.
"""

from django.shortcuts import render

from .forms import CommentForm, MetadataForm
from .models import Person, Photo, Tag


def _suggestions(user):
    """Podpowiedzi tylko z albumów, które dana osoba widzi: nazwiska z innych gałęzi rodziny nie wyciekają."""
    photos = Photo.objects.visible_to(user)
    return {
        "people": Person.objects.filter(photos__in=photos).distinct().values_list("name", flat=True),
        "tags": Tag.objects.filter(photos__in=photos).distinct().values_list("name", flat=True),
        "places": photos.exclude(place="").order_by("place").values_list("place", flat=True).distinct(),
    }


def panel_context(request, photo, comment_form=None, metadata_form=None):
    comments = list(photo.comments.select_related("author"))
    for comment in comments:
        comment.deletable = comment.can_delete(request.user)
    people = list(photo.people.all())
    tags = list(photo.tags.all())
    return {
        "photo": photo,
        "comments": comments,
        "comment_form": comment_form or CommentForm(),
        "metadata_form": metadata_form or MetadataForm.for_photo(photo),
        "metadata_open": metadata_form is not None,
        "photo_people": people,
        "photo_tags": tags,
        "has_metadata": bool(photo.date_text or photo.place or photo.description or people or tags),
        "suggestions": _suggestions(request.user),
    }


def fragment(request, photo, comment_form=None, metadata_form=None, status=200):
    context = panel_context(request, photo, comment_form, metadata_form)
    response = render(request, "albums/includes/photo_panel.html", context, status=status)
    response["X-Comment-Count"] = str(len(context["comments"]))
    response["Cache-Control"] = "private, no-store"
    return response
