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
