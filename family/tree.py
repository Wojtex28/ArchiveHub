"""Operacje na drzewie: relacje z kontrolą błędów i zapis każdej zmiany do historii."""

from django.core.exceptions import ValidationError
from django.db import transaction

from albums.models import Person

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


def _record(user, kind, person, summary, before=None, after=None):
    return TreeChange.objects.create(
        user=user, kind=kind, person=person, summary=summary[:300], before=before or {}, after=after or {}
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


@transaction.atomic
def add_relation(user, person, other, kind):
    """``other`` zostaje rodzicem, dzieckiem albo partnerem osoby ``person``."""
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
    _put_in_tree(user, person)
    _put_in_tree(user, other)
    return _record(user, TreeChange.RELATION_ADDED, person, summary, after=data)


@transaction.atomic
def remove_relation(user, person, other, kind):
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
    if deleted:
        _record(user, TreeChange.RELATION_REMOVED, person, summary, before=data)
    return bool(deleted)


@transaction.atomic
def edit_person(user, person, before):
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
    )


@transaction.atomic
def remove_from_tree(user, person):
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
        user, TreeChange.PERSON_REMOVED, person, f"Usunięto z drzewa: {person.name}", before, snapshot(person)
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
