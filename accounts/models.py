from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


class FamilyGroup(models.Model):
    """Grupa osób, np. „Bereza” albo „Najbliższa rodzina”.

    Kod rodzinny przypisuje do grupy; od ETAPU 6 grupy dostają dostęp do albumów.
    """

    name = models.CharField("nazwa", max_length=60, unique=True)
    description = models.CharField("opis", max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "grupa"
        verbose_name_plural = "grupy"

    def __str__(self):
        return self.name


class User(AbstractUser):
    """Konto w archiwum.

    Login (``username``) to nick wybrany przy dołączaniu, np. „Karolina”.
    Wielkość liter nie ma znaczenia przy logowaniu i przy sprawdzaniu, czy nick jest wolny.
    """

    display_name = models.CharField("imię wyświetlane", max_length=60, blank=True)
    family_groups = models.ManyToManyField(
        FamilyGroup, blank=True, related_name="members", verbose_name="grupy"
    )
    joined_with_code = models.ForeignKey(
        "InviteCode",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="joined_users",
        verbose_name="dołączył(a) kodem",
    )

    class Meta:
        verbose_name = "użytkownik"
        verbose_name_plural = "użytkownicy"
        constraints = [
            models.UniqueConstraint(Lower("username"), name="accounts_user_username_ci_unique"),
        ]

    def __str__(self):
        return self.display_name or self.username


class InviteCode(models.Model):
    """Kod rodzinny: pozwala założyć konto i od razu przypisuje do grupy."""

    code = models.CharField("kod", max_length=60, unique=True)
    group = models.ForeignKey(
        FamilyGroup, on_delete=models.PROTECT, related_name="invite_codes", verbose_name="grupa"
    )
    note = models.CharField("notatka", max_length=200, blank=True)
    is_active = models.BooleanField("aktywny", default=True)
    max_uses = models.PositiveIntegerField("limit użyć", null=True, blank=True)
    expires_at = models.DateTimeField("ważny do", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "kod rodzinny"
        verbose_name_plural = "kody rodzinne"

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = self.normalize(self.code)
        super().save(*args, **kwargs)

    @staticmethod
    def normalize(raw):
        return " ".join(raw.split()).lower()

    @property
    def uses(self):
        return self.joined_users.count()

    def unusable_reason(self, now=None):
        """Zwraca powód, dla którego kodu nie można użyć, albo None."""
        now = now or timezone.now()
        if not self.is_active:
            return "wyłączony"
        if self.expires_at and self.expires_at <= now:
            return "wygasł"
        if self.max_uses is not None and self.uses >= self.max_uses:
            return "wykorzystany"
        return None


class FailedAttempt(models.Model):
    """Nieudana próba logowania lub podania kodu; podstawa limitu prób."""

    scope = models.CharField(max_length=20)
    key = models.CharField(max_length=200)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [models.Index(fields=["scope", "key", "created_at"])]

    def __str__(self):
        return f"{self.scope} {self.key}"
