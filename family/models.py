"""Drzewo rodzinne: relacje między osobami ze zdjęć i historia zmian.

Węzłem drzewa jest ``albums.Person``: ta sama osoba, którą rodzina oznacza na zdjęciach.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from albums.models import Person


class ParentChild(models.Model):
    parent = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="child_links")
    child = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="parent_links")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["parent", "child"], name="family_parent_child_unique"),
            models.CheckConstraint(
                condition=~models.Q(parent=models.F("child")), name="family_not_own_parent"
            ),
        ]
        verbose_name = "rodzic i dziecko"
        verbose_name_plural = "rodzice i dzieci"

    def __str__(self):
        return f"{self.parent} → {self.child}"


class Partnership(models.Model):
    """Para (małżeństwo albo związek). ``person1`` ma zawsze mniejsze id, więc para jest jedna."""

    person1 = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="+")
    person2 = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="+")
    # ETAP 31: kilku partnerów jednej osoby. Rok ślubu ustala kolejność (1. związek po lewej,
    # 2. po prawej), rozwód rysuje linię przerywaną. Oba pola są opcjonalne.
    since = models.CharField("rok ślubu", max_length=60, blank=True)
    since_year = models.SmallIntegerField(null=True, blank=True, editable=False)
    ended = models.BooleanField("rozwód lub rozstanie", default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["person1", "person2"], name="family_partnership_unique"),
            models.CheckConstraint(
                condition=models.Q(person1__lt=models.F("person2")), name="family_partner_order"
            ),
        ]
        verbose_name = "para"
        verbose_name_plural = "pary"

    def __str__(self):
        return f"{self.person1} + {self.person2}"


class Sibling(models.Model):
    """Rodzeństwo bez wspólnego rodzica w drzewie (ETAP 33): np. brat osoby, której rodziców nikt nie dodał.

    Rodzeństwo ze wspólnym rodzicem wynika z ``ParentChild`` i nie potrzebuje tego zapisu. Gdy ktoś
    z rodzeństwa dostaje rodzica, reszta dostaje go też (``tree.share_parents``).
    """

    person1 = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="+")
    person2 = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["person1", "person2"], name="family_sibling_unique"),
            models.CheckConstraint(
                condition=models.Q(person1__lt=models.F("person2")), name="family_sibling_order"
            ),
        ]
        verbose_name = "rodzeństwo"
        verbose_name_plural = "rodzeństwo"

    def __str__(self):
        return f"{self.person1} i {self.person2} (rodzeństwo)"


class TreeChange(models.Model):
    """Jedna zmiana w drzewie: kto, kiedy, co. ``before``/``after`` pozwalają ją cofnąć (``tree.undo``)."""

    PERSON_ADDED = "person_added"
    PERSON_EDITED = "person_edited"
    PERSON_REMOVED = "person_removed"
    RELATION_ADDED = "relation_added"
    RELATION_REMOVED = "relation_removed"
    COUPLE_EDITED = "couple_edited"
    KINDS = [
        (PERSON_ADDED, "dodanie osoby"),
        (PERSON_EDITED, "zmiana danych"),
        (PERSON_REMOVED, "usunięcie z drzewa"),
        (RELATION_ADDED, "dodanie relacji"),
        (RELATION_REMOVED, "usunięcie relacji"),
        (COUPLE_EDITED, "zmiana związku"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    kind = models.CharField(max_length=20, choices=KINDS)
    person = models.ForeignKey(Person, null=True, on_delete=models.SET_NULL, related_name="tree_changes")
    summary = models.CharField(max_length=300)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    # Ta zmiana cofa inną (Panel → Drzewo → „Przywróć”). Cofnięcie też da się cofnąć.
    reverts = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="reverted_by"
    )

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "zmiana w drzewie"
        verbose_name_plural = "zmiany w drzewie"

    def __str__(self):
        return self.summary
