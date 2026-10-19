from django.urls import path

from . import views

urlpatterns = [
    path("logowanie/", views.login_view, name="login"),
    path("wyloguj/", views.logout_view, name="logout"),
    path("dolacz/", views.join_code_view, name="join"),
    path("dolacz/profil/", views.join_profile_view, name="join_profile"),
    path("konto/haslo/", views.OwnPasswordChangeView.as_view(), name="password_change"),
]
