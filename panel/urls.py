from django.urls import path

from . import views

app_name = "panel"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("uzytkownicy/", views.user_list, name="user_list"),
    path("uzytkownicy/nowy/", views.user_create, name="user_create"),
    path("uzytkownicy/<int:pk>/", views.user_detail, name="user_detail"),
    path("uzytkownicy/<int:pk>/aktywnosc/", views.user_toggle_active, name="user_toggle_active"),
    path("uzytkownicy/<int:pk>/usun/", views.user_delete, name="user_delete"),
    path("kody/", views.code_list, name="code_list"),
    path("kody/<int:pk>/aktywnosc/", views.code_toggle_active, name="code_toggle_active"),
    path("grupy/", views.group_list, name="group_list"),
    path("grupy/<int:pk>/", views.group_edit, name="group_edit"),
    path("albumy/", views.album_list, name="album_list"),
    path("albumy/<int:pk>/", views.album_detail, name="album_detail"),
    path("albumy/<int:pk>/przetworz/", views.album_reprocess, name="album_reprocess"),
    path("albumy/<int:pk>/okladka/<int:photo_pk>/", views.album_set_cover, name="album_set_cover"),
    path("albumy/<int:pk>/w-gore/", views.album_move, {"direction": "up"}, name="album_move_up"),
    path("albumy/<int:pk>/w-dol/", views.album_move, {"direction": "down"}, name="album_move_down"),
    path("albumy/uloz-wedlug-folderow/", views.album_sort_by_folder, name="album_sort_by_folder"),
    path("uprawnienia/", views.permissions, name="permissions"),
    path("komentarze/", views.comment_list, name="comment_list"),
    path("komentarze/<int:pk>/usun/", views.comment_delete, name="comment_delete"),
    path("opisy/", views.descriptions, name="descriptions"),
    path("opisy/<str:kind>/<int:pk>/", views.named_edit, name="named_edit"),
    path("synchronizacja/", views.sync, name="sync"),
    path("stan/", views.server_status, name="server_status"),
    path("tlo-logowania/", views.login_photos, name="login_photos"),
    path("tlo-logowania/<int:pk>.jpg", views.login_photo_preview, name="login_photo_preview"),
    path("tlo-logowania/<int:pk>/pokazuj/", views.login_photo_toggle, name="login_photo_toggle"),
    path("tlo-logowania/<int:pk>/usun/", views.login_photo_delete, name="login_photo_delete"),
]
