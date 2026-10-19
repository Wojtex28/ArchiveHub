from django.conf import settings
from django.db import models
from django.utils import timezone

from accounts.models import FamilyGroup


class AlbumQuerySet(models.QuerySet):
    def visible_to(self, user):
        """Albumy, które dana osoba może oglądać.

        Administrator widzi wszystko. Pozostali: albumy nieukryte, których folder istnieje,
        przypisane do jednej z ich grup. Grupa „widzi wszystkie albumy” daje dostęp do
        każdego takiego albumu, także dodanego później.
        """
        if not (user.is_authenticated and user.is_active):
            return self.none()
        if user.is_superuser:
            return self
        available = self.filter(is_hidden=False, folder_missing=False)
        groups = user.family_groups.all()
        if groups.filter(sees_all_albums=True).exists():
            return available
        return available.filter(groups__in=groups).distinct()


class Album(models.Model):
    """Album = jeden folder w bibliotece zdjęć (``ARCHIVEHUB_ALBUMS_DIR``).

    Albumy tworzy synchronizacja, nie ręczne dodawanie w panelu.
    """

    folder = models.CharField("folder", max_length=255, unique=True)
    title = models.CharField("tytuł", max_length=200)
    description = models.TextField("opis", blank=True)
    is_hidden = models.BooleanField("ukryty", default=False)
    folder_missing = models.BooleanField("brak folderu", default=False)
    photo_count = models.PositiveIntegerField("liczba zdjęć", default=0)
    groups = models.ManyToManyField(FamilyGroup, blank=True, related_name="albums", verbose_name="grupy")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = AlbumQuerySet.as_manager()

    class Meta:
        ordering = ["folder"]
        verbose_name = "album"
        verbose_name_plural = "albumy"

    def __str__(self):
        return self.title


class SyncReport(models.Model):
    """Wynik jednej synchronizacji biblioteki z bazą."""

    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    albums_total = models.PositiveIntegerField(default=0)
    photos_total = models.PositiveIntegerField(default=0)
    new_albums = models.JSONField(default=list)
    missing_albums = models.JSONField(default=list)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "raport synchronizacji"
        verbose_name_plural = "raporty synchronizacji"

    def __str__(self):
        return f"Synchronizacja {self.started_at:%Y-%m-%d %H:%M}"

    @property
    def ok(self):
        return not self.error
