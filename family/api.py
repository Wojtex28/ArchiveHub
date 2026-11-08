"""Dane drzewa dla kanwy (static/js/family-tree.js) i zmiany wysyłane z kanwy.

Każda zmiana odpowiada pełnym stanem drzewa: rodzina to najwyżej kilkaset osób, więc to prostsze
i pewniejsze niż składanie zmian po stronie przeglądarki.
"""

import json

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST, require_safe

from albums.models import NamedModel, Person, Photo

from . import tree
from .models import ParentChild, Partnership
from .views import tree_access

# Kanwa ma granice, żeby kafelek nie uciekł w nieskończoność po błędzie.
COORD_LIMIT = 100_000


def tree_data(user):
    people = list(Person.objects.filter(in_tree=True).order_by("key"))
    portraits = {p.portrait_id for p in people if p.portrait_id}
    visible = Photo.objects.visible_to(user).in_bulk(portraits)
    outside = (
        Person.objects.filter(in_tree=False)
        .annotate(count=Count("photos"))
        .filter(count__gt=0)
        .order_by("-count", "key")
    )
    return {
        "people": [
            {
                "id": p.pk,
                "name": p.name,
                "maiden": p.maiden_name,
                "years": p.life,
                "deceased": p.deceased,
                "born": p.birth_year,
                "died": p.death_year,
                "x": p.tree_x,
                "y": p.tree_y,
                "url": reverse("family:person", args=[p.pk]),
                "portrait": _portrait(visible.get(p.portrait_id)),
            }
            for p in people
        ],
        "parents": list(ParentChild.objects.values_list("parent_id", "child_id")),
        "partners": list(Partnership.objects.values_list("person1_id", "person2_id")),
        # ETAP 31: rok ślubu (kolejność związków) i rozwód (linia przerywana).
        "couples": [
            {"a": c.person1_id, "b": c.person2_id, "since": c.since, "year": c.since_year, "ended": c.ended}
            for c in Partnership.objects.all()
            if c.since or c.ended
        ],
        "outside": [{"id": p.pk, "name": p.name, "count": p.count} for p in outside[:200]],
        "names": list(Person.objects.values_list("name", flat=True)),
        "canEdit": user.can_edit_tree,
    }


def _portrait(photo):
    if photo is None:
        return None
    url = f"{reverse('albums:thumb', args=[photo.pk])}?v={photo.version_front}"
    return {"url": url, "turn": photo.pending_front}


def _ok(request, **extra):
    return JsonResponse({**tree_data(request.user), **extra})


def _error(message, status=400):
    return JsonResponse({"error": message}, status=status)


def _body(request):
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _person(value, in_tree=None):
    try:
        query = Person.objects.filter(pk=int(value))
    except (TypeError, ValueError):
        return None
    if in_tree is not None:
        query = query.filter(in_tree=in_tree)
    return query.first()


def _coord(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if -COORD_LIMIT <= number <= COORD_LIMIT else None


def _name(value):
    name = " ".join(str(value or "").split())
    return name if 0 < len(name) <= NamedModel.MAX_LENGTH else ""


@tree_access()
@require_safe
def data(request):
    return _ok(request)


@tree_access(edit=True)
@require_POST
@transaction.atomic
def save_positions(request):
    """Zapis miejsc kafelków po przeciągnięciu albo „Ułóż automatycznie”: ``{"positions": {id: [x, y]}}``."""
    positions = _body(request).get("positions")
    if not isinstance(positions, dict):
        return _error("Brak położeń.")
    people = Person.objects.in_bulk([int(k) for k in positions if str(k).isdigit()])
    changed = []
    for pk, person in people.items():
        value = positions.get(str(pk)) or positions.get(pk)
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            continue
        x, y = _coord(value[0]), _coord(value[1])
        if x is None or y is None:
            continue
        person.tree_x, person.tree_y = round(x, 1), round(y, 1)
        changed.append(person)
    Person.objects.bulk_update(changed, ["tree_x", "tree_y"])
    return _ok(request)


@tree_access(edit=True)
@require_POST
def add(request):
    """Nowa osoba albo osoba ze zdjęć.

    Treść: ``{"name"|"id", "new", "x", "y", "relation": {"to", "kind", "second"}}``.

    Nazwa, którą ktoś już ma, nie łączy się sama: odpowiedź 409 z listą ``matches`` i formularz pyta,
    czy to ta sama osoba (wtedy ``id``), czy imiennik (``"new": true``).
    """
    body = _body(request)
    relation = body.get("relation") or {}
    other, second = None, tree.AUTO
    if relation:
        other = _person(relation.get("to"), in_tree=True)
        if other is None:
            return _error("Nie ma takiej osoby w drzewie.", 404)
        # Drugi rodzic nowego dziecka: id, ``null`` (nie wiadomo) albo brak klucza (jedyny partner).
        if "second" in relation:
            second = None
            if relation["second"] is not None:
                second = _person(relation["second"], in_tree=True)
                if second is None:
                    return _error("Nie ma takiej osoby w drzewie.", 404)
    with transaction.atomic():
        if body.get("id") is not None:
            person = _person(body["id"])
            if person is None:
                return _error("Nie ma takiej osoby.", 404)
        else:
            name = _name(body.get("name"))
            if not name:
                return _error("Wpisz imię i nazwisko (najwyżej 100 znaków).")
            try:
                person = tree.person_for(name, tree.NEW if body.get("new") is True else None)
            except tree.NeedsChoice as exc:
                matches = [tree.namesake_info(p, request.user) for p in exc.matches[:10]]
                return JsonResponse({"error": exc.message, "matches": matches}, status=409)
        if other is not None:
            try:
                # „kind” mówi, kim nowa osoba jest dla ``other``.
                tree.add_relation(request.user, other, person, relation.get("kind"), second_parent=second)
            except ValidationError as exc:
                transaction.set_rollback(True)
                return _error(exc.messages[0])
        else:
            tree.put_in_tree(request.user, person)
        x, y = _coord(body.get("x")), _coord(body.get("y"))
        if x is not None and y is not None and person.tree_x is None:
            Person.objects.filter(pk=person.pk).update(tree_x=round(x, 1), tree_y=round(y, 1))
    return _ok(request, added=person.pk)


@tree_access(edit=True)
@require_POST
def relation(request):
    """Połączenie dwóch osób z drzewa: ``{"person", "other", "kind", "remove": bool}``."""
    body = _body(request)
    person, other = _person(body.get("person"), in_tree=True), _person(body.get("other"), in_tree=True)
    if person is None or other is None:
        return _error("Nie ma takiej osoby w drzewie.", 404)
    kind = body.get("kind")
    if kind not in tree.RELATION_KINDS:
        return _error("Nieznany rodzaj relacji.")
    if body.get("remove"):
        tree.remove_relation(request.user, person, other, kind)
        return _ok(request)
    try:
        tree.add_relation(request.user, person, other, kind)
    except ValidationError as exc:
        return _error(exc.messages[0])
    return _ok(request)


@tree_access(edit=True)
@require_POST
def remove(request):
    person = _person(_body(request).get("id"), in_tree=True)
    if person is None:
        return _error("Nie ma takiej osoby w drzewie.", 404)
    tree.remove_from_tree(request.user, person)
    return _ok(request)


@tree_access(edit=True)
@require_POST
def alive(request):
    """Przełącznik „Żyje / Nie żyje” z kanwy: ``{"id", "deceased": bool}``."""
    body = _body(request)
    person = _person(body.get("id"), in_tree=True)
    if person is None:
        return _error("Nie ma takiej osoby w drzewie.", 404)
    deceased = body.get("deceased")
    if not isinstance(deceased, bool):
        return _error("Brak wartości przełącznika.")
    if not deceased and (person.death_date or person.death_place):
        return _error("Ta osoba ma wpisaną datę lub miejsce śmierci. Usuń je w „Edytuj dane”.")
    with transaction.atomic():
        before = tree.snapshot(person)
        person.deceased = deceased
        person.save(update_fields=["deceased"])
        tree.edit_person(request.user, person, before)
    return _ok(request)


@tree_access(edit=True)
@require_POST
def couple(request):
    """Rok ślubu i rozwód pary z kanwy: ``{"person", "other", "since", "ended"}``."""
    body = _body(request)
    person, other = _person(body.get("person"), in_tree=True), _person(body.get("other"), in_tree=True)
    if person is None or other is None:
        return _error("Nie ma takiej osoby w drzewie.", 404)
    try:
        tree.edit_couple(request.user, person, other, str(body.get("since") or ""), body.get("ended") is True)
    except ValidationError as exc:
        return _error(exc.messages[0])
    return _ok(request)
