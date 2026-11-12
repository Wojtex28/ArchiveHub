"""Punkty osób na zdjęciu (ETAP 44): kto jest kim, wskazany kliknięciem na awersie.

Punkt jest dodatkiem do oznaczenia „Kto jest na zdjęciu”: osoby oznaczone wcześniej zostają
bez punktu, dopóki ktoś go nie postawi. Może to zrobić każdy, kto widzi album.
"""

import logging
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from .comments import photo_page_url, wants_fragment
from .models import PersonMark, Photo, PhotoChange
from .photo_panel import fragment

logger = logging.getLogger(__name__)

# Wspólny limit ze zmianami opisu (albums.metadata.PER_MINUTE), liczony z historii zmian.
PER_MINUTE = 30


def turn_marks(photo, clockwise=True):
    """Obrót awersu o 90°: punkty obracają się razem ze zdjęciem."""
    for mark in photo.marks.all():
        mark.x, mark.y = (1 - mark.y, mark.x) if clockwise else (mark.y, 1 - mark.x)
        mark.save(update_fields=["x", "y"])


def _fraction(text):
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    # Odrzuca też NaN, bo żadne porównanie z NaN nie jest prawdziwe.
    return round(value, 4) if 0 <= value <= 1 else None


@transaction.atomic
def set_mark(photo, person, user, x=None, y=None):
    """Stawia, przesuwa albo (bez współrzędnych) usuwa punkt osoby. Zwraca True, gdy coś się zmieniło."""
    old = photo.marks.filter(person=person).first()
    before = f"{person.name}: punkt" if old else f"{person.name}: bez punktu"
    if x is None:
        if not old:
            return False
        old.delete()
        after = f"{person.name}: bez punktu"
    else:
        if old and (old.x, old.y) == (x, y):
            return False
        PersonMark.objects.update_or_create(
            photo=photo, person=person, defaults={"x": x, "y": y, "set_by": user, "set_at": timezone.now()}
        )
        after = f"{person.name}: punkt przesunięty" if old else f"{person.name}: punkt"
    PhotoChange.objects.create(photo=photo, user=user, changes={"points": [before, after]})
    return True


@require_POST
@login_required
def photo_mark(request, pk):
    """Zapis punktu: ``osoba`` (numer), ``x`` i ``y`` (0–1) albo ``usun=1``. Odsyła odświeżony panel."""
    photo = get_object_or_404(Photo.objects.visible_to(request.user).select_related("album"), pk=pk)
    number = request.POST.get("osoba", "")
    person = photo.people.filter(pk=number).first() if number.isdigit() else None
    if person is None:
        return HttpResponseBadRequest("osoba: ktoś oznaczony na tym zdjęciu")
    if request.POST.get("usun"):
        x = y = None
    else:
        x, y = _fraction(request.POST.get("x")), _fraction(request.POST.get("y"))
        if x is None or y is None:
            return HttpResponseBadRequest("x, y: liczby od 0 do 1")
    recent = PhotoChange.objects.filter(
        user=request.user, created_at__gte=timezone.now() - timedelta(minutes=1)
    ).count()
    if recent >= PER_MINUTE:
        return HttpResponseBadRequest("Za dużo zmian w krótkim czasie. Odczekaj chwilę.")
    if set_mark(photo, person, request.user, x, y):
        logger.info("%s zmienił(a) punkt osoby %s na %s", request.user, person, photo)
    if wants_fragment(request):
        return fragment(request, photo)
    return redirect(photo_page_url(photo, anchor="osoby"))
