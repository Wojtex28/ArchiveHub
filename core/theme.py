"""Tryb nocny (ETAP 40).

Wybór zapamiętuje ciasteczko ``motyw`` w przeglądarce (nie konto), więc działa też na stronie
logowania. Bez ciasteczka strona idzie za ustawieniem systemu (``prefers-color-scheme`` w CSS).
"""

from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

COOKIE = "motyw"
# Wartość ciasteczka -> atrybut data-theme na <html>.
THEMES = {"ciemny": "dark", "jasny": "light"}
ONE_YEAR = 365 * 24 * 60 * 60


def current_theme(request):
    """Zwraca „dark”, „light” albo pusty napis (bez wyboru: jak w systemie)."""
    return THEMES.get(request.COOKIES.get(COOKIE, ""), "")


@require_POST
def set_theme(request):
    """Przełącznik bez JavaScriptu (z JavaScriptem ciasteczko ustawia static/js/theme.js)."""
    choice = request.POST.get(COOKIE, "")
    target = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(target, {request.get_host()}, require_https=request.is_secure()):
        target = reverse("archive")
    response = HttpResponseRedirect(target)
    if choice in THEMES:
        response.set_cookie(COOKIE, choice, max_age=ONE_YEAR, samesite="Lax", secure=request.is_secure())
    else:
        response.delete_cookie(COOKIE)
    return response
