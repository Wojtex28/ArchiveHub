from django.conf import settings

from .theme import current_theme


def site(request):
    return {"site_title": settings.SITE_TITLE, "theme": current_theme(request)}
