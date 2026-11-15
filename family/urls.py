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
    path("drzewo/osoba/<int:pk>/para/<int:other_pk>/", views.couple_edit, name="couple_edit"),
    path("drzewo/osoba/<int:pk>/para/<int:other_pk>/kolejnosc/", views.partner_order, name="partner_order"),
    path("drzewo/osoba/<int:pk>/zdarzenie/", views.event_add, name="event_add"),
    path("drzewo/zdarzenie/<int:pk>/", views.event_edit, name="event_edit"),
    path("drzewo/osoba/<int:pk>/zdjecia/", views.person_photos_add, name="person_photos_add"),
    path("drzewo/zdjecie/<uuid:key>/<str:size>.jpg", views.person_photo_file, name="person_photo_file"),
    path("drzewo/zdjecie/<int:pk>/opis/", views.person_photo_edit, name="person_photo_edit"),
    path("drzewo/zdjecie/<int:pk>/usun/", views.person_photo_remove, name="person_photo_remove"),
    path("drzewo/zdarzenie/<int:pk>/usun/", views.event_remove, name="event_remove"),
    path("drzewo/dane.json", api.data, name="data"),
    path("drzewo/api/polozenie/", api.save_positions, name="api_positions"),
    path("drzewo/api/dodaj/", api.add, name="api_add"),
    path("drzewo/api/relacja/", api.relation, name="api_relation"),
    path("drzewo/api/usun/", api.remove, name="api_remove"),
    path("drzewo/api/zyje/", api.alive, name="api_alive"),
    path("drzewo/api/para/", api.couple, name="api_couple"),
    path("drzewo/api/zdarzenie/", api.event, name="api_event"),
    path("drzewo/api/sprawdzenie/", api.check, name="api_check"),
    path("drzewo/api/osoba/<int:pk>/", api.person, name="api_person"),
]
