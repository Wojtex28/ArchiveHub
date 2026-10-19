from django.urls import path

from . import views

urlpatterns = [
    path("", views.landing, name="landing"),
    path("archiwum/", views.archive_placeholder, name="archive"),
    path("healthz", views.healthz, name="healthz"),
    path("robots.txt", views.robots_txt, name="robots_txt"),
]
