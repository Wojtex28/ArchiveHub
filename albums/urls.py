from django.urls import path

from . import views

app_name = "albums"

urlpatterns = [
    path("archiwum/<int:pk>/", views.album_gallery, name="gallery"),
    path("archiwum/<int:album_pk>/<int:pk>/", views.photo_page, name="photo"),
    path(
        "archiwum/<int:album_pk>/<int:pk>/rewers/",
        views.photo_page,
        {"reverse": True},
        name="photo_reverse",
    ),
    path("zdjecia/<int:pk>/miniatura.webp", views.photo_thumb, name="thumb"),
    path("zdjecia/<int:pk>/rewers.webp", views.photo_thumb, {"reverse": True}, name="thumb_reverse"),
    path("archiwum/<int:pk>/pobierz/", views.album_download, name="album_download"),
    path("archiwum/<int:pk>/pobierz-caly/", views.album_download_all, name="album_download_all"),
    path("zdjecia/<int:pk>/obroc/", views.photo_rotate, name="rotate"),
    path("zdjecia/<int:pk>/pobierz/", views.photo_download, name="download"),
    path(
        "zdjecia/<int:pk>/rewers/pobierz/", views.photo_download, {"reverse": True}, name="download_reverse"
    ),
    path("zdjecia/<int:pk>/podglad.jpg", views.photo_preview, name="preview"),
    path("zdjecia/<int:pk>/rewers.jpg", views.photo_preview, {"reverse": True}, name="preview_reverse"),
]
