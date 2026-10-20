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
    # Kolejność w archiwum; nowy album trafia na koniec.
    position = models.PositiveIntegerField("kolejność", default=0)
    cover = models.ForeignKey(
        "Photo",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="okładka",
    )
    folder_missing = models.BooleanField("brak folderu", default=False)
    photo_count = models.PositiveIntegerField("liczba zdjęć", default=0)
    # Ustawiane w panelu; worker importu przetwarza wtedy album jeszcze raz ze skanów w udziale.
    reprocess_requested = models.BooleanField("do ponownego przetworzenia", default=False)
    groups = models.ManyToManyField(FamilyGroup, blank=True, related_name="albums", verbose_name="grupy")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = AlbumQuerySet.as_manager()

    class Meta:
        ordering = ["position", "folder"]
        verbose_name = "album"
        verbose_name_plural = "albumy"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self._state.adding and not self.position:
            top = Album.objects.aggregate(top=models.Max("position"))["top"] or 0
            self.position = top + 1
        super().save(*args, **kwargs)

    @property
    def cover_photo(self):
        """Okładka wybrana w panelu, a bez niej pierwsze zdjęcie albumu."""
        if self.cover_id and not self.cover.file_missing:
            return self.cover
        return self.photos.filter(file_missing=False).first()

    @property
    def path(self):
        return settings.ARCHIVEHUB_ALBUMS_DIR / self.folder


class Photo(models.Model):
    """Jedno zdjęcie w albumie: wersja do oglądania (JPEG) i miniatura (WebP), opcjonalnie z rewersem.

    Pliki leżą w folderze albumu:
    ``oryginaly/<nazwa>.jpg``: pełna rozdzielczość skanu, do pobrania;
    ``podglad/<nazwa>.jpg``: do oglądania na ekranie;
    ``miniatury/<nazwa>.webp``: do siatki zdjęć.
    Rewers ma te same pliki z końcówką ``_r``. Skany PNG/TIFF z udziału nie są przechowywane w bibliotece.
    """

    album = models.ForeignKey(Album, on_delete=models.CASCADE, related_name="photos")
    name = models.CharField("nazwa", max_length=200)
    source_name = models.CharField("plik źródłowy", max_length=255)
    position = models.PositiveIntegerField("kolejność", default=0)
    # Rozmiar oryginału (pełna rozdzielczość).
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

    def original_path(self, reverse=False):
        return self.album.path / ORIGINAL_DIR / f"{self.file_stem(reverse)}.jpg"

    def preview_path(self, reverse=False):
        return self.album.path / PREVIEW_DIR / f"{self.file_stem(reverse)}.jpg"

    def legacy_path(self, reverse=False):
        """Wersja 5000 px z pierwszego wydania importu; zastępuje ją ponowne przetworzenie."""
        return self.album.path / LEGACY_WEB_DIR / f"{self.file_stem(reverse)}.jpg"

    def files_present(self):
        has_full = self.original_path().is_file() and self.preview_path().is_file()
        return self.thumb_path().is_file() and (has_full or self.legacy_path().is_file())

    def thumb_path(self, reverse=False):
        return self.album.path / THUMB_DIR / f"{self.file_stem(reverse)}.webp"

    def file_stem(self, reverse=False):
        return f"{self.name}{settings.ARCHIVEHUB_REVERSE_SUFFIX}" if reverse else self.name


ORIGINAL_DIR = "oryginaly"
PREVIEW_DIR = "podglad"
THUMB_DIR = "miniatury"
LEGACY_WEB_DIR = "zdjecia"


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
    is_reprocess = models.BooleanField("ponowne przetworzenie", default=False)
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
