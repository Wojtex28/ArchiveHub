from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, F, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST, require_safe

from albums.models import Person, Photo
from albums.search import refresh_search_text
from core.middleware import CONTENT_SECURITY_POLICY

from . import chronology, tree
from .forms import LifeEventForm, NewPersonForm, PersonForm, RelationForm
from .models import LifeEvent

PHOTOS_SHOWN = 60


def tree_access(edit=False):
    """Drzewo widzą konta z dostępem (Panel → Osoby → konto); edycja tylko z prawem edycji."""

    def decorator(view):
        @login_required
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            allowed = request.user.can_edit_tree if edit else request.user.can_view_tree
            if not allowed:
                raise Http404
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def _suggestions():
    return Person.objects.values_list("name", flat=True)


@tree_access()
@require_safe
def tree_home(request):
    return _tree_page(request)


def _namesakes(request, exc):
    return {"name": exc.name, "matches": [tree.namesake_info(p, request.user) for p in exc.matches]}


def _tree_page(request, form=None, namesakes=None):
    query = " ".join(request.GET.get("q", "").split())
    people = Person.objects.filter(in_tree=True).select_related("portrait")
    if query:
        people = people.filter(Q(name__icontains=query) | Q(maiden_name__icontains=query))
    outside = (
        Person.objects.filter(in_tree=False)
        .annotate(count=Count("photos"))
        .filter(count__gt=0)
        .order_by("-count", "key")
    )
    people = list(people)
    # Portret tylko z albumów, które dana osoba widzi.
    visible = set(
        Photo.objects.visible_to(request.user)
        .filter(pk__in=[p.portrait_id for p in people if p.portrait_id])
        .values_list("pk", flat=True)
    )
    for person in people:
        person.visible_portrait = person.portrait if person.portrait_id in visible else None
    return render(
        request,
        "family/tree.html",
        {
            "people": people,
            "query": query,
            "outside": outside,
            "form": form or NewPersonForm(),
            "namesakes": namesakes,
            "suggestions": _suggestions(),
        },
    )


@tree_access(edit=True)
@require_POST
def person_add(request):
    form = NewPersonForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Wpisz imię i nazwisko.")
        return redirect("family:tree")
    try:
        person = tree.person_for(form.cleaned_data["name"], request.POST.get("kto"))
    except tree.NeedsChoice as exc:
        return _tree_page(request, form, _namesakes(request, exc))
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
        return redirect("family:tree")
    tree.put_in_tree(request.user, person)
    messages.success(request, f"{person.name} jest w drzewie. Uzupełnij dane i dodaj rodzinę.")
    return redirect("family:person", person.pk)


def visible_photos(user, person):
    return (
        Photo.objects.visible_to(user)
        .filter(people=person)
        .select_related("album")
        .prefetch_related("people")
        .annotate(comment_count=Count("comments"))
        .order_by("album__position", "album__title", "position")
    )


@tree_access()
@require_safe
def person_detail(request, pk):
    person = get_object_or_404(Person.objects.select_related("portrait"), pk=pk)
    if request.GET.get("okno") == "1":
        return _embedded_card(request, person)
    return _person_page(request, person)


def _embedded_card(request, person):
    """Karta osoby w okienku nad drzewem (ETAP 34): bez menu i edycji, tylko do podglądu.

    To jedyna strona, którą wolno osadzić, i tylko na stronach tej samej domeny (drzewo)."""
    response = _person_page(request, person, embedded=True)
    response["X-Frame-Options"] = "SAMEORIGIN"
    response["Content-Security-Policy"] = CONTENT_SECURITY_POLICY.replace(
        "frame-ancestors 'none'", "frame-ancestors 'self'"
    )
    return response


def photos_by_date(photos):
    """Zdjęcia od najnowszych, jak w galerii telefonu (ETAP 45); bez daty na końcu.

    Każde dostaje ``period`` (dziesięciolecie albo „Bez daty”) na nagłówek nad grupą.
    """
    ordered = list(
        photos.order_by(
            F("year_to").desc(nulls_last=True),
            F("year_from").desc(nulls_last=True),
            "album__position",
            "album__title",
            "position",
        )[:PHOTOS_SHOWN]
    )
    for photo in ordered:
        if photo.year_to is None:
            photo.period = "Bez daty"
        else:
            decade = photo.year_to // 10 * 10
            photo.period = f"{decade}–{decade + 9}"
    return ordered


def _person_page(request, person, relation_form=None, namesakes=None, embedded=False, event_form=None):
    photos = visible_photos(request.user, person)
    portrait = person.portrait if person.portrait and photos.filter(pk=person.portrait_id).exists() else None
    return render(
        request,
        "family/person.html",
        {
            "embedded": embedded,
            "base_template": "family/embed_base.html" if embedded else "app_base.html",
            "person": person,
            "portrait": portrait,
            "parents": tree.parents(person),
            "partners": tree.partners_in_order(person),
            "children": tree.children(person),
            "siblings": tree.siblings(person),
            "photos": photos_by_date(photos),
            "timeline": chronology.timeline(person),
            "event_form": event_form or LifeEventForm(),
            "event_open": event_form is not None,
            "photo_total": photos.count(),
            "relation_form": relation_form or RelationForm(label_suffix=""),
            "namesakes": namesakes,
            "suggestions": _suggestions(),
            "can_edit": request.user.can_edit_tree and not embedded,
        },
    )


@tree_access(edit=True)
@require_http_methods(["GET", "HEAD", "POST"])
def person_edit(request, pk):
    person = get_object_or_404(Person, pk=pk)
    before = tree.snapshot(person)
    old_name = person.name
    portraits = visible_photos(request.user, person)
    form = PersonForm(request.POST or None, instance=person, portraits=portraits)
    if request.method == "POST" and form.is_valid():
        person, notice = save_person(request.user, form, before, old_name)
        if notice:
            messages.info(request, notice)
        messages.success(request, "Zapisano.")
        return redirect("family:person", person.pk)
    # Punkt osoby na zdjęciu (ETAP 44) podpowiada kadr portretu.
    marks = {mark.photo_id: mark for mark in person.marks.all()}
    portrait_photos = list(portraits)
    for photo in portrait_photos:
        photo.mark = marks.get(photo.pk)
    return render(
        request,
        "family/person_form.html",
        {"person": person, "form": form, "portrait_photos": portrait_photos},
    )


def save_person(user, form, before, old_name):
    """Zapis danych osoby (strona „Edytuj dane” i panel boczny drzewa). Zwraca osobę i przypomnienie."""
    with transaction.atomic():
        person = form.save()
        tree.edit_person(user, person, before)
    notice = ""
    if person.name != old_name:
        # Nazwa osoby jest w tekście do wyszukiwania jej zdjęć.
        refresh_search_text(list(person.photos.values_list("pk", flat=True)))
        if tree.same_name(person.name).exclude(pk=person.pk).exists():
            notice = f"W archiwum jest też inna osoba „{person.name}”. Lata życia pomogą je odróżnić."
    return person, notice


@tree_access(edit=True)
@require_POST
def relation_add(request, pk):
    person = get_object_or_404(Person, pk=pk)
    form = RelationForm(request.POST, label_suffix="")
    if form.is_valid():
        try:
            with transaction.atomic():
                other = tree.person_for(form.cleaned_data["name"], request.POST.get("kto"))
                tree.add_relation(request.user, person, other, form.cleaned_data["kind"])
        except tree.NeedsChoice as exc:
            return _person_page(request, person, form, _namesakes(request, exc))
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            messages.success(
                request, f"Dodano: {other.name} ({tree.RELATION_KINDS[form.cleaned_data['kind']]})."
            )
    else:
        messages.error(request, "Wpisz imię i nazwisko i wybierz, kim jest ta osoba.")
    return redirect("family:person", person.pk)


@tree_access(edit=True)
@require_POST
def relation_remove(request, pk, other_pk, kind):
    person = get_object_or_404(Person, pk=pk)
    other = get_object_or_404(Person, pk=other_pk)
    if kind not in tree.RELATION_KINDS:
        raise Http404
    if tree.remove_relation(request.user, person, other, kind):
        messages.success(request, f"Usunięto połączenie z: {other.name}.")
    return redirect("family:person", person.pk)


@tree_access(edit=True)
@require_POST
def person_remove(request, pk):
    person = get_object_or_404(Person, pk=pk, in_tree=True)
    tree.remove_from_tree(request.user, person)
    messages.success(
        request, f"Usunięto z drzewa: {person.name}. Oznaczenia na zdjęciach zostały, a zmianę da się cofnąć."
    )
    return redirect("family:tree")


@tree_access(edit=True)
@require_POST
def couple_edit(request, pk, other_pk):
    """Rok ślubu i rozwód pary (formularz pod partnerem na karcie osoby)."""
    person = get_object_or_404(Person, pk=pk)
    other = get_object_or_404(Person, pk=other_pk)
    try:
        changed = tree.edit_couple(
            request.user, person, other, request.POST.get("since", ""), request.POST.get("ended") == "on"
        )
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    else:
        if changed:
            messages.success(request, f"Zapisano: {person.name} i {other.name}.")
    return redirect("family:person", person.pk)


@tree_access(edit=True)
@require_POST
def event_add(request, pk):
    """„+ Dodaj zdarzenie” na karcie osoby (ETAP 46)."""
    person = get_object_or_404(Person, pk=pk)
    form = LifeEventForm(request.POST)
    if not form.is_valid():
        return _person_page(request, person, event_form=form)
    tree.save_event(request.user, person, form.cleaned_data)
    messages.success(request, "Dodano zdarzenie.")
    return redirect(reverse("family:person", args=[person.pk]) + "#chronologia")


@tree_access(edit=True)
@require_http_methods(["GET", "HEAD", "POST"])
def event_edit(request, pk):
    event = get_object_or_404(LifeEvent.objects.select_related("person"), pk=pk)
    form = LifeEventForm(request.POST or None, instance=event)
    if request.method == "POST" and form.is_valid():
        # Formularz nie zapisuje sam: zapis idzie przez historię zmian drzewa.
        event.refresh_from_db()
        tree.save_event(request.user, event.person, form.cleaned_data, event=event)
        messages.success(request, "Zapisano zdarzenie.")
        return redirect(reverse("family:person", args=[event.person_id]) + "#chronologia")
    return render(request, "family/event_form.html", {"person": event.person, "event": event, "form": form})


@tree_access(edit=True)
@require_POST
def event_remove(request, pk):
    event = get_object_or_404(LifeEvent.objects.select_related("person"), pk=pk)
    person = event.person
    tree.remove_event(request.user, event)
    messages.success(request, "Usunięto zdarzenie. W razie pomyłki wraca przez Panel → Drzewo.")
    return redirect(reverse("family:person", args=[person.pk]) + "#chronologia")
