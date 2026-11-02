"""Operacje na drzewie: relacje z kontrolą błędów i zapis każdej zmiany do historii."""

from django.core.exceptions import ValidationError
from django.db import transaction

from albums.dates import DateError, parse_date
from albums.models import Person, Photo, name_key
from albums.search import refresh_search_text

from .models import ParentChild, Partnership, TreeChange

# Pola osoby, które zapisuje historia (i które ETAP 23 przywraca).
PERSON_FIELDS = [
    "name",
    "maiden_name",
    "birth_date",
    "birth_place",
    "death_date",
    "death_place",
    "bio",
    "portrait_id",
    "in_tree",
]
FIELD_LABELS = {
    "name": "imię i nazwisko",
    "maiden_name": "nazwisko rodowe",
    "birth_date": "data urodzenia",
    "birth_place": "miejsce urodzenia",
    "death_date": "data śmierci",
    "death_place": "miejsce śmierci",
    "bio": "historia",
    "portrait_id": "portret",
}

PARENT, CHILD, PARTNER = "rodzic", "dziecko", "partner"
AUTO = object()  # drugi rodzic nowego dziecka: jedyny partner rodzica, jeśli jest
RELATION_KINDS = {PARENT: "rodzic", CHILD: "dziecko", PARTNER: "partner / partnerka"}
MAX_PARENTS = 2


def parents(person):
    return Person.objects.filter(child_links__child=person)


def children(person):
    return Person.objects.filter(parent_links__parent=person)


def partners(person):
    ids = (
        Partnership.objects.filter(person1=person)
        .values_list("person2", flat=True)
        .union(Partnership.objects.filter(person2=person).values_list("person1", flat=True))
    )
    return Person.objects.filter(pk__in=list(ids))


def _links(person):
    return {
        "parents": sorted(parents(person).values_list("pk", flat=True)),
        "children": sorted(children(person).values_list("pk", flat=True)),
        "partners": sorted(partners(person).values_list("pk", flat=True)),
    }


def snapshot(person, with_links=False):
    data = {field: getattr(person, field) for field in PERSON_FIELDS}
    if with_links:
        data["links"] = _links(person)
    return data


def _record(user, kind, person, summary, before=None, after=None, reverts=None):
    return TreeChange.objects.create(
        user=user,
        kind=kind,
        person=person,
        summary=summary[:300],
        before=before or {},
        after=after or {},
        reverts=reverts,
    )


def _ancestor_ids(person):
    seen, frontier = set(), {person.pk}
    while frontier:
        frontier = set(ParentChild.objects.filter(child__in=frontier).values_list("parent", flat=True)) - seen
        seen |= frontier
    return seen


def _put_in_tree(user, person):
    if not person.in_tree:
        before = snapshot(person)
        person.in_tree = True
        person.save(update_fields=["in_tree"])
        _record(
            user,
            TreeChange.PERSON_ADDED,
            person,
            f"Dodano do drzewa: {person.name}",
            before,
            snapshot(person),
        )


@transaction.atomic
def add_person(user, name):
    """Nowa osoba w drzewie albo osoba ze zdjęć o tej nazwie (bez względu na wielkość liter)."""
    person = Person.objects.get_or_create_named(name)
    _put_in_tree(user, person)
    return person


def _create_link(person, other, kind):
    """Sprawdza i tworzy relację. Zwraca jej zapis do historii i opis."""
    if other.pk == person.pk:
        raise ValidationError("Osoba nie może być spokrewniona sama ze sobą.")
    if kind == PARENT:
        parent, child = other, person
    elif kind == CHILD:
        parent, child = person, other
    elif kind == PARTNER:
        parent = child = None
    else:
        raise ValidationError("Nieznany rodzaj relacji.")

    if kind == PARTNER:
        first, second = sorted([person, other], key=lambda p: p.pk)
        if Partnership.objects.filter(person1=first, person2=second).exists():
            raise ValidationError(f"{other.name} już jest partnerem lub partnerką tej osoby.")
        Partnership.objects.create(person1=first, person2=second)
        data = {"kind": PARTNER, "person1": first.pk, "person2": second.pk}
        summary = f"Para: {person.name} i {other.name}"
    else:
        if ParentChild.objects.filter(parent=parent, child=child).exists():
            raise ValidationError(f"{parent.name} już jest rodzicem: {child.name}.")
        if ParentChild.objects.filter(child=child).count() >= MAX_PARENTS:
            raise ValidationError(f"{child.name} ma już dwoje rodziców.")
        if parent.pk == child.pk or child.pk in _ancestor_ids(parent):
            raise ValidationError(
                f"{child.name} jest przodkiem: {parent.name}. Takie połączenie zrobiłoby pętlę."
            )
        if parent.pk in {p.pk for p in partners(child)}:
            raise ValidationError(f"{parent.name} i {child.name} są już parą.")
        ParentChild.objects.create(parent=parent, child=child)
        data = {"kind": "rodzic-dziecko", "parent": parent.pk, "child": child.pk}
        summary = f"{parent.name} jest rodzicem: {child.name}"
    return data, summary


@transaction.atomic
def add_relation(user, person, other, kind, reverts=None, second_parent=AUTO):
    """``other`` zostaje rodzicem, dzieckiem albo partnerem osoby ``person``.

    Dziecko w drzewie pochodzi od pary: nowe dziecko osoby z jednym partnerem dostaje od razu oboje
    rodziców (``second_parent`` wskazuje drugiego rodzica wprost albo ``None``, gdy go nie ma), a drugi
    rodzic dziecka zostaje parą z pierwszym. Każde takie połączenie jest osobnym wpisem w historii.
    """
    data, summary = _create_link(person, other, kind)
    _put_in_tree(user, person)
    _put_in_tree(user, other)
    change = _record(user, TreeChange.RELATION_ADDED, person, summary, after=data, reverts=reverts)
    if kind in (PARENT, CHILD) and reverts is None:
        parent, child = (other, person) if kind == PARENT else (person, other)
        if kind == CHILD:
            _add_second_parent(user, parent, child, second_parent)
        _pair_parents(user, child)
    return change


def _add_second_parent(user, parent, child, second):
    automatic = second is AUTO
    if automatic:
        if ParentChild.objects.filter(child=child).count() != 1:
            return
        mates = list(partners(parent))
        second = mates[0] if len(mates) == 1 else None
    if second is None or second.pk in {p.pk for p in parents(child)}:
        return
    try:
        with transaction.atomic():
            data, summary = _create_link(child, second, PARENT)
    except ValidationError:
        if automatic:
            return  # np. partner jest dzieckiem tej osoby: zostaje jeden rodzic
        raise
    _put_in_tree(user, second)
    _record(user, TreeChange.RELATION_ADDED, child, summary, after=data)


def _pair_parents(user, child):
    """Dwoje rodziców jednego dziecka to para (także gdy się rozstali): linia dziecka idzie od pary."""
    pair = sorted(parents(child), key=lambda p: p.pk)
    if len(pair) != 2 or Partnership.objects.filter(person1=pair[0], person2=pair[1]).exists():
        return
    Partnership.objects.create(person1=pair[0], person2=pair[1])
    data = {"kind": PARTNER, "person1": pair[0].pk, "person2": pair[1].pk}
    _record(
        user,
        TreeChange.RELATION_ADDED,
        pair[0],
        f"Para: {pair[0].name} i {pair[1].name} (rodzice: {child.name})",
        after=data,
    )


@transaction.atomic
def remove_relation(user, person, other, kind, reverts=None):
    if kind == PARTNER:
        first, second = sorted([person, other], key=lambda p: p.pk)
        deleted, _ = Partnership.objects.filter(person1=first, person2=second).delete()
        data = {"kind": PARTNER, "person1": first.pk, "person2": second.pk}
        summary = f"Usunięto parę: {person.name} i {other.name}"
    else:
        parent, child = (other, person) if kind == PARENT else (person, other)
        deleted, _ = ParentChild.objects.filter(parent=parent, child=child).delete()
        data = {"kind": "rodzic-dziecko", "parent": parent.pk, "child": child.pk}
        summary = f"Usunięto: {parent.name} jako rodzic {child.name}"
    if not deleted:
        return None
    return _record(user, TreeChange.RELATION_REMOVED, person, summary, before=data, reverts=reverts)


@transaction.atomic
def edit_person(user, person, before, reverts=None):
    """Zapisuje do historii, co się zmieniło względem ``before`` (snapshot sprzed edycji)."""
    after = snapshot(person)
    changed = [field for field in FIELD_LABELS if before.get(field) != after.get(field)]
    if not changed:
        return None
    labels = ", ".join(FIELD_LABELS[field] for field in changed)
    return _record(
        user,
        TreeChange.PERSON_EDITED,
        person,
        f"{person.name}: zmiana ({labels})",
        {field: before[field] for field in changed},
        {field: after[field] for field in changed},
        reverts,
    )


@transaction.atomic
def remove_from_tree(user, person, reverts=None):
    """Zdejmuje osobę z drzewa razem z relacjami. Osoba i jej oznaczenia na zdjęciach zostają."""
    before = snapshot(person, with_links=True)
    ParentChild.objects.filter(parent=person).delete()
    ParentChild.objects.filter(child=person).delete()
    Partnership.objects.filter(person1=person).delete()
    Partnership.objects.filter(person2=person).delete()
    person.in_tree = False
    person.tree_x = person.tree_y = None
    person.save(update_fields=["in_tree", "tree_x", "tree_y"])
    return _record(
        user,
        TreeChange.PERSON_REMOVED,
        person,
        f"Usunięto z drzewa: {person.name}",
        before,
        snapshot(person),
        reverts,
    )


@transaction.atomic
def merge_into(source, target):
    """Panel łączy dwie osoby o tej samej nazwie: relacje i puste dane drzewa przechodzą na ``target``."""
    for link in ParentChild.objects.filter(parent=source):
        if (
            link.child_id != target.pk
            and not ParentChild.objects.filter(parent=target, child=link.child).exists()
        ):
            ParentChild.objects.create(parent=target, child=link.child)
    for link in ParentChild.objects.filter(child=source):
        if (
            link.parent_id != target.pk
            and not ParentChild.objects.filter(parent=link.parent, child=target).exists()
        ):
            ParentChild.objects.create(parent=link.parent, child=target)
    for other in partners(source):
        if other.pk != target.pk:
            first, second = sorted([target, other], key=lambda p: p.pk)
            Partnership.objects.get_or_create(person1=first, person2=second)
    for field in PERSON_FIELDS:
        if field != "name" and not getattr(target, field) and getattr(source, field):
            setattr(target, field, getattr(source, field))
    if target.birth_date and not target.birth_year:
        target.birth_year = source.birth_year
    if target.death_date and not target.death_year:
        target.death_year = source.death_year
    target.save()
    # Historia zostaje przy osobie, która zostaje po połączeniu.
    TreeChange.objects.filter(person=source).update(person=target)


# --- Cofanie zmian (Panel → Drzewo → „Przywróć”) -----------------------------------------------


def sort_year(text):
    """Rok do sortowania z tekstu daty: środek zakresu („lata 20.” → 1924)."""
    try:
        date = parse_date(text)
    except DateError:
        return None
    return (date.year_from + date.year_to) // 2 if date else None


def _link_from(data):
    """Zapis relacji z historii jako (osoba, druga osoba, kim druga jest dla pierwszej)."""
    if data.get("kind") == PARTNER:
        ids, kind = [data.get("person1"), data.get("person2")], PARTNER
    else:
        ids, kind = [data.get("child"), data.get("parent")], PARENT
    people = Person.objects.in_bulk([pk for pk in ids if pk])
    if len(people) < 2:
        raise ValidationError("Jednej z tych osób nie ma już w archiwum, więc nie da się tego cofnąć.")
    return people[ids[0]], people[ids[1]], kind


def _person_of(change):
    if change.person is None:
        raise ValidationError("Tej osoby nie ma już w archiwum, więc nie da się tego cofnąć.")
    return change.person


def _restore_fields(user, person, values, change):
    before = snapshot(person)
    old_name = person.name
    for field, value in values.items():
        if field not in FIELD_LABELS:
            continue
        if field == "name":
            clash = Person.objects.filter(key=name_key(value)).exclude(pk=person.pk).first()
            if clash:
                raise ValidationError(f"Nazwę „{value}” ma teraz inna osoba, więc nie da się jej przywrócić.")
        if field == "portrait_id" and value and not Photo.objects.filter(pk=value).exists():
            value = None
        setattr(person, field, value)
    person.birth_year = sort_year(person.birth_date)
    person.death_year = sort_year(person.death_date)
    person.save()
    if person.name != old_name:
        refresh_search_text(list(person.photos.values_list("pk", flat=True)))
    return edit_person(user, person, before, reverts=change)


def _restore_person(user, person, before, change):
    """Wraca osobę do drzewa razem z relacjami, które da się odtworzyć."""
    old = snapshot(person)
    person.in_tree = True
    person.save(update_fields=["in_tree"])
    links = before.get("links", {})
    wanted = (
        [(pk, PARENT) for pk in links.get("parents", [])]
        + [(pk, CHILD) for pk in links.get("children", [])]
        + [(pk, PARTNER) for pk in links.get("partners", [])]
    )
    others = Person.objects.in_bulk([pk for pk, _ in wanted])
    skipped = []
    for pk, kind in wanted:
        other = others.get(pk)
        if other is None:
            continue
        try:
            with transaction.atomic():
                _create_link(person, other, kind)
        except ValidationError:
            skipped.append(other.name)
            continue
        _put_in_tree(user, other)
    summary = f"Przywrócono do drzewa: {person.name}"
    if skipped:
        summary += f" (bez połączeń z: {', '.join(skipped)})"
    return _record(
        user, TreeChange.PERSON_ADDED, person, summary, old, snapshot(person, with_links=True), change
    )


@transaction.atomic
def undo(user, change):
    """Cofa zmianę z historii. Cofnięcie zapisuje się jako nowa zmiana, więc i je można cofnąć."""
    change = TreeChange.objects.select_for_update().get(pk=change.pk)
    if change.reverted_by.exists():
        raise ValidationError("Ta zmiana jest już cofnięta.")
    kind = change.kind
    if kind == TreeChange.RELATION_ADDED:
        person, other, relation = _link_from(change.after)
        result = remove_relation(user, person, other, relation, reverts=change)
        if not result:
            raise ValidationError("Tej relacji już nie ma w drzewie.")
    elif kind == TreeChange.RELATION_REMOVED:
        person, other, relation = _link_from(change.before)
        result = add_relation(user, person, other, relation, reverts=change)
    elif kind == TreeChange.PERSON_EDITED:
        result = _restore_fields(user, _person_of(change), change.before, change)
        if result is None:
            raise ValidationError("Dane tej osoby już są takie jak przed zmianą.")
    elif kind == TreeChange.PERSON_ADDED:
        person = _person_of(change)
        if not person.in_tree:
            raise ValidationError(f"{person.name} już nie jest w drzewie.")
        result = remove_from_tree(user, person, reverts=change)
    elif kind == TreeChange.PERSON_REMOVED:
        person = _person_of(change)
        if person.in_tree:
            raise ValidationError(f"{person.name} już jest w drzewie.")
        result = _restore_person(user, person, change.before, change)
    else:
        raise ValidationError("Nieznany rodzaj zmiany.")
    return result


def _show(field, value):
    if field == "portrait_id":
        return f"zdjęcie nr {value}" if value else ""
    return value or ""


def edit_rows(change):
    """Zmienione pola jako (co, było, jest), do Panel → Drzewo."""
    if change.kind != TreeChange.PERSON_EDITED:
        return []
    return [
        (FIELD_LABELS[field], _show(field, change.before.get(field)), _show(field, change.after.get(field)))
        for field in change.after
        if field in FIELD_LABELS
    ]


def link_rows(change, names):
    """Krewni zapisani przy usunięciu albo przywróceniu osoby, jako (kto, nazwy)."""
    data = change.before if change.kind == TreeChange.PERSON_REMOVED else change.after
    links = data.get("links") or {}
    rows = []
    for key, label in (("parents", "rodzice"), ("partners", "partnerzy"), ("children", "dzieci")):
        people = ", ".join(names.get(pk, "osoba usunięta z archiwum") for pk in links.get(key, []))
        if people:
            rows.append((label, people))
    return rows


def related_ids(change):
    """Id osób z zapisów relacji, żeby pokazać ich nazwy."""
    ids = set()
    for data in (change.before, change.after):
        for pks in (data.get("links") or {}).values():
            ids.update(pks)
    return ids
