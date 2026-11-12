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
from django.views.decorators.http import require_http_methods, require_POST, require_safe

from albums.models import NamedModel, Person, Photo

from . import tree
from .forms import PersonForm
from .models import ParentChild, Partnership, Sibling
from .views import save_person, tree_access, visible_photos

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
                "gender": p.gender,
                "years": p.life,
                "deceased": p.deceased,
                "born": p.birth_year,
                "died": p.death_year,
                # ETAP 34: dane do podglądu w panelu bocznym.
                "birth": p.birth_date,
                "birthPlace": p.birth_place,
                "death": p.death_date,
                "deathPlace": p.death_place,
                "burial": p.burial_place,
                "bio": p.bio,
                "x": p.tree_x,
                "y": p.tree_y,
                "url": reverse("family:person", args=[p.pk]),
                "portrait": _portrait(visible.get(p.portrait_id), p),
            }
            for p in people
        ],
        "parents": list(ParentChild.objects.values_list("parent_id", "child_id")),
        "partners": list(Partnership.objects.values_list("person1_id", "person2_id")),
        # ETAP 33: rodzeństwo bez wspólnego rodzica w drzewie.
        "siblings": list(Sibling.objects.values_list("person1_id", "person2_id")),
        # ETAP 31: rok ślubu (kolejność związków) i rozwód (linia przerywana).
        "couples": [
            {
                "a": c.person1_id,
                "b": c.person2_id,
                "since": c.since,
                "year": c.since_year,
                "ended": c.ended,
                "place": c.place,
            }
            for c in Partnership.objects.all()
            if c.since or c.ended or c.place
        ],
        "outside": [{"id": p.pk, "name": p.name, "count": p.count} for p in outside[:200]],
        "names": list(Person.objects.values_list("name", flat=True)),
        "canEdit": user.can_edit_tree,
    }


def _portrait(photo, person=None):
    if photo is None:
        return None
    url = f"{reverse('albums:thumb', args=[photo.pk])}?v={photo.version_front}"
    data = {"url": url, "turn": photo.pending_front}
    if person is not None:
        # ETAP 45: kadr portretu w kółku.
        data.update(x=person.portrait_x, y=person.portrait_y, zoom=person.portrait_zoom)
    return data


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
        place = body.get("place")
        tree.edit_couple(
            request.user,
            person,
            other,
            str(body.get("since") or ""),
            body.get("ended") is True,
            place=str(place) if place is not None else None,
        )
    except ValidationError as exc:
        return _error(exc.messages[0])
    return _ok(request)


PERSON_FIELDS = {
    "name": "name",
    "maiden": "maiden_name",
    "birth": "birth_date",
    "birthPlace": "birth_place",
    "death": "death_date",
    "deathPlace": "death_place",
    "burial": "burial_place",
    "bio": "bio",
    "gender": "gender",
}


CROP_FIELDS = {"portraitX": "portrait_x", "portraitY": "portrait_y", "portraitZoom": "portrait_zoom"}
# Tyle zdjęć osoby pokazuje okno wyboru portretu.
PORTRAITS_SHOWN = 200


@tree_access()
@require_http_methods(["GET", "HEAD", "POST"])
def person(request, pk):
    """Dane osoby do edycji w panelu bocznym (ETAP 34).

    GET: portrety do wyboru (zdjęcia z tą osobą, które widzi konto). POST: zapis jak „Edytuj dane”,
    ``{"name", "maiden", "birth", "birthPlace", "deceased", "death", "deathPlace", "bio", "portrait"}``.
    """
    person = Person.objects.filter(pk=pk).first()
    if person is None:
        return _error("Nie ma takiej osoby.", 404)
    portraits = visible_photos(request.user, person)
    if request.method != "POST":
        # Punkt osoby na zdjęciu (ETAP 44) podpowiada kadr: twarz trafia na środek kółka.
        marks = {mark.photo_id: [mark.x, mark.y] for mark in person.marks.all()}
        return JsonResponse(
            {
                "portrait": person.portrait_id if portraits.filter(pk=person.portrait_id).exists() else None,
                "crop": {"x": person.portrait_x, "y": person.portrait_y, "zoom": person.portrait_zoom},
                "portraits": [
                    {"id": photo.pk, **_portrait(photo), "mark": marks.get(photo.pk)}
                    for photo in portraits[:PORTRAITS_SHOWN]
                ],
            }
        )
    if not request.user.can_edit_tree:
        return _error("Nie masz prawa edycji drzewa.", 403)
    body = _body(request)
    data = {field: str(body.get(key) or "") for key, field in PERSON_FIELDS.items()}
    if body.get("deceased") is True:
        data["deceased"] = "on"
    for key, field in PERSON_FIELDS.items():
        if key not in body:
            # Strona otwarta przed aktualizacją nie zna nowych pól (płeć, pochówek): zostają dotychczasowe.
            data[field] = str(getattr(person, field) or "")
    portrait = body.get("portrait")
    data["portrait"] = str(portrait) if portrait else ""
    for key, field in CROP_FIELDS.items():
        if isinstance(body.get(key), (int, float)) and not isinstance(body.get(key), bool):
            data[field] = str(body[key])
    form = PersonForm(data, instance=person, portraits=portraits)
    before, old_name = tree.snapshot(person), person.name
    if not form.is_valid():
        errors = {key: form.errors[field][0] for key, field in PERSON_FIELDS.items() if field in form.errors}
        if "portrait" in form.errors:
            errors["portrait"] = form.errors["portrait"][0]
        return JsonResponse({"error": "Popraw zaznaczone pola.", "errors": errors}, status=400)
    person, notice = save_person(request.user, form, before, old_name)
    return _ok(request, notice=notice)
