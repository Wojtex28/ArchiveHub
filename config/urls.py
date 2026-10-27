from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from accounts.views import needs_two_factor_setup

# Panel awaryjny: te same zasady co nasz panel, łącznie z logowaniem dwuskładnikowym.
_admin_has_permission = admin.site.has_permission
admin.site.has_permission = lambda request: (
    _admin_has_permission(request) and not needs_two_factor_setup(request.user)
)

urlpatterns = [
    # Panel awaryjny Django loguje przez naszą stronę logowania (z limitem prób).
    path(
        f"{settings.DJANGO_ADMIN_PATH}login/",
        RedirectView.as_view(pattern_name="login", query_string=True),
    ),
    path(settings.DJANGO_ADMIN_PATH, admin.site.urls),
    path("panel/", include("panel.urls")),
    path("", include("albums.urls")),
    path("", include("accounts.urls")),
    path("", include("core.urls")),
]
