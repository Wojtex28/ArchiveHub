from django.urls import path

from . import views

app_name = "albums"

urlpatterns = [
    path("zdjecia/<int:pk>/miniatura.webp", views.photo_thumb, name="thumb"),
    path("zdjecia/<int:pk>/rewers.webp", views.photo_thumb, {"reverse": True}, name="thumb_reverse"),
]
