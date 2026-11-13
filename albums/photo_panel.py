"""Panel zdjęcia: opis (ETAP 13) i komentarze (ETAP 10) jako jeden fragment HTML.

Podgląd w galerii wczytuje go obok zdjęcia, a osobna strona zdjęcia wstawia ten sam szablon.
"""

from django.db.models import Q
from django.shortcuts import render

from .forms import CommentForm, MetadataForm
from .models import Person, Photo, Tag, namesake_keys, person_token


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
    people = Person.objects.filter(visible).distinct().order_by("-in_tree", "key", "pk")
    namesakes = namesake_keys()
    return [
        {
            "name": person.name,
            # Imiennika wskazuje numer („Jan Bereza #12”), resztę sama nazwa.
            "token": person_token(person, namesakes),
            "same": person.key in namesakes,
            "years": person.years if person.in_tree else "",
            "tree": person.in_tree,
        }
        for person in people
    ]


def panel_context(request, photo, comment_form=None, metadata_form=None, people_form=None):
    comments = list(photo.comments.select_related("author"))
    for comment in comments:
        comment.deletable = comment.can_delete(request.user)
    people = list(photo.people.all())
    namesakes = namesake_keys()
    marks = {mark.person_id: mark for mark in photo.marks.all()}
    for person in people:
        person.mark = marks.get(person.pk)
        # Dwie osoby „Jan Bereza” na liście „Kto” odróżniają lata życia z drzewa.
        person.namesake_years = person.years if person.key in namesakes and person.in_tree else ""
    tags = list(photo.tags.all())
    return {
        "photo": photo,
        "comments": comments,
        "comment_form": comment_form or CommentForm(),
        "metadata_form": metadata_form or MetadataForm.for_photo(photo, part="opis"),
        "metadata_open": metadata_form is not None,
        "people_form": people_form or MetadataForm.for_photo(photo, part="osoby"),
        "people_open": people_form is not None,
        "can_view_tree": request.user.can_view_tree,
        "is_favorite": photo.favorites.filter(user=request.user).exists(),
        "is_collected": photo.favorites.filter(user=request.user).exists()
        or photo.user_album_entries.filter(album__user=request.user).exists(),
        "photo_people": people,
        "photo_tags": tags,
        "has_metadata": bool(photo.date_text or photo.place or photo.description or tags),
        "suggestions": suggestions_for(request.user),
        "people_choices": people_choices(request.user),
    }


def fragment(request, photo, comment_form=None, metadata_form=None, people_form=None, status=200):
    context = panel_context(request, photo, comment_form, metadata_form, people_form)
    response = render(request, "albums/includes/photo_panel.html", context, status=status)
    response["X-Comment-Count"] = str(len(context["comments"]))
    response["Cache-Control"] = "private, no-store"
    return response
