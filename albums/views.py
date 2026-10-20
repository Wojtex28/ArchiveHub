from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_safe

from .models import Photo


@require_safe
@login_required
def photo_thumb(request, pk, reverse=False):
    """Miniatura zdjęcia. Uprawnienia sprawdzane przy każdym pliku: adres wpisany ręcznie nic nie da."""
    photo = get_object_or_404(Photo.objects.visible_to(request.user).select_related("album"), pk=pk)
    if reverse and not photo.has_reverse:
        raise Http404
    try:
        handle = photo.thumb_path(reverse=reverse).open("rb")
    except FileNotFoundError:
        raise Http404 from None
    response = FileResponse(handle, content_type="image/webp")
    # Prywatnie: przeglądarka może trzymać miniaturę, ale żaden pośrednik (np. Cloudflare) już nie.
    response["Cache-Control"] = "private, max-age=86400"
    return response
