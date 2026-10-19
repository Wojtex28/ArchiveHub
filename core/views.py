import logging

from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_safe

logger = logging.getLogger(__name__)


@require_safe
def landing(request):
    return render(request, "core/landing.html")


@require_safe
@login_required
def archive_home(request):
    # Albumy pojawią się tu w kolejnych etapach.
    return render(request, "core/archive_home.html")


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
