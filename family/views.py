from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST, require_safe

from albums.models import Person, Photo
from albums.search import refresh_search_text

from . import tree
from .forms import NewPersonForm, PersonForm, RelationForm

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


def _visible_photos(user, person):
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
    return _person_page(request, get_object_or_404(Person.objects.select_related("portrait"), pk=pk))


def _person_page(request, person, relation_form=None, namesakes=None):
    photos = _visible_photos(request.user, person)
    portrait = person.portrait if person.portrait and photos.filter(pk=person.portrait_id).exists() else None
    return render(
        request,
        "family/person.html",
        {
            "person": person,
            "portrait": portrait,
            "parents": tree.parents(person),
            "partners": tree.partners_in_order(person),
            "children": tree.children(person),
            "siblings": tree.siblings(person),
            "photos": photos[:PHOTOS_SHOWN],
            "photo_total": photos.count(),
            "relation_form": relation_form or RelationForm(label_suffix=""),
            "namesakes": namesakes,
            "suggestions": _suggestions(),
            "can_edit": request.user.can_edit_tree,
        },
    )


@tree_access(edit=True)
@require_http_methods(["GET", "HEAD", "POST"])
def person_edit(request, pk):
    person = get_object_or_404(Person, pk=pk)
    before = tree.snapshot(person)
    old_name = person.name
    portraits = _visible_photos(request.user, person)
    form = PersonForm(request.POST or None, instance=person, portraits=portraits)
    if request.method == "POST" and form.is_valid():
        person = form.save()
        if person.name != old_name:
            # Nazwa osoby jest w tekście do wyszukiwania jej zdjęć.
            refresh_search_text(list(person.photos.values_list("pk", flat=True)))
            if tree.same_name(person.name).exclude(pk=person.pk).exists():
                messages.info(
                    request,
                    f"W archiwum jest też inna osoba „{person.name}”. Lata życia pomogą je odróżnić.",
                )
        tree.edit_person(request.user, person, before)
        messages.success(request, "Zapisano.")
        return redirect("family:person", person.pk)
    return render(
        request, "family/person_form.html", {"person": person, "form": form, "portraits": portraits}
    )


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
