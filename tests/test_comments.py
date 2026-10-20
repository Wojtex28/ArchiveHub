"""ETAP 10: komentarze pod zdjęciami."""

import pytest
from django.urls import reverse

from accounts.models import FamilyGroup
from albums.models import Album, Comment, Photo

FETCH = {"HTTP_X_REQUESTED_WITH": "fetch"}


def make_photo(album, name, position):
    return Photo.objects.create(
        album=album,
        name=name,
        source_name=f"{name}.png",
        position=position,
        checksum=f"{album.folder}-{name}",
        width=40,
        height=30,
    )


@pytest.fixture
def family(db, tmp_path, settings, make_user, group):
    settings.ARCHIVEHUB_ALBUMS_DIR = tmp_path
    album = Album.objects.create(folder="01_Brazowy", title="Brązowy")
    album.groups.add(group)
    other = Album.objects.create(folder="02_Obcy", title="Obcy")
    other.groups.add(FamilyGroup.objects.create(name="Włodyka"))
    karolina = make_user("Karolina")
    adam = make_user("Adam")
    for person in (karolina, adam):
        person.family_groups.add(group)
    return {
        "album": album,
        "photo": make_photo(album, "img_1", 1),
        "second": make_photo(album, "img_2", 2),
        "stranger": make_photo(other, "obce", 1),
        "karolina": karolina,
        "adam": adam,
    }


@pytest.fixture
def karolina(client, family):
    client.force_login(family["karolina"])
    return client


def comments_url(photo):
    return reverse("albums:comments", args=[photo.pk])


def test_add_comment_signed_with_nick(karolina, family):
    photo = family["photo"]
    text = "  To babcia Helena w Berezowie, ok. 1958.  "
    response = karolina.post(comments_url(photo), {"text": text}, **FETCH)
    assert response.status_code == 200
    assert response["X-Comment-Count"] == "1"
    comment = Comment.objects.get()
    assert comment.author == family["karolina"]
    assert comment.text == "To babcia Helena w Berezowie, ok. 1958."
    page = response.content.decode()
    assert "<strong>Karolina</strong>" in page
    assert "To babcia Helena" in page


def test_comment_without_javascript_returns_to_photo_page(karolina, family):
    photo = family["photo"]
    response = karolina.post(comments_url(photo), {"text": "Wesele wujka"})
    assert response.status_code == 302
    assert response["Location"].endswith(f"/{photo.pk}/?komentarze=1#komentarze")
    page = karolina.get(response["Location"]).content.decode()
    assert "Wesele wujka" in page
    assert 'id="komentarze"' in page


def test_comments_are_escaped(karolina, family):
    photo = family["photo"]
    karolina.post(comments_url(photo), {"text": '<script>alert("x")</script>\n<img src=x onerror=alert(1)>'})
    page = karolina.get(comments_url(photo), **FETCH).content.decode()
    assert "<script>alert" not in page
    assert "<img src=x" not in page
    assert "&lt;script&gt;" in page
    assert "<br>" in page


def test_empty_comment_is_rejected(karolina, family):
    response = karolina.post(comments_url(family["photo"]), {"text": "   "}, **FETCH)
    assert response.status_code == 400
    assert "To pole jest wymagane" in response.content.decode()
    assert not Comment.objects.exists()


def test_empty_comment_without_javascript_shows_error_on_photo_page(karolina, family):
    response = karolina.post(comments_url(family["photo"]), {"text": ""})
    assert response.status_code == 400
    assert "To pole jest wymagane" in response.content.decode()
    assert 'class="viewer__img"' in response.content.decode()


def test_too_long_comment_is_rejected(karolina, family):
    response = karolina.post(comments_url(family["photo"]), {"text": "a" * 2001}, **FETCH)
    assert response.status_code == 400
    assert not Comment.objects.exists()


def test_too_many_comments_in_a_minute(karolina, family):
    for number in range(10):
        karolina.post(comments_url(family["photo"]), {"text": f"komentarz {number}"}, **FETCH)
    response = karolina.post(comments_url(family["photo"]), {"text": "jeszcze jeden"}, **FETCH)
    assert response.status_code == 400
    assert "Odczekaj chwilę" in response.content.decode()
    assert Comment.objects.count() == 10


def test_comments_need_access_to_album(karolina, family):
    stranger = family["stranger"]
    assert karolina.get(comments_url(stranger), **FETCH).status_code == 404
    assert karolina.post(comments_url(stranger), {"text": "hej"}, **FETCH).status_code == 404
    assert not Comment.objects.exists()


def test_comments_need_login(client, family):
    response = client.post(comments_url(family["photo"]), {"text": "hej"})
    assert response.status_code == 302
    assert "/logowanie/" in response["Location"]
    assert not Comment.objects.exists()


def test_plain_get_redirects_to_photo_page(karolina, family):
    response = karolina.get(comments_url(family["photo"]))
    assert response.status_code == 302
    assert "?komentarze=1" in response["Location"]


def test_author_deletes_own_comment(karolina, family):
    comment = Comment.objects.create(photo=family["photo"], author=family["karolina"], text="pomyłka")
    page = karolina.get(comments_url(family["photo"]), **FETCH).content.decode()
    assert reverse("albums:comment_delete", args=[comment.pk]) in page
    response = karolina.post(reverse("albums:comment_delete", args=[comment.pk]), **FETCH)
    assert response.status_code == 200
    assert response["X-Comment-Count"] == "0"
    assert not Comment.objects.exists()


def test_cannot_delete_someone_elses_comment(karolina, family):
    comment = Comment.objects.create(photo=family["photo"], author=family["adam"], text="Adam pisze")
    page = karolina.get(comments_url(family["photo"]), **FETCH).content.decode()
    assert reverse("albums:comment_delete", args=[comment.pk]) not in page
    assert karolina.post(reverse("albums:comment_delete", args=[comment.pk])).status_code == 404
    assert Comment.objects.filter(pk=comment.pk).exists()


def test_master_deletes_any_comment(client, master, family):
    comment = Comment.objects.create(photo=family["photo"], author=family["adam"], text="spam")
    client.force_login(master)
    response = client.post(reverse("albums:comment_delete", args=[comment.pk]))
    assert response.status_code == 302
    assert not Comment.objects.exists()


def test_comment_of_deleted_account_stays(karolina, family):
    Comment.objects.create(photo=family["photo"], author=family["adam"], text="Zostaję")
    family["adam"].delete()
    page = karolina.get(comments_url(family["photo"]), **FETCH).content.decode()
    assert "konto usunięte" in page
    assert "Zostaję" in page


def test_comments_belong_to_one_photo(karolina, family):
    Comment.objects.create(photo=family["photo"], author=family["adam"], text="pod pierwszym")
    page = karolina.get(comments_url(family["second"]), **FETCH).content.decode()
    assert "pod pierwszym" not in page
    assert "Nikt jeszcze nie skomentował" in page


def test_gallery_shows_comment_counts(karolina, family):
    for text in ("jeden", "dwa"):
        Comment.objects.create(photo=family["photo"], author=family["adam"], text=text)
    response = karolina.get(reverse("albums:gallery", args=[family["album"].pk]))
    counts = {photo.pk: photo.comment_count for photo in response.context["photos"]}
    assert counts == {family["photo"].pk: 2, family["second"].pk: 0}
    page = response.content.decode()
    assert 'data-comments="2"' in page
    assert f'data-comments-url="{comments_url(family["photo"])}"' in page


def test_photo_page_comment_panel_only_when_asked(karolina, family):
    photo = family["photo"]
    url = reverse("albums:photo", args=[family["album"].pk, photo.pk])
    Comment.objects.create(photo=photo, author=family["adam"], text="widać dopiero po otwarciu")
    closed = karolina.get(url).content.decode()
    assert "widać dopiero po otwarciu" not in closed
    assert 'aria-label="Opis i komentarze (1)"' in closed
    opened = karolina.get(url + "?komentarze=1").content.decode()
    assert "widać dopiero po otwarciu" in opened
    # Następne zdjęcie otwiera się z panelem komentarzy.
    assert f'{family["second"].pk}/?komentarze=1"' in opened


# --- Panel administratora ---------------------------------------------------


def test_panel_lists_newest_comments_first(master_client, family):
    Comment.objects.create(photo=family["photo"], author=family["adam"], text="starszy")
    Comment.objects.create(photo=family["second"], author=family["karolina"], text="nowszy")
    page = master_client.get(reverse("panel:comment_list")).content.decode()
    assert page.index("nowszy") < page.index("starszy")
    assert "Brązowy" in page


def test_panel_deletes_comment(master_client, family):
    comment = Comment.objects.create(photo=family["photo"], author=family["adam"], text="do usunięcia")
    response = master_client.post(reverse("panel:comment_delete", args=[comment.pk]))
    assert response.status_code == 302
    assert not Comment.objects.exists()


def test_panel_comments_only_for_master(karolina, family):
    assert karolina.get(reverse("panel:comment_list")).status_code == 404
