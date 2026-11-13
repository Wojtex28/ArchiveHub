"""Sprawdzanie drzewa (ETAP 55): rzeczy, które wyglądają na pomyłkę w danych.

Każda uwaga to :class:`Issue` z osobami, których dotyczy. Część to prawie na pewno błąd (np. troje
rodziców), część tylko „do sprawdzenia” (np. duża różnica wieku). Uwagę „to się zgadza” można
schować (:class:`family.models.CheckDismissal`), a wraca, gdy zmienią się dane, których dotyczy.

Uwagi o układzie (rodzeństwo w różnych rzędach drzewa) liczy kanwa, bo tylko ona zna rzędy.
"""

import hashlib
from dataclasses import dataclass, field

from albums.models import Person

from .models import CheckDismissal, ParentChild, Partnership, Sibling

ERROR = "blad"
WARNING = "uwaga"

# Granice wieku rodzica w chwili narodzin dziecka (w latach).
PARENT_MIN_AGE = 14
MOTHER_MAX_AGE = 55
FATHER_MAX_AGE = 80
PARTNER_GAP = 30


@dataclass
class Issue:
    kind: str
    level: str
    text: str
    people: list = field(default_factory=list)  # [(id, imię i nazwisko)]
    detail: str = ""  # stan danych, od którego zależy uwaga (zmiana danych przywraca schowaną)

    @property
    def key(self):
        ids = ",".join(str(pk) for pk, _ in sorted(self.people))
        return hashlib.sha256(f"{self.kind}|{ids}|{self.detail}".encode()).hexdigest()[:20]

    def as_dict(self):
        return {
            "key": self.key,
            "kind": self.kind,
            "level": self.level,
            "text": self.text,
            "people": [{"id": pk, "name": name} for pk, name in self.people],
        }


class _Graph:
    def __init__(self):
        people = Person.objects.filter(in_tree=True)
        self.person = {p.pk: p for p in people}
        self.parents = {pk: set() for pk in self.person}
        self.children = {pk: set() for pk in self.person}
        self.partners = {pk: set() for pk in self.person}
        self.siblings = {pk: set() for pk in self.person}
        for parent, child in ParentChild.objects.values_list("parent_id", "child_id"):
            if parent in self.person and child in self.person:
                self.parents[child].add(parent)
                self.children[parent].add(child)
        for a, b in Partnership.objects.values_list("person1_id", "person2_id"):
            if a in self.person and b in self.person:
                self.partners[a].add(b)
                self.partners[b].add(a)
        for a, b in Sibling.objects.values_list("person1_id", "person2_id"):
            if a in self.person and b in self.person:
                self.siblings[a].add(b)
                self.siblings[b].add(a)

    def who(self, *ids):
        return [(pk, self.person[pk].name) for pk in ids]

    def ancestors(self, pk, depth=None):
        """Przodkowie z odległością w pokoleniach: {id: najmniejsza odległość}."""
        found, frontier, level = {}, {pk}, 0
        while frontier and (depth is None or level < depth):
            level += 1
            nxt = set()
            for item in frontier:
                for parent in self.parents[item]:
                    if parent not in found:
                        found[parent] = level
                        nxt.add(parent)
            frontier = nxt
        return found


def _born(person):
    return person.birth_year


def _died(person):
    return person.death_year


def _relation(graph, a, b):
    """Bliskie pokrewieństwo dwóch osób jako słowo („rodzeństwo”, „kuzynostwo”) albo None."""
    up_a, up_b = graph.ancestors(a, 3), graph.ancestors(b, 3)
    if b in up_a or a in up_b:
        level = up_a.get(b) or up_b.get(a)
        return {1: "rodzic i dziecko", 2: "dziadek/babcia i wnuk"}.get(level, "przodek i potomek")
    if b in graph.siblings[a]:
        return "rodzeństwo"
    common = set(up_a) & set(up_b)
    if not common:
        return None
    best = min(common, key=lambda pk: (up_a[pk] + up_b[pk], pk))
    steps = sorted((up_a[best], up_b[best]))
    return {
        (1, 1): "rodzeństwo",
        (1, 2): "ciocia/wujek i siostrzeniec/bratanek",
        (2, 2): "kuzynostwo",
    }.get(tuple(steps))


def find_issues():
    graph = _Graph()
    issues = []
    people = graph.person

    for pk, person in people.items():
        born, died = _born(person), _died(person)
        if born is not None and died is not None and died < born:
            issues.append(
                Issue(
                    "smierc",
                    ERROR,
                    f"Rok śmierci ({died}) jest wcześniejszy niż rok urodzenia ({born}).",
                    graph.who(pk),
                    f"{born}-{died}",
                )
            )
        ps = sorted(graph.parents[pk])
        if len(ps) > 2:
            issues.append(
                Issue(
                    "rodzice",
                    ERROR,
                    f"{person.name} ma {len(ps)} rodziców. Może któryś z nich to dziadek albo babcia?",
                    graph.who(pk, *ps),
                )
            )
        # Rodzic i dziadek jednocześnie: dziecko podpięte też do rodziców swojego rodzica.
        for parent in ps:
            for grand in sorted(graph.parents[parent]):
                if grand in graph.parents[pk]:
                    issues.append(
                        Issue(
                            "dziadek",
                            ERROR,
                            f"{people[grand].name} jest zapisany jako rodzic osoby {person.name} "
                            f"i jednocześnie jako rodzic jej rodzica ({people[parent].name}).",
                            graph.who(pk, parent, grand),
                        )
                    )
        if born is None:
            continue
        for parent in ps:
            p = people[parent]
            p_born, p_died = _born(p), _died(p)
            if p_born is not None:
                age = born - p_born
                limit = MOTHER_MAX_AGE if p.gender == "K" else FATHER_MAX_AGE
                if age < 0:
                    text = (
                        f"{p.name} (ur. {p_born}) jest młodszy(-a) niż dziecko: {person.name} (ur. {born})."
                    )
                    level = ERROR
                elif age < PARENT_MIN_AGE:
                    text = f"{p.name} miał(a) {age} lat, gdy urodziło się dziecko: {person.name}."
                    level = ERROR
                elif age > limit:
                    text = f"{p.name} miał(a) {age} lat, gdy urodziło się dziecko: {person.name}."
                    level = WARNING
                else:
                    text = ""
                if text:
                    issues.append(Issue("wiek", level, text, graph.who(parent, pk), f"{p_born}-{born}"))
            # Ojciec mógł umrzeć przed narodzinami (rok zapasu), matka nie.
            if p_died is not None and born > p_died + (0 if p.gender == "K" else 1):
                issues.append(
                    Issue(
                        "po-smierci",
                        ERROR,
                        f"{person.name} urodził(a) się w {born}, a {p.name} zmarł(a) w {p_died}.",
                        graph.who(parent, pk),
                        f"{p_died}-{born}",
                    )
                )

    seen = set()
    for a in people:
        for b in graph.partners[a]:
            if (b, a) in seen:
                continue
            seen.add((a, b))
            pa, pb = people[a], people[b]
            word = _relation(graph, a, b)
            if word:
                issues.append(
                    Issue(
                        "krewni",
                        ERROR if word in ("rodzeństwo", "rodzic i dziecko") else WARNING,
                        f"{pa.name} i {pb.name} są parą, a w drzewie wychodzi {word}.",
                        graph.who(a, b),
                    )
                )
            if _born(pa) is not None and _born(pb) is not None and abs(_born(pa) - _born(pb)) > PARTNER_GAP:
                issues.append(
                    Issue(
                        "para-wiek",
                        WARNING,
                        f"{pa.name} i {pb.name}: {abs(_born(pa) - _born(pb))} lat różnicy wieku.",
                        graph.who(a, b),
                        f"{_born(pa)}-{_born(pb)}",
                    )
                )

    # Ta sama osoba wpisana dwa razy: imię i nazwisko jak u kogoś z tymi samymi rodzicami albo rokiem.
    by_name = {}
    for pk, person in people.items():
        by_name.setdefault(person.name.casefold(), []).append(pk)
    for ids in by_name.values():
        for i, a in enumerate(ids):
            for b in ids[i + 1 :]:
                pa, pb = people[a], people[b]
                same_parents = graph.parents[a] and graph.parents[a] == graph.parents[b]
                same_year = _born(pa) is not None and _born(pa) == _born(pb)
                if same_parents or same_year:
                    issues.append(
                        Issue(
                            "dwa-razy",
                            WARNING,
                            f"{pa.name} jest w drzewie dwa razy (te same "
                            f"{'rodzice' if same_parents else 'lata'}). Może to jedna osoba?",
                            graph.who(a, b),
                        )
                    )
    return issues


def issues_for(user=None):
    """Uwagi bez schowanych („to się zgadza”), najpierw błędy."""
    hidden = set(CheckDismissal.objects.values_list("key", flat=True))
    found = [issue for issue in find_issues() if issue.key not in hidden]
    return sorted(found, key=lambda issue: (issue.level != ERROR, issue.kind, issue.text))
