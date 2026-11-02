"""Panel zdjęcia: opis (ETAP 13) i komentarze (ETAP 10) jako jeden fragment HTML.

Podgląd w galerii wczytuje go obok zdjęcia, a osobna strona zdjęcia wstawia ten sam szablon.
"""

from django.db.models import Q
from django.shortcuts import render

from .forms import CommentForm, MetadataForm
from .models import Person, Photo, Tag


def suggestions_for(user):
    """Podpowiedzi tylko z albumów, które dana osoba widzi: nazwiska z innych gałęzi rodziny nie wyciekają."""
    photos = Photo.objects.visible_to(user)
    return {
        "people": Person.objects.filter(photos__in=photos).distinct().values_list("name", flat=True),
        "tags": Tag.objects.filter(photos__in=photos).distinct().values_list("name", flat=True),
        "places": photos.exclude(place="").order_by("place").values_list("place", flat=True).distinct(),
    }


def people_choices(user):
    """Osoby do wyboru w polu „Kto”: najpierw z drzewa (z latami życia), potem pozostałe ze zdjęć.

    Osoby z drzewa widzi tylko konto z dostępem do drzewa; pozostałe tylko z albumów, które konto widzi.
    """
    visible = Q(photos__in=Photo.objects.visible_to(user))
    if user.can_view_tree:
        visible |= Q(in_tree=True)
    people = Person.objects.filter(visible).distinct().order_by("-in_tree", "key")
    return [
        {"name": person.name, "years": person.years if person.in_tree else "", "tree": person.in_tree}
        for person in people
    ]


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
        "suggestions": suggestions_for(request.user),
        "people_choices": people_choices(request.user),
    }


def fragment(request, photo, comment_form=None, metadata_form=None, status=200):
    context = panel_context(request, photo, comment_form, metadata_form)
    response = render(request, "albums/includes/photo_panel.html", context, status=status)
    response["X-Comment-Count"] = str(len(context["comments"]))
    response["Cache-Control"] = "private, no-store"
    return response
