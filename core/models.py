import uuid

from django.conf import settings
from django.db import models


class LoginPhoto(models.Model):
    """Zdjęcie pływające w tle strony logowania.

    To czysta dekoracja, niezależna od albumów. Strona logowania jest publiczna,
    więc te zdjęcia widzi każdy, kto zna adres archiwum.
    """

    key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    is_active = models.BooleanField("pokazuj", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = "zdjęcie w tle logowania"
        verbose_name_plural = "zdjęcia w tle logowania"

    def __str__(self):
        return f"{self.key}.jpg"

    @property
    def path(self):
        return settings.ARCHIVEHUB_LOGIN_PHOTOS_DIR / f"{self.key}.jpg"


class Event(models.Model):
    """Wpis dziennika: logowania, zmiany zabezpieczeń, ostrzeżenia i błędy (podgląd w panelu).

    Pełne logi zbiera Docker; tu trafia tylko to, co administrator powinien zobaczyć bez Shella.
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    level = models.PositiveSmallIntegerField()
    source = models.CharField(max_length=100)
    message = models.TextField()

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.source}: {self.message[:60]}"

    @property
    def is_problem(self):
        return self.level >= 30  # logging.WARNING
