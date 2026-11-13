from django.conf import settings
from django.utils.functional import SimpleLazyObject

from .theme import current_theme


def _has_own_albums(request):
    from albums.models import UserAlbum

    user = getattr(request, "user", None)
    return bool(user and user.is_authenticated and UserAlbum.objects.filter(user=user).exists())


def site(request):
    return {
        "site_title": settings.SITE_TITLE,
        "theme": current_theme(request),
        # Gwiazdka ☆ otwiera wybór albumu tylko u kogoś, kto ma „Moje albumy” (ETAP 51).
        # Leniwie: zapytanie idzie tylko na stronach, które o to pytają.
        "has_own_albums": SimpleLazyObject(lambda: _has_own_albums(request)),
    }
