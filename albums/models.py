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


class PhotoQuerySet(models.QuerySet):
    def visible_to(self, user):
        """Zdjęcia z albumów, które dana osoba może oglądać."""
        # Każdy plik zdjęcia (miniatura, podgląd, oryginał) przechodzi przez to sprawdzenie.
        return self.filter(album__in=Album.objects.visible_to(user))


class Album(models.Model):
    """Album = jeden folder w bibliotece zdjęć (``ARCHIVEHUB_ALBUMS_DIR``).

    Albumy tworzy synchronizacja, nie ręczne dodawanie w panelu.
    """

    folder = models.CharField("folder", max_length=255, unique=True)
    title = models.CharField("tytuł", max_length=200)
    description = models.TextField("opis", blank=True)
    is_hidden = models.BooleanField("ukryty", default=False)
    # Folder z oryginalnymi skanami PNG na Google Drive (udostępnianie ustawia się w Drive).
    originals_url = models.URLField("link do oryginałów PNG", max_length=500, blank=True)
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

    def viewers(self):
        """Osoby (poza administratorem), które widzą ten album w archiwum."""
        from django.contrib.auth import get_user_model

        users = get_user_model().objects.filter(is_active=True, is_superuser=False)
        if self.is_hidden or self.folder_missing:
            return users.none()
        return (
            users.filter(
                models.Q(family_groups__in=self.groups.all()) | models.Q(family_groups__sees_all_albums=True)
            )
            .distinct()
            .order_by("username")
        )


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
    # Obrót zgodnie z ruchem wskazówek zegara (0, 90, 180, 270), ustawiany przez rodzinę w galerii.
    # *_applied: obrót, który worker zapisał już w plikach. Różnicę do tego czasu dokłada przeglądarka (CSS).
    rotation = models.PositiveSmallIntegerField("obrót", default=0)
    applied_rotation = models.PositiveSmallIntegerField(default=0)
    reverse_rotation = models.PositiveSmallIntegerField("obrót rewersu", default=0)
    reverse_applied_rotation = models.PositiveSmallIntegerField(default=0)
    rotated_at = models.DateTimeField(null=True, blank=True)
    rotated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    # Opis od rodziny (ETAP 13). Datę wpisuje się po ludzku (albums.dates), zakres lat służy do szukania.
    description = models.TextField("opis", max_length=2000, blank=True)
    date_text = models.CharField("data", max_length=60, blank=True)
    year_from = models.PositiveSmallIntegerField("rok od", null=True, blank=True, db_index=True)
    year_to = models.PositiveSmallIntegerField("rok do", null=True, blank=True)
    place = models.CharField("miejsce", max_length=200, blank=True)
    people = models.ManyToManyField("Person", blank=True, related_name="photos", verbose_name="osoby")
    tags = models.ManyToManyField("Tag", blank=True, related_name="photos", verbose_name="tagi")
    described_at = models.DateTimeField(null=True, blank=True)
    described_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # Opis, osoby, tagi i komentarze małymi literami, bez polskich znaków (albums.search).
    search_text = models.TextField(blank=True, editable=False)

    objects = PhotoQuerySet.as_manager()

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

    def target_rotation(self, reverse=False):
        return self.reverse_rotation if reverse else self.rotation

    def baked_rotation(self, reverse=False):
        return self.reverse_applied_rotation if reverse else self.applied_rotation

    def pending_rotation(self, reverse=False):
        """Obrót, którego jeszcze nie ma w plikach: tyle obraca obraz przeglądarka."""
        return (self.target_rotation(reverse) - self.baked_rotation(reverse)) % 360

    @property
    def pending_front(self):
        return self.pending_rotation()

    @property
    def pending_back(self):
        return self.pending_rotation(reverse=True)

    def file_version(self, reverse=False):
        # Dopisywane do adresów plików: po obróceniu pliku przeglądarka nie pokaże starej wersji z pamięci.
        return self.baked_rotation(reverse)

    @property
    def version_front(self):
        return self.file_version()

    @property
    def version_back(self):
        return self.file_version(reverse=True)

    def file_stem(self, reverse=False):
        return f"{self.name}{settings.ARCHIVEHUB_REVERSE_SUFFIX}" if reverse else self.name

    def caption(self):
        """Krótki podpis pod zdjęciem: data · miejsce · osoby (z prefetch_related("people") bez zapytań)."""
        names = ", ".join(person.name for person in self.people.all())
        return " · ".join(part for part in (self.date_text, self.place, names) if part)

    @property
    def is_described(self):
        return bool(self.described_at)


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


class Comment(models.Model):
    """Komentarz rodziny pod zdjęciem (wspólny dla awersu i rewersu), podpisany nickiem autora."""

    MAX_LENGTH = 2000

    photo = models.ForeignKey(
        Photo, on_delete=models.CASCADE, related_name="comments", verbose_name="zdjęcie"
    )
    # Po usunięciu konta komentarz zostaje, podpisany „konto usunięte”.
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="comments",
        verbose_name="autor",
    )
    text = models.TextField("treść", max_length=MAX_LENGTH)
    created_at = models.DateTimeField("dodano", default=timezone.now, db_index=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = "komentarz"
        verbose_name_plural = "komentarze"

    def __str__(self):
        return f"{self.author or 'konto usunięte'} o {self.photo}: {self.text[:40]}"

    def can_delete(self, user):
        """Własny komentarz usuwa autor, każdy inny administrator."""
        return user.is_superuser or (self.author_id is not None and self.author_id == user.pk)


class NamedQuerySet(models.QuerySet):
    def get_or_create_named(self, name):
        """Ta sama nazwa bez względu na wielkość liter (także „Ł” i „ł”) to ten sam wpis."""
        name = " ".join(name.split())
        found = self.filter(key=name_key(name)).first()
        return found or self.create(name=name)


def name_key(name):
    return " ".join(name.split()).casefold()


class NamedModel(models.Model):
    """Osoba albo tag: nazwa do wyświetlenia i klucz bez wielkości liter (SQLite nie zna polskich liter)."""

    MAX_LENGTH = 100

    name = models.CharField("nazwa", max_length=MAX_LENGTH)
    key = models.CharField(max_length=MAX_LENGTH, unique=True, editable=False)

    objects = NamedQuerySet.as_manager()

    class Meta:
        abstract = True
        ordering = ["key"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.name = " ".join(self.name.split())
        self.key = name_key(self.name)
        super().save(*args, **kwargs)


class Person(NamedModel):
    """Osoba rozpoznana przez rodzinę na zdjęciach (bez rozpoznawania twarzy)."""

    class Meta(NamedModel.Meta):
        verbose_name = "osoba"
        verbose_name_plural = "osoby"


class Tag(NamedModel):
    class Meta(NamedModel.Meta):
        verbose_name = "tag"
        verbose_name_plural = "tagi"


class PhotoChange(models.Model):
    """Jedna zmiana opisu zdjęcia: kto, kiedy i co (``{"pole": [przed, po]}``). Pozwala cofnąć pomyłkę."""

    photo = models.ForeignKey(Photo, on_delete=models.CASCADE, related_name="changes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    changes = models.JSONField(default=dict)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "zmiana opisu"
        verbose_name_plural = "zmiany opisów"

    def __str__(self):
        return f"{self.user or 'konto usunięte'}: {self.photo} ({', '.join(self.changes)})"
