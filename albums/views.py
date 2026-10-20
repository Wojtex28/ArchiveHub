import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import (
    FileResponse,
    Http404,
    HttpResponseBadRequest,
    HttpResponseNotModified,
    JsonResponse,
    StreamingHttpResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import http_date
from django.views.decorators.http import require_POST, require_safe
from django.views.static import was_modified_since

from .downloads import (
    ZipDownload,
    attachment_header,
    download_size,
    file_name,
    ready_original,
    safe_name,
    take_zip_slot,
)
from .models import Album, Photo
from .photo_panel import panel_context
from .rotation import rotate

logger = logging.getLogger(__name__)

# Tyle zdjęć można zaznaczyć do jednego ZIP-a (cały album to i tak ok. 50–200).
MAX_SELECTED = 1000


def _visible_photo(request, pk, reverse):
    """Zdjęcie, o ile pytająca osoba widzi jego album. Inaczej 404, także dla nieistniejących numerów."""
    photo = get_object_or_404(Photo.objects.visible_to(request.user).select_related("album"), pk=pk)
    if reverse and not photo.has_reverse:
        raise Http404
    return photo


def _serve(request, path, content_type):
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        raise Http404 from None
    # Przeglądarka pyta „czy coś się zmieniło?” i dostaje krótkie „nie”, zamiast całego pliku jeszcze raz.
    if not was_modified_since(request.headers.get("If-Modified-Since"), int(mtime)):
        response = HttpResponseNotModified()
    else:
        response = FileResponse(path.open("rb"), content_type=content_type)
    response["Last-Modified"] = http_date(mtime)
    # Prywatnie: przeglądarka może trzymać plik, ale żaden pośrednik (np. Cloudflare) już nie.
    response["Cache-Control"] = "private, max-age=86400"
    return response


@require_safe
@login_required
def photo_thumb(request, pk, reverse=False):
    """Miniatura zdjęcia. Uprawnienia sprawdzane przy każdym pliku: adres wpisany ręcznie nic nie da."""
    photo = _visible_photo(request, pk, reverse)
    return _serve(request, photo.thumb_path(reverse=reverse), "image/webp")


@require_safe
@login_required
def photo_preview(request, pk, reverse=False):
    """Wersja do oglądania na ekranie (2560 px). Oryginał w pełnej rozdzielczości nie jest tu wysyłany."""
    photo = _visible_photo(request, pk, reverse)
    path = photo.preview_path(reverse=reverse)
    if not path.is_file():
        # Album sprzed pełnej rozdzielczości, jeszcze nie przetworzony ponownie.
        path = photo.legacy_path(reverse=reverse)
    return _serve(request, path, "image/jpeg")


def _visible_album(request, pk):
    return get_object_or_404(Album.objects.visible_to(request.user), pk=pk)


@require_safe
@login_required
def album_gallery(request, pk):
    album = _visible_album(request, pk)
    photos = list(
        album.photos.filter(file_missing=False)
        .annotate(comment_count=Count("comments"))
        .prefetch_related("people")
    )
    return render(
        request,
        "albums/gallery.html",
        {"album": album, "photos": photos, "album_size": download_size(photos)},
    )


@require_safe
@login_required
def photo_page(request, album_pk, pk, reverse=False):
    """Jedno zdjęcie na całą stronę. Działa bez JavaScriptu i jako link do wysłania komuś z rodziny."""
    return render_photo_page(request, album_pk, pk, reverse)


def render_photo_page(request, album_pk, pk, reverse=False, comment_form=None, metadata_form=None):
    """Strona zdjęcia; z formularzem także po nieudanym zapisie komentarza albo opisu bez JavaScriptu."""
    album = _visible_album(request, album_pk)
    ids = list(album.photos.filter(file_missing=False).values_list("pk", flat=True))
    if pk not in ids:
        raise Http404
    photo = get_object_or_404(Photo, pk=pk)
    if reverse and not photo.has_reverse:
        raise Http404
    index = ids.index(pk)
    failed = comment_form is not None or metadata_form is not None
    show_comments = "komentarze" in request.GET or failed
    return render(
        request,
        "albums/photo.html",
        {
            **panel_context(request, photo, comment_form, metadata_form),
            "show_comments": show_comments,
            "album": album,
            "photo": photo,
            "reverse": reverse,
            "number": index + 1,
            "total": len(ids),
            "previous_pk": ids[index - 1] if index > 0 else None,
            "next_pk": ids[index + 1] if index + 1 < len(ids) else None,
        },
        status=400 if failed else 200,
    )


@require_POST
@login_required
def photo_rotate(request, pk):
    """↺/↻ w galerii. Może każdy, kto widzi album; zapis od razu, bez potwierdzania."""
    reverse = request.POST.get("side") == "rewers"
    direction = request.POST.get("direction")
    if direction not in ("lewo", "prawo"):
        return HttpResponseBadRequest("direction: lewo albo prawo")
    photo = _visible_photo(request, pk, reverse)
    rotate(photo, request.user, reverse=reverse, clockwise=direction == "prawo")
    return JsonResponse(
        {"rotation": photo.target_rotation(reverse), "pending": photo.pending_rotation(reverse)}
    )


@require_safe
@login_required
def photo_download(request, pk, reverse=False):
    """Oryginał w pełnej rozdzielczości do zapisania. Uprawnienia sprawdzane przy każdym pobraniu."""
    photo = _visible_photo(request, pk, reverse)
    path = ready_original(photo, reverse)
    if path is None:
        raise Http404
    logger.info("%s pobiera %s%s", request.user, photo, " (rewers)" if reverse else "")
    name = f"{safe_name(photo.album.title)} - {file_name(photo, reverse)}"
    response = FileResponse(path.open("rb"), content_type="image/jpeg")
    response["Content-Disposition"] = attachment_header(name)
    response["Cache-Control"] = "private, no-store"
    return response


@require_POST
@login_required
def album_download(request, pk):
    """Zaznaczone zdjęcia albumu jako jeden ZIP (z rewersami)."""
    album = _visible_album(request, pk)
    ids = [int(value) for value in request.POST.getlist("photos") if value.isdigit()][:MAX_SELECTED]
    photos = list(album.photos.filter(pk__in=ids, file_missing=False))
    if not photos:
        messages.error(request, "Zaznacz co najmniej jedno zdjęcie.")
        return redirect("albums:gallery", album.pk)
    return _zip_response(request, album, photos, f"{safe_name(album.title)} ({len(photos)} zdj.).zip")


@require_safe
@login_required
def album_download_all(request, pk):
    """Cały album (z rewersami) jako jeden ZIP."""
    album = _visible_album(request, pk)
    photos = list(album.photos.filter(file_missing=False))
    if not photos:
        raise Http404
    return _zip_response(request, album, photos, f"{safe_name(album.title)}.zip")


def _zip_response(request, album, photos, name):
    slot = take_zip_slot()
    if slot is None:
        logger.warning("%s: wszystkie miejsca na ZIP zajęte (album %s)", request.user, album.folder)
        messages.warning(
            request,
            "W tej chwili kilka osób pobiera albumy naraz. Spróbuj ponownie za kilka minut.",
        )
        return redirect("albums:gallery", album.pk)
    logger.info("%s pobiera ZIP z %s zdjęciami z albumu %s", request.user, len(photos), album.folder)
    content = ZipDownload(photos, safe_name(album.title), slot)
    response = StreamingHttpResponse(content, content_type="application/zip")
    response["Content-Disposition"] = attachment_header(name)
    response["Cache-Control"] = "private, no-store"
    return response
