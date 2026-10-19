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
]
