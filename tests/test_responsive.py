"""ETAP 12: drobne rzeczy po stronie HTML do obsługi telefonu i powiększania."""

from django.urls import reverse

from albums.models import Album


def test_panel_loads_tabs_script(master_client):
    page = master_client.get(reverse("panel:dashboard")).content.decode()
    assert "js/tabs.js" in page
    assert 'aria-current="page"' in page


def test_gallery_hint_mentions_zoom(client, make_user, group, db):
    album = Album.objects.create(folder="01_Album", title="Album")
    album.groups.add(group)
    user = make_user("Karolina")
    user.family_groups.add(group)
    client.force_login(user)
    page = client.get(reverse("albums:gallery", args=[album.pk])).content.decode()
    assert "powiększysz dwuklikiem, kółkiem myszy albo dwoma palcami" in page
