from django.urls import path

from . import collections, comments, favorites, marks, metadata, search, views

app_name = "albums"

urlpatterns = [
    path("szukaj/", search.search, name="search"),
    path("ulubione/", favorites.favorites_page, name="favorites"),
    path("ulubione/pobierz/", favorites.favorites_download, name="favorites_download"),
    path("zdjecia/<int:pk>/ulubione/", favorites.favorite_toggle, name="favorite"),
    path("zdjecia/<int:pk>/moje-albumy/", collections.photo_collections, name="photo_collections"),
    path("moje-albumy/nowy/", collections.album_create, name="own_album_create"),
    path("moje-albumy/<int:pk>/", collections.album_page, name="own_album"),
    path("moje-albumy/<int:pk>/pobierz/", collections.album_download, name="own_album_download"),
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
    path("zdjecia/<int:pk>/komentarze/", comments.photo_comments, name="comments"),
    path("zdjecia/<int:pk>/opis/", metadata.photo_metadata, name="metadata"),
    path("zdjecia/<int:pk>/punkt/", marks.photo_mark, name="mark"),
    path("komentarze/<int:pk>/usun/", comments.comment_delete, name="comment_delete"),
    path("zdjecia/<int:pk>/pobierz/", views.photo_download, name="download"),
    path(
        "zdjecia/<int:pk>/rewers/pobierz/", views.photo_download, {"reverse": True}, name="download_reverse"
    ),
    path("zdjecia/<int:pk>/podglad.jpg", views.photo_preview, name="preview"),
    path("zdjecia/<int:pk>/rewers.jpg", views.photo_preview, {"reverse": True}, name="preview_reverse"),
]
