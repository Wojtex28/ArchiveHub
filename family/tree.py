"""Operacje na drzewie: relacje z kontrolą błędów i zapis każdej zmiany do historii."""

from django.core.exceptions import ValidationError
from django.db import models, transaction

from albums.dates import DateError, parse_date
from albums.models import Person, Photo, name_key
from albums.search import refresh_search_text

from .models import LifeEvent, ParentChild, Partnership, Sibling, TreeChange

# Pola osoby, które zapisuje historia (i które ETAP 23 przywraca).
PERSON_FIELDS = [
    "name",
    "maiden_name",
    "birth_date",
    "birth_place",
    "death_date",
    "death_place",
    "burial_place",
    "deceased",
    "bio",
    "portrait_id",
    "gender",
    "in_tree",
]
FIELD_LABELS = {
    "name": "imię i nazwisko",
    "maiden_name": "nazwisko rodowe",
    "birth_date": "data urodzenia",
    "birth_place": "miejsce urodzenia",
    "death_date": "data śmierci",
    "death_place": "miejsce śmierci",
    "burial_place": "pochówek",
    "deceased": "czy żyje",
    "bio": "historia",
    "portrait_id": "portret",
    "gender": "płeć",
}

PARENT, CHILD, PARTNER, SIBLING = "rodzic", "dziecko", "partner", "rodzenstwo"
AUTO = object()  # drugi rodzic nowego dziecka: jedyny partner rodzica, jeśli jest
RELATION_KINDS = {
    PARENT: "rodzic",
    CHILD: "dziecko",
    PARTNER: "partner / partnerka",
    SIBLING: "brat / siostra",
}
PAIR_KINDS = {PARTNER: Partnership, SIBLING: Sibling}
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


def linked_siblings(person):
    """Rodzeństwo zapisane wprost (``Sibling``), bez rodzeństwa przez wspólnego rodzica."""
    ids = (
        Sibling.objects.filter(person1=person)
        .values_list("person2", flat=True)
        .union(Sibling.objects.filter(person2=person).values_list("person1", flat=True))
    )
    return Person.objects.filter(pk__in=list(ids))


def siblings(person):
    """Całe rodzeństwo: przez wspólnego rodzica i zapisane wprost. Każdy ma ``linked`` (da się usunąć)."""
    linked = {p.pk for p in linked_siblings(person)}
    by_parent = set(
        ParentChild.objects.filter(parent__in=parents(person))
        .exclude(child=person)
        .values_list("child", flat=True)
    )
    people = list(Person.objects.filter(pk__in=linked | by_parent))
    people.sort(key=lambda p: (p.birth_year is None, p.birth_year or 0, p.name))
    for p in people:
        p.linked = p.pk in linked and p.pk not in by_parent
    return people


def _links(person):
    return {
        "parents": sorted(parents(person).values_list("pk", flat=True)),
        "children": sorted(children(person).values_list("pk", flat=True)),
        "partners": sorted(partners(person).values_list("pk", flat=True)),
        "siblings": sorted(linked_siblings(person).values_list("pk", flat=True)),
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


@transaction.atomic
def put_in_tree(user, person):
    _put_in_tree(user, person)
    return person


# --- Imiennicy (ETAP 26) -------------------------------------------------------------
# Dwie osoby mogą nazywać się tak samo (dziadek i wnuk „Jan Bereza”). Wpisana nazwa nie wskazuje więc
# jednoznacznie osoby: gdy jest już zajęta, pytamy, czy chodzi o kogoś z archiwum, czy o nową osobę.

NEW = "nowa"


class NeedsChoice(Exception):
    """W archiwum są już osoby o tej nazwie: trzeba zapytać, czy to któraś z nich."""

    def __init__(self, name, matches):
        super().__init__(name)
        self.name = name
        self.matches = matches

    @property
    def message(self):
        return f"W archiwum jest już „{self.name}”. Wybierz, czy to ta sama osoba, czy jej imiennik."


def same_name(name):
    return Person.objects.filter(key=name_key(name)).order_by(*Person.NAMESAKE_ORDER)


def _photo_count(n):
    if n == 1:
        return "1 zdjęcie"
    few = 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14
    return f"{n} zdjęcia" if few else f"{n} zdjęć"


def namesake_info(person, user):
    """Imiennik do wyboru: po czym rozpoznać, o kogo chodzi (lata, rodzina, liczba zdjęć)."""
    facts = []
    if person.maiden_name:
        facts.append(f"z d. {person.maiden_name}")
    if person.years:
        facts.append(person.years)
    facts.append("w drzewie" if person.in_tree else "spoza drzewa")
    parent_names = [p.name for p in parents(person)]
    if parent_names:
        facts.append("rodzice: " + ", ".join(parent_names))
    partner_names = [p.name for p in partners(person)]
    if partner_names:
        facts.append("partner/ka: " + ", ".join(partner_names))
    photos = Photo.objects.visible_to(user).filter(people=person).count()
    if photos:
        facts.append(_photo_count(photos))
    return {"id": person.pk, "name": person.name, "inTree": person.in_tree, "facts": " · ".join(facts)}


def person_for(name, who=None):
    """Osoba wpisana w formularzu drzewa.

    ``who``: ``NEW`` (nowa osoba, także gdy ktoś już tak się nazywa), id osoby o tej nazwie albo ``None``.
    Przy ``None`` i zajętej nazwie rzuca :class:`NeedsChoice`, żeby nie połączyć cicho dwóch różnych ludzi.
    """
    name = " ".join(name.split())
    if who == NEW:
        return Person.objects.create(name=name)
    matches = list(same_name(name))
    if who not in (None, ""):
        for person in matches:
            if str(person.pk) == str(who):
                return person
        raise ValidationError("Wybierz osobę z listy.")
    if not matches:
        return Person.objects.create(name=name)
    raise NeedsChoice(name, matches)


def _create_link(person, other, kind):
    """Sprawdza i tworzy relację. Zwraca jej zapis do historii i opis."""
    if other.pk == person.pk:
        raise ValidationError("Osoba nie może być spokrewniona sama ze sobą.")
    if kind == PARENT:
        parent, child = other, person
    elif kind == CHILD:
        parent, child = person, other
    elif kind in (PARTNER, SIBLING):
        parent = child = None
    else:
        raise ValidationError("Nieznany rodzaj relacji.")

    if kind == SIBLING:
        first, second = sorted([person, other], key=lambda p: p.pk)
        if Sibling.objects.filter(person1=first, person2=second).exists():
            raise ValidationError(f"{other.name} już jest rodzeństwem tej osoby.")
        family = _ancestor_ids(person) | {c.pk for c in _descendants(person)}
        family |= {p.pk for p in partners(person)}
        if other.pk in family:
            raise ValidationError(f"{other.name} jest już w tej rodzinie kimś innym niż rodzeństwo.")
        Sibling.objects.create(person1=first, person2=second)
        data = {"kind": SIBLING, "person1": first.pk, "person2": second.pk}
        summary = f"Rodzeństwo: {person.name} i {other.name}"
    elif kind == PARTNER:
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


def _descendants(person):
    seen, frontier = set(), {person.pk}
    while frontier:
        frontier = set(ParentChild.objects.filter(parent__in=frontier).values_list("child", flat=True)) - seen
        seen |= frontier
    return Person.objects.filter(pk__in=seen)


@transaction.atomic
def add_relation(user, person, other, kind, reverts=None, second_parent=AUTO):
    """``other`` zostaje rodzicem, dzieckiem albo partnerem osoby ``person``.

    Dziecko w drzewie pochodzi od pary: nowe dziecko osoby z jednym partnerem dostaje od razu oboje
    rodziców (``second_parent`` wskazuje drugiego rodzica wprost albo ``None``, gdy go nie ma), a drugi
    rodzic dziecka zostaje parą z pierwszym. Każde takie połączenie jest osobnym wpisem w historii.
    """
    if kind == SIBLING and reverts is None:
        return _add_sibling(user, person, other)
    data, summary = _create_link(person, other, kind)
    _put_in_tree(user, person)
    _put_in_tree(user, other)
    change = _record(user, TreeChange.RELATION_ADDED, person, summary, after=data, reverts=reverts)
    if kind in (PARENT, CHILD) and reverts is None:
        parent, child = (other, person) if kind == PARENT else (person, other)
        if kind == CHILD:
            _add_second_parent(user, parent, child, second_parent)
        _pair_parents(user, child)
        share_parents(user, child)
    return change


def _add_parent_link(user, child, parent):
    data, summary = _create_link(child, parent, PARENT)
    _put_in_tree(user, parent)
    return _record(user, TreeChange.RELATION_ADDED, child, summary, after=data)


def _add_sibling(user, person, other):
    """``other`` zostaje bratem lub siostrą osoby ``person`` (ETAP 33).

    Gdy któreś z nich ma rodziców w drzewie, drugie dostaje tych samych rodziców (rodzeństwo wynika
    wtedy z rodziców). Gdy nikt nie ma rodziców, zostaje zapis ``Sibling`` łączący całe rodzeństwo.
    """
    if other.pk == person.pk:
        raise ValidationError("Osoba nie może być spokrewniona sama ze sobą.")
    _put_in_tree(user, person)
    _put_in_tree(user, other)
    mine, theirs = list(parents(person)), list(parents(other))
    if mine or theirs:
        source, target = (person, other) if mine else (other, person)
        have = {p.pk for p in parents(target)}
        missing = [p for p in parents(source) if p.pk not in have]
        if not missing:
            raise ValidationError(f"{other.name} już jest rodzeństwem tej osoby.")
        if len(have) + len(missing) > MAX_PARENTS:
            raise ValidationError(
                f"{target.name} ma już innych rodziców w drzewie. Dodaj rodzica ręcznie albo usuń "
                "niepotrzebne połączenie."
            )
        changes = [_add_parent_link(user, target, p) for p in missing]
        _pair_parents(user, target)
        share_parents(user, target)
        return changes[0]
    # Nikt nie ma rodziców: łączymy całe rodzeństwo obu osób ze sobą.
    group_a = [person] + list(linked_siblings(person))
    group_b = [other] + list(linked_siblings(other))
    if other.pk in {p.pk for p in group_a}:
        raise ValidationError(f"{other.name} już jest rodzeństwem tej osoby.")
    first = None
    for a in group_a:
        for b in group_b:
            if a.pk == b.pk:
                continue
            pair = sorted([a, b], key=lambda p: p.pk)
            if Sibling.objects.filter(person1=pair[0], person2=pair[1]).exists():
                continue
            data, summary = _create_link(a, b, SIBLING)
            change = _record(user, TreeChange.RELATION_ADDED, a, summary, after=data)
            first = first or change
    return first


def share_parents(user, child):
    """Rodzic dodany komuś z rodzeństwa (zapis ``Sibling``) staje się też rodzicem reszty rodzeństwa."""
    mine = list(parents(child))
    if not mine:
        return
    for other in linked_siblings(child):
        have = {p.pk for p in parents(other)}
        added = False
        for parent in mine:
            if parent.pk in have or len(have) >= MAX_PARENTS:
                continue
            try:
                with transaction.atomic():
                    _add_parent_link(user, other, parent)
            except ValidationError:
                continue
            have.add(parent.pk)
            added = True
        if added:
            _pair_parents(user, other)


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
    if kind == SIBLING:
        first, second = sorted([person, other], key=lambda p: p.pk)
        deleted, _ = Sibling.objects.filter(person1=first, person2=second).delete()
        data = {"kind": SIBLING, "person1": first.pk, "person2": second.pk}
        summary = f"Usunięto rodzeństwo: {person.name} i {other.name}"
    elif kind == PARTNER:
        first, second = sorted([person, other], key=lambda p: p.pk)
        couple = Partnership.objects.filter(person1=first, person2=second).first()
        data = {"kind": PARTNER, "person1": first.pk, "person2": second.pk}
        if couple is not None:
            data.update(_couple_data(couple))
        deleted, _ = Partnership.objects.filter(person1=first, person2=second).delete()
        summary = f"Usunięto parę: {person.name} i {other.name}"
    else:
        parent, child = (other, person) if kind == PARENT else (person, other)
        deleted, _ = ParentChild.objects.filter(parent=parent, child=child).delete()
        data = {"kind": "rodzic-dziecko", "parent": parent.pk, "child": child.pk}
        summary = f"Usunięto: {parent.name} jako rodzic {child.name}"
    if not deleted:
        return None
    return _record(user, TreeChange.RELATION_REMOVED, person, summary, before=data, reverts=reverts)


# --- Związki (ETAP 31) ----------------------------------------------------------------------------

COUPLE_LABELS = {"since": "rok ślubu", "place": "miejsce ślubu", "ended": "rozwód"}


def couple(person, other):
    first, second = sorted([person, other], key=lambda p: p.pk)
    return Partnership.objects.filter(person1=first, person2=second).first()


def _couple_data(couple):
    return {"since": couple.since, "place": couple.place, "ended": couple.ended}


def partners_in_order(person):
    """Partnerzy osoby od pierwszego związku: wg roku ślubu, bez roku na końcu w kolejności dodania.

    Każdy ma atrybut ``couple`` (Partnership) i ``couple_text``.
    """
    couples = Partnership.objects.filter(models.Q(person1=person) | models.Q(person2=person))
    couples = sorted(couples, key=lambda c: (c.since_year is None, c.since_year or 0, c.pk))

    def other_id(c):
        return c.person2_id if c.person1_id == person.pk else c.person1_id

    people = Person.objects.in_bulk([other_id(c) for c in couples])
    result = []
    for c in couples:
        other = people[other_id(c)]
        other.couple, other.couple_text = c, couple_text(c)
        result.append(other)
    return result


def couple_text(couple):
    """„ślub 1950 · rozwód” do list i karty osoby."""
    wedding = " ".join(filter(None, ["ślub", couple.since, f"({couple.place})" if couple.place else ""]))
    parts = [wedding if couple.since or couple.place else "", "rozwód" if couple.ended else ""]
    return " · ".join(part for part in parts if part)


@transaction.atomic
def edit_couple(user, person, other, since, ended, reverts=None, place=None):
    """Rok i miejsce ślubu, rozwód pary. Zwraca wpis historii albo ``None``, gdy nic się nie zmieniło.

    ``place=None`` zostawia miejsce ślubu bez zmian (strona otwarta przed ETAP 47 go nie wysyła).
    """
    pair = couple(person, other)
    if pair is None:
        raise ValidationError(f"{person.name} i {other.name} nie są parą.")
    try:
        date = parse_date(" ".join(str(since or "").split()))
    except DateError as exc:
        raise ValidationError(str(exc)) from None
    before = _couple_data(pair)
    pair.since = date.text if date else ""
    pair.since_year = (date.year_from + date.year_to) // 2 if date else None
    pair.ended = bool(ended)
    if place is not None:
        pair.place = " ".join(str(place).split())[:200]
    after = _couple_data(pair)
    changed = [field for field in COUPLE_LABELS if before[field] != after[field]]
    if not changed:
        return None
    pair.save()
    ids = {"kind": PARTNER, "person1": pair.person1_id, "person2": pair.person2_id}
    labels = ", ".join(COUPLE_LABELS[field] for field in changed)
    return _record(
        user,
        TreeChange.COUPLE_EDITED,
        person,
        f"Para {person.name} i {other.name}: zmiana ({labels})",
        {**ids, **{field: before[field] for field in changed}},
        {**ids, **{field: after[field] for field in changed}},
        reverts,
    )


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
    Sibling.objects.filter(models.Q(person1=person) | models.Q(person2=person)).delete()
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
    for other in linked_siblings(source):
        if other.pk != target.pk:
            first, second = sorted([target, other], key=lambda p: p.pk)
            Sibling.objects.get_or_create(person1=first, person2=second)
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


# --- Zdarzenia z życia (ETAP 46) ------------------------------------------------------------

EVENT_LABELS = {
    "kind": "rodzaj",
    "title": "tytuł",
    "date": "kiedy",
    "until": "do kiedy",
    "place": "miejsce",
    "note": "notatka",
    "photo": "zdjęcie",
    "on_timeline": "na osi czasu",
}
EVENT_TEXT = [field for field in EVENT_LABELS if field not in ("photo", "on_timeline")]


def event_data(event):
    return {
        "id": event.pk,
        **{field: getattr(event, field) for field in EVENT_TEXT},
        "photo": event.photo_id,
        "on_timeline": event.on_timeline,
    }


@transaction.atomic
def save_event(user, person, values, event=None, reverts=None):
    """Dodaje zdarzenie albo zapisuje zmiany w istniejącym. Zwraca wpis historii (None bez zmian)."""
    before = event_data(event) if event else {}
    event = event or LifeEvent(person=person)
    for field in EVENT_TEXT:
        setattr(event, field, values.get(field, "") or "")
    # ETAP 54: historia sprzed tej wersji nie zna miejsca na osi, więc zostaje dotychczasowe
    # (a nowe zdarzenie dostaje domyślne dla swojego rodzaju).
    if values.get("on_timeline") is not None:
        event.on_timeline = bool(values["on_timeline"])
    elif event.pk is None:
        event.on_timeline = event.kind not in LifeEvent.OFF_TIMELINE
    photo = values.get("photo")
    photo_id = getattr(photo, "pk", photo) or None
    # Zdjęcie usunięte z archiwum po zapisaniu historii: zdarzenie wraca bez niego.
    event.photo_id = photo_id if photo_id and Photo.objects.filter(pk=photo_id).exists() else None
    event.year = sort_year(event.date) or sort_year(event.until)
    after = {**before, **event_data(event), "id": before.get("id")}
    if before == after:
        return None
    event.save()
    after["id"] = event.pk
    verb = "zmieniono zdarzenie" if before else "dodano zdarzenie"
    summary = f"{person.name}: {verb} ({event.heading})"
    return _record(user, TreeChange.EVENT_CHANGED, person, summary, before, after, reverts)


@transaction.atomic
def remove_event(user, event, reverts=None):
    before, person = event_data(event), event.person
    summary = f"{person.name}: usunięto zdarzenie ({event.heading})"
    event.delete()
    return _record(user, TreeChange.EVENT_CHANGED, person, summary, before, {}, reverts)


def _undo_event(user, change):
    person = _person_of(change)
    current = LifeEvent.objects.filter(pk=change.after.get("id"), person=person).first()
    if not change.before:
        if current is None:
            raise ValidationError("Tego zdarzenia już nie ma.")
        return remove_event(user, current, reverts=change)
    if change.after and current is None:
        raise ValidationError(
            "Tego zdarzenia już nie ma, więc nie da się przywrócić jego poprzedniej treści."
        )
    result = save_event(user, person, change.before, event=current, reverts=change)
    if result is None:
        raise ValidationError("To zdarzenie już jest takie jak przed zmianą.")
    return result


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
    if data.get("kind") in (PARTNER, SIBLING):
        ids, kind = [data.get("person1"), data.get("person2")], data["kind"]
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
        + [(pk, SIBLING) for pk in links.get("siblings", [])]
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
        if relation == PARTNER and any(change.before.get(f) for f in ("since", "place", "ended")):
            Partnership.objects.filter(
                person1=change.before["person1"], person2=change.before["person2"]
            ).update(
                place=change.before.get("place", ""),
                since=change.before.get("since", ""),
                since_year=sort_year(change.before.get("since", "")),
                ended=bool(change.before.get("ended")),
            )
    elif kind == TreeChange.COUPLE_EDITED:
        person, other, _ = _link_from(change.before)
        pair = couple(person, other)
        if pair is None:
            raise ValidationError("Tej pary już nie ma w drzewie.")
        values = {**_couple_data(pair), **{f: change.before[f] for f in COUPLE_LABELS if f in change.before}}
        result = edit_couple(
            user, person, other, values["since"], values["ended"], reverts=change, place=values["place"]
        )
        if result is None:
            raise ValidationError("Ta para już jest taka jak przed zmianą.")
    elif kind == TreeChange.EVENT_CHANGED:
        result = _undo_event(user, change)
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
    if field == "deceased":
        return "nie żyje" if value else "żyje"
    if field == "portrait_id":
        return f"zdjęcie nr {value}" if value else ""
    if field == "gender":
        return dict(Person.GENDERS).get(value or "", "")
    return value or ""


def _show_couple(field, value):
    if field == "ended":
        return "tak" if value else "nie"
    return value or ""


def edit_rows(change):
    """Zmienione pola jako (co, było, jest), do Panel → Drzewo."""
    if change.kind == TreeChange.COUPLE_EDITED:
        return [
            (label, _show_couple(f, change.before.get(f)), _show_couple(f, change.after.get(f)))
            for f, label in COUPLE_LABELS.items()
            if f in change.after
        ]
    if change.kind == TreeChange.EVENT_CHANGED:
        kinds = dict(LifeEvent.KINDS)

        def show(f, data):
            if f == "kind":
                return kinds.get(data.get(f), "")
            if f == "photo":
                return f"zdjęcie nr {data[f]}" if data.get(f) else ""
            if f == "on_timeline":
                return {True: "tak", False: "nie, pod osią"}.get(data.get(f), "")
            return data.get(f) or ""

        return [
            (label, show(f, change.before), show(f, change.after))
            for f, label in EVENT_LABELS.items()
            if change.before.get(f) != change.after.get(f)
        ]
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
    for key, label in (
        ("parents", "rodzice"),
        ("partners", "partnerzy"),
        ("siblings", "rodzeństwo"),
        ("children", "dzieci"),
    ):
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
