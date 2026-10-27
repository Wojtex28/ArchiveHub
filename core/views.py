import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.crypto import constant_time_compare
from django.views.decorators.http import require_safe

from albums.models import Album, Photo

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
            "alt": f"Zdjęcie z albumu {photo.album.title}",
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


@require_safe
@login_required
def archive_home(request):
    albums = Album.objects.visible_to(request.user)
    if request.user.is_superuser:
        albums = albums.filter(folder_missing=False)
    return render(request, "core/archive_home.html", {"albums": albums})


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
def robots_txt(request):
    return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")
