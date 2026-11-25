import logging
import re

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import FileResponse, Http404, HttpResponse, HttpResponsePermanentRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.http import require_safe

from albums.collections import own_album_cards
from albums.display import album_cards
from albums.favorites import favorite_photos
from albums.models import Album, Photo
from family.anniversaries import anniversaries, next_anniversary

from . import status
from .models import LoginPhoto

logger = logging.getLogger(__name__)


# Tyle zdjęć leży „na stole” na stronie głównej.
LANDING_PHOTOS = 5


def plural(number, one, few, many):
    """Polska odmiana: 1 album, 2 albumy, 5 albumów, 22 albumy, 12 albumów."""
    if number == 1:
        return f"{number} {one}"
    if number % 10 in (2, 3, 4) and number % 100 not in (12, 13, 14):
        return f"{number} {few}"
    return f"{number} {many}"


def _album_photos(user):
    """Losowe zdjęcia z albumów, które ta osoba widzi (każde prowadzi do swojej strony)."""
    photos = (
        Photo.objects.visible_to(user)
        .filter(file_missing=False, album__folder_missing=False)
        .select_related("album")
        .order_by("?")[:LANDING_PHOTOS]
    )
    return [
        {
            "src": f"{reverse('albums:thumb', args=[photo.pk])}?v={photo.version_front}",
            "href": reverse("albums:photo", args=[photo.album_id, photo.pk]),
            "rotation": photo.pending_front,
            "alt": f"Zdjęcie z albumu {photo.album.display_title}",
        }
        for photo in photos
    ]


def _public_photos():
    """Dla niezalogowanych tylko zdjęcia z tła logowania: te administrator wybrał jako publiczne."""
    photos = LoginPhoto.objects.filter(is_active=True).order_by("?")[:LANDING_PHOTOS]
    return [
        {"src": reverse("login_photo", args=[photo.key]), "href": None, "rotation": 0, "alt": ""}
        for photo in photos
    ]


@require_safe
def landing(request):
    """Strona główna: kilka zdjęć rozrzuconych jak na stole i wejście do archiwum."""
    context = {}
    if request.user.is_authenticated:
        albums = Album.objects.visible_to(request.user).filter(folder_missing=False)
        photos = Photo.objects.visible_to(request.user).filter(
            file_missing=False, album__folder_missing=False
        )
        context["cards"] = _album_photos(request.user)
        context["stats"] = (
            f"{plural(albums.count(), 'album', 'albumy', 'albumów')} · "
            f"{plural(photos.count(), 'zdjęcie', 'zdjęcia', 'zdjęć')}"
        )
    else:
        context["cards"] = _public_photos()
    return render(request, "core/landing.html", context)


VIEW_COOKIE = "albumy_widok"
VIEWS = ("kafelki", "lista")
# 0.61.0: kolejność albumów na stronie archiwum (jak w Panelu, według lat albo w grupach).
SORT_COOKIE = "albumy_kolejnosc"
SORTS = {"domyslnie": "Domyślnie", "lata": "Chronologicznie", "grupy": "Według grup"}
NO_GROUP = "Pozostałe"


def _first_year(card):
    if card.album.year_from:
        return card.album.year_from
    match = re.search(r"\d{4}", card.years or "")
    return int(match[0]) if match else None


def _by_years(cards):
    """Od najstarszych; albumy bez lat na końcu, w kolejności z Panelu."""
    return sorted(cards, key=lambda c: (_first_year(c) is None, _first_year(c) or 0))


def _by_groups(cards, user):
    """Sekcje według grup (kodów rodzinnych). Album w kilku grupach jest w każdej z nich.

    Zwykła osoba widzi sekcje tylko swoich grup; administrator i grupy „widzi wszystkie albumy”
    widzą wszystkie grupy.
    """
    shown = None
    if not user.is_superuser and not user.family_groups.filter(sees_all_albums=True).exists():
        shown = set(user.family_groups.values_list("pk", flat=True))
    links = Album.groups.through.objects.filter(album_id__in=[c.album.pk for c in cards]).select_related(
        "familygroup"
    )
    groups_of = {}
    for link in links:
        if shown is None or link.familygroup_id in shown:
            groups_of.setdefault(link.album_id, []).append(link.familygroup)
    sections = {}
    rest = []
    for card in cards:
        groups = groups_of.get(card.album.pk)
        if not groups:
            rest.append(card)
        for group in groups or []:
            sections.setdefault(group.name, []).append(card)
    result = [{"title": name, "cards": sections[name]} for name in sorted(sections, key=str.lower)]
    if rest:
        result.append({"title": NO_GROUP, "cards": rest})
    return result


@require_safe
@login_required
def archive_home(request):
    albums = Album.objects.visible_to(request.user)
    if request.user.is_superuser:
        albums = albums.filter(folder_missing=False)
    # Kafelki albo lista (ETAP 50). Wybór zapamiętuje ciasteczko; bez JavaScriptu działa link ?widok=.
    chosen = request.GET.get("widok")
    layout = chosen if chosen in VIEWS else request.COOKIES.get(VIEW_COOKIE)
    if layout not in VIEWS:
        layout = VIEWS[0]
    sort_chosen = request.GET.get("sort")
    sort = sort_chosen if sort_chosen in SORTS else request.COOKIES.get(SORT_COOKIE)
    if sort not in SORTS:
        sort = "domyslnie"
    cards = album_cards(albums, request.user)
    if sort == "lata":
        cards = _by_years(cards)
    sections = _by_groups(cards, request.user) if sort == "grupy" else [{"title": "", "cards": cards}]
    favorites = favorite_photos(request.user)
    response = render(
        request,
        "core/archive_home.html",
        {
            "cards": cards,
            "sections": sections,
            "sort": sort,
            "sorts": SORTS,
            "layout": layout,
            "favorite_count": favorites.count(),
            "favorite_cover": favorites.first(),
            "own_albums": own_album_cards(request.user),
            **_anniversaries(request.user),
        },
    )
    if chosen in VIEWS:
        response.set_cookie(VIEW_COOKIE, chosen, max_age=365 * 24 * 3600, samesite="Lax")
    if sort_chosen in SORTS:
        response.set_cookie(SORT_COOKIE, sort_chosen, max_age=365 * 24 * 3600, samesite="Lax")
    return response


def _anniversaries(user):
    """Rocznice nad albumami (ETAP 58), dla osób, które widzą drzewo."""
    if not user.can_view_tree:
        return {}
    found = anniversaries()
    upcoming = None if found else next_anniversary()
    shown = found + ([upcoming] if upcoming else [])
    portraits = {p.portrait_id for a in shown for p in a.people if p.portrait_id}
    visible = set(Photo.objects.visible_to(user).filter(pk__in=portraits).values_list("pk", flat=True))
    for item in shown:
        for person in item.people:
            person.visible_portrait = person.portrait if person.portrait_id in visible else None
    return {"anniversaries": found, "next_anniversary": upcoming, "today": timezone.localdate()}


@require_safe
def login_photo(request, key):
    """Zdjęcie z tła strony logowania. Publiczne, bo strona logowania jest publiczna."""
    photo = get_object_or_404(LoginPhoto, key=key, is_active=True)
    try:
        handle = photo.path.open("rb")
    except FileNotFoundError:
        raise Http404 from None
    response = FileResponse(handle, content_type="image/jpeg")
    response["Cache-Control"] = "public, max-age=86400"
    return response


@require_safe
def healthz(request):
    """Sprawdzenie dla Dockera i monitoringu: aplikacja działa i baza odpowiada."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        logger.exception("Healthcheck: baza danych nie odpowiada")
        return JsonResponse({"status": "error", "database": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


@require_safe
def healthz_full(request):
    """Pełny stan dla monitoringu z zewnątrz. Działa tylko z kluczem z .env (ARCHIVEHUB_STATUS_TOKEN).

    Odpowiada 200, gdy wszystko działa, a 503, gdy coś wymaga uwagi; usługa monitorująca
    wysyła wtedy maila. Nazwy sprawdzeń bez szczegółów: adres jest dostępny z internetu.
    """
    token = settings.ARCHIVEHUB_STATUS_TOKEN
    if not token or not constant_time_compare(request.GET.get("klucz", ""), token):
        raise Http404
    checks = status.all_checks()
    problems = [check.key for check in checks if not check.ok]
    return JsonResponse(
        {"status": "problem" if problems else "ok", "problemy": problems},
        status=503 if problems else 200,
        headers={"Cache-Control": "no-store"},
    )


@require_safe
@require_safe
def favicon(request):
    """Przeglądarki pytają o /favicon.ico same z siebie (0.60.0): odsyłamy do pliku ze static."""
    return HttpResponsePermanentRedirect(static("img/favicon.ico"))


def robots_txt(request):
    return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")
