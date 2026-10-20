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

    @property
    def path(self):
        return settings.ARCHIVEHUB_ALBUMS_DIR / self.folder


class Photo(models.Model):
    """Jedno zdjęcie w albumie: wersja do oglądania (JPEG) i miniatura (WebP), opcjonalnie z rewersem.

    Pliki leżą w folderze albumu: ``zdjecia/<nazwa>.jpg`` i ``miniatury/<nazwa>.webp``,
    rewers jako ``<nazwa>_r``. Oryginały skanów nie są przechowywane w bibliotece.
    """

    album = models.ForeignKey(Album, on_delete=models.CASCADE, related_name="photos")
    name = models.CharField("nazwa", max_length=200)
    source_name = models.CharField("plik źródłowy", max_length=255)
    position = models.PositiveIntegerField("kolejność", default=0)
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    checksum = models.CharField("suma kontrolna", max_length=64)
    has_reverse = models.BooleanField("ma rewers", default=False)
    reverse_checksum = models.CharField(max_length=64, blank=True)
    file_missing = models.BooleanField("brak pliku", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["album", "position", "pk"]
        verbose_name = "zdjęcie"
        verbose_name_plural = "zdjęcia"
        constraints = [
            models.UniqueConstraint(fields=["album", "name"], name="albums_photo_unique_name"),
            models.UniqueConstraint(fields=["album", "checksum"], name="albums_photo_unique_checksum"),
        ]

    def __str__(self):
        return f"{self.album.folder}/{self.name}"

    def web_path(self, reverse=False):
        return self.album.path / WEB_DIR / f"{self.file_stem(reverse)}.jpg"

    def thumb_path(self, reverse=False):
        return self.album.path / THUMB_DIR / f"{self.file_stem(reverse)}.webp"

    def file_stem(self, reverse=False):
        return f"{self.name}{settings.ARCHIVEHUB_REVERSE_SUFFIX}" if reverse else self.name


WEB_DIR = "zdjecia"
THUMB_DIR = "miniatury"


class ImportJob(models.Model):
    """Import jednego folderu z udziału ``import``. Każda zmiana zawartości folderu to nowy wpis."""

    WAITING = "waiting"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
    STATUSES = [
        (WAITING, "czeka na koniec kopiowania"),
        (PROCESSING, "importowanie"),
        (DONE, "zaimportowano"),
        (FAILED, "błąd"),
    ]

    folder = models.CharField(max_length=255)
    signature = models.CharField(max_length=64)
    status = models.CharField(max_length=20, choices=STATUSES, default=WAITING)
    stable_since = models.DateTimeField(default=timezone.now)
    album = models.ForeignKey(Album, null=True, blank=True, on_delete=models.SET_NULL, related_name="imports")
    photos_added = models.PositiveIntegerField(default=0)
    reverses_added = models.PositiveIntegerField(default=0)
    skipped = models.JSONField(default=list)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "import"
        verbose_name_plural = "importy"

    def __str__(self):
        return f"Import {self.folder} ({self.get_status_display()})"


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
    missing_photos = models.JSONField(default=list)
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
