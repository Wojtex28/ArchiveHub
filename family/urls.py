from django.urls import path

from . import api, views

app_name = "family"

urlpatterns = [
    path("drzewo/", views.tree_home, name="tree"),
    path("drzewo/dodaj/", views.person_add, name="person_add"),
    path("drzewo/osoba/<int:pk>/", views.person_detail, name="person"),
    path("drzewo/osoba/<int:pk>/edytuj/", views.person_edit, name="person_edit"),
    path("drzewo/osoba/<int:pk>/usun/", views.person_remove, name="person_remove"),
    path("drzewo/osoba/<int:pk>/rodzina/", views.relation_add, name="relation_add"),
    path(
        "drzewo/osoba/<int:pk>/rodzina/<int:other_pk>/<str:kind>/usun/",
        views.relation_remove,
        name="relation_remove",
    ),
    path("drzewo/dane.json", api.data, name="data"),
    path("drzewo/api/polozenie/", api.save_positions, name="api_positions"),
    path("drzewo/api/dodaj/", api.add, name="api_add"),
    path("drzewo/api/relacja/", api.relation, name="api_relation"),
    path("drzewo/api/usun/", api.remove, name="api_remove"),
]
