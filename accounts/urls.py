from django.urls import path

from . import views

urlpatterns = [
    path("logowanie/", views.login_view, name="login"),
    path("logowanie/kod/", views.login_two_factor_view, name="login_two_factor"),
    path("wyloguj/", views.logout_view, name="logout"),
    path("dolacz/", views.join_code_view, name="join"),
    path("dolacz/profil/", views.join_profile_view, name="join_profile"),
    path("konto/kod/", views.add_code_view, name="add_code"),
    path("konto/dwuskladnikowe/", views.two_factor_view, name="two_factor"),
    path("konto/haslo/", views.OwnPasswordChangeView.as_view(), name="password_change"),
]
