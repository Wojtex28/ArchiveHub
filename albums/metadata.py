"""Opis zdjęcia (ETAP 13): data, miejsce, osoby, tagi i opis, uzupełniane przez rodzinę.

Poprawiać może każdy, kto widzi album, tak jak obracać i komentować. Każda zmiana trafia do
historii (:class:`PhotoChange`), więc pomyłkę widać i da się ją cofnąć ręcznie.
"""

import logging
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from .comments import photo_page_url, wants_fragment
from .forms import MetadataForm
from .models import Person, Photo, PhotoChange, Tag, name_key
from .photo_panel import fragment

logger = logging.getLogger(__name__)

# Ochrona przed hurtowym nadpisywaniem opisów (np. przez przejęte konto).
PER_MINUTE = 30

# Nazwy pól w historii zmian, w kolejności wyświetlania.
LABELS = {
    "date": "Kiedy",
    "place": "Gdzie",
    "people": "Osoby",
    "tags": "Tagi",
    "description": "Opis",
}


def current_values(photo):
    return {
        "date": photo.date_text,
        "place": photo.place,
        "people": [person.name for person in photo.people.all()],
        "tags": [tag.name for tag in photo.tags.all()],
        "description": photo.description,
    }


def _same(field, before, after):
    if field in ("people", "tags"):
        return [name_key(name) for name in before] == [name_key(name) for name in after]
    return before == after


def _set_names(photo, field, model, names):
    """Ustawia osoby albo tagi; wpisy, które przestały być na jakimkolwiek zdjęciu, znikają."""
    relation = getattr(photo, field)
    old = set(relation.values_list("pk", flat=True))
    items = [model.objects.get_or_create_named(name) for name in names]
    relation.set(items)
    model.objects.filter(pk__in=old - {item.pk for item in items}, photos__isnull=True).delete()


@transaction.atomic
def save_metadata(photo, user, data):
    """Zapisuje opis z formularza. Zwraca zmienione pola (pusty słownik, gdy nic się nie zmieniło)."""
    before = current_values(photo)
    after = {
        "date": data["date"].text,
        "place": " ".join(data["place"].split()),
        "people": data["people"],
        "tags": data["tags"],
        "description": data["description"].strip(),
    }
    changes = {
        field: [before[field], after[field]]
        for field in LABELS
        if not _same(field, before[field], after[field])
    }
    if not changes:
        return changes
    photo.date_text = data["date"].text
    photo.year_from = data["date"].year_from
    photo.year_to = data["date"].year_to
    photo.place = after["place"]
    photo.description = after["description"]
    photo.described_at = timezone.now()
    photo.described_by = user
    fields = ["date_text", "year_from", "year_to", "place", "description", "described_at", "described_by"]
    photo.save(update_fields=fields)
    if "people" in changes:
        _set_names(photo, "people", Person, after["people"])
    if "tags" in changes:
        _set_names(photo, "tags", Tag, after["tags"])
    PhotoChange.objects.create(photo=photo, user=user, changes=changes)
    return changes


def change_rows(change):
    """Zmiana do wyświetlenia: [(etykieta, przed, po)] z listami złączonymi przecinkami."""
    rows = []
    for field, label in LABELS.items():
        if field not in change.changes:
            continue
        before, after = change.changes[field]
        if isinstance(before, list):
            before, after = ", ".join(before), ", ".join(after)
        rows.append((label, before, after))
    return rows


@require_POST
@login_required
def photo_metadata(request, pk):
    """Zapis opisu zdjęcia. Z JavaScriptem odsyła odświeżony panel, bez niego wraca na stronę zdjęcia."""
    photo = get_object_or_404(Photo.objects.visible_to(request.user).select_related("album"), pk=pk)
    form = MetadataForm(request.POST)
    recent = PhotoChange.objects.filter(
        user=request.user, created_at__gte=timezone.now() - timedelta(minutes=1)
    ).count()
    if form.is_valid() and recent >= PER_MINUTE:
        form.add_error(None, "Za dużo zmian w krótkim czasie. Odczekaj chwilę.")
    if not form.is_valid():
        if wants_fragment(request):
            return fragment(request, photo, metadata_form=form, status=400)
        from .views import render_photo_page

        return render_photo_page(request, photo.album_id, photo.pk, metadata_form=form)
    changes = save_metadata(photo, request.user, form.cleaned_data)
    if changes:
        logger.info("%s zmienił(a) opis %s: %s", request.user, photo, ", ".join(changes))
    if wants_fragment(request):
        return fragment(request, photo)
    return redirect(photo_page_url(photo, anchor="opis"))
