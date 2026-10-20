from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponseNotModified
from django.shortcuts import get_object_or_404, render
from django.utils.http import http_date
from django.views.decorators.http import require_safe
from django.views.static import was_modified_since

from .models import Album, Photo


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
    photos = album.photos.filter(file_missing=False)
    return render(request, "albums/gallery.html", {"album": album, "photos": photos})


@require_safe
@login_required
def photo_page(request, album_pk, pk, reverse=False):
    """Jedno zdjęcie na całą stronę. Działa bez JavaScriptu i jako link do wysłania komuś z rodziny."""
    album = _visible_album(request, album_pk)
    ids = list(album.photos.filter(file_missing=False).values_list("pk", flat=True))
    if pk not in ids:
        raise Http404
    photo = get_object_or_404(Photo, pk=pk)
    if reverse and not photo.has_reverse:
        raise Http404
    index = ids.index(pk)
    return render(
        request,
        "albums/photo.html",
        {
            "album": album,
            "photo": photo,
            "reverse": reverse,
            "number": index + 1,
            "total": len(ids),
            "previous_pk": ids[index - 1] if index > 0 else None,
            "next_pk": ids[index + 1] if index + 1 < len(ids) else None,
        },
    )
