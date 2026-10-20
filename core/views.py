import logging

from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_safe

from albums.models import Album

from .models import LoginPhoto

logger = logging.getLogger(__name__)


@require_safe
def landing(request):
    return render(request, "core/landing.html")


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
def robots_txt(request):
    return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")
