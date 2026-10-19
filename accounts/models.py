from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Konto w archiwum.

    Własny model od pierwszego dnia, żeby w kolejnych etapach (kody rodzinne,
    grupy) można było go rozszerzać bez trudnej migracji.
    """

    display_name = models.CharField("imię wyświetlane", max_length=60, blank=True)

    class Meta:
        verbose_name = "użytkownik"
        verbose_name_plural = "użytkownicy"

    def __str__(self):
        return self.display_name or self.username
