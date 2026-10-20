import logging
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Prefetch, Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST, require_safe

from accounts.models import FamilyGroup, InviteCode
from albums.importer import import_dir, natural_key
from albums.metadata import change_rows
from albums.models import Album, Comment, ImportJob, Person, PhotoChange, SyncReport, Tag, name_key
from albums.sync import albums_dir, sync_albums
from config import __version__
from core.login_photos import delete_login_photo, save_login_photo
from core.models import LoginPhoto

from .codes import suggest_code
from .forms import (
    AlbumForm,
    FamilyGroupForm,
    InviteCodeForm,
    LoginPhotoUploadForm,
    SetPasswordForm,
    UserCreateForm,
    UserEditForm,
)

logger = logging.getLogger(__name__)
User = get_user_model()


def master_required(view):
    """Panel jest tylko dla administratora. Innym zalogowanym udaje, że nie istnieje (404)."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not (request.user.is_active and request.user.is_superuser):
            raise Http404
        return view(request, *args, **kwargs)

    return wrapper


@master_required
def dashboard(request):
    albums = Album.objects.filter(folder_missing=False)
    # Ostatnie zdarzenia: dołączenia i synchronizacje, najnowsze na górze.
    events = [
        (person.date_joined, "join", person) for person in User.objects.order_by("-date_joined")[:8]
    ] + [(report.started_at, "sync", report) for report in SyncReport.objects.all()[:8]]
    events += [(job.finished_at, "import", job) for job in ImportJob.objects.exclude(finished_at=None)[:8]]
    events.sort(key=lambda event: event[0], reverse=True)
    return render(
        request,
        "panel/dashboard.html",
        {
            "user_count": User.objects.filter(is_active=True).count(),
            "inactive_count": User.objects.filter(is_active=False).count(),
            "album_count": albums.count(),
            "photo_count": albums.aggregate(total=Sum("photo_count"))["total"] or 0,
            "group_count": FamilyGroup.objects.count(),
            "code_count": InviteCode.objects.filter(is_active=True).count(),
            "last_sync": SyncReport.objects.first(),
            "pending_imports": ImportJob.objects.filter(
                status__in=[ImportJob.WAITING, ImportJob.PROCESSING]
            ).count(),
            "events": events[:8],
            "version": __version__,
        },
    )


# --- Użytkownicy ------------------------------------------------------------


@master_required
def user_list(request):
    users = User.objects.order_by("-is_active", "username").prefetch_related("family_groups")
    return render(request, "panel/user_list.html", {"users": users})


@master_required
@require_http_methods(["GET", "HEAD", "POST"])
def user_create(request):
    form = UserCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        nick = form.cleaned_data["nick"]
        user = User.objects.create_user(
            username=nick, password=form.cleaned_data["password"], display_name=nick
        )
        user.family_groups.set(form.cleaned_data["groups"])
        logger.info("Administrator %s utworzył konto %s", request.user, user.username)
        messages.success(request, f"Utworzono konto „{user.username}”.")
        return redirect("panel:user_detail", user.pk)
    return render(request, "panel/user_create.html", {"form": form})


@master_required
@require_http_methods(["GET", "HEAD", "POST"])
def user_detail(request, pk):
    person = get_object_or_404(User, pk=pk)
    edit_form = UserEditForm(instance=person)
    password_form = SetPasswordForm(person)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "edit":
            edit_form = UserEditForm(request.POST, instance=person)
            if edit_form.is_valid():
                edit_form.save()
                messages.success(request, "Zapisano zmiany.")
                return redirect("panel:user_detail", person.pk)
        elif action == "password":
            password_form = SetPasswordForm(person, request.POST)
            if password_form.is_valid():
                person.set_password(password_form.cleaned_data["new_password"])
                person.save(update_fields=["password"])
                logger.info("Administrator %s ustawił nowe hasło dla %s", request.user, person.username)
                messages.success(
                    request, f"Ustawiono nowe hasło dla „{person.username}”. Stare sesje wygasły."
                )
                return redirect("panel:user_detail", person.pk)

    return render(
        request,
        "panel/user_detail.html",
        {
            "person": person,
            "edit_form": edit_form,
            "password_form": password_form,
            "visible_albums": Album.objects.visible_to(person),
        },
    )


@master_required
@require_POST
def user_toggle_active(request, pk):
    person = get_object_or_404(User, pk=pk)
    if person == request.user:
        messages.error(request, "Nie możesz wyłączyć własnego konta.")
    else:
        person.is_active = not person.is_active
        person.save(update_fields=["is_active"])
        state = "włączone" if person.is_active else "wyłączone"
        logger.info("Administrator %s: konto %s %s", request.user, person.username, state)
        messages.success(request, f"Konto „{person.username}” jest teraz {state}.")
    return redirect("panel:user_detail", person.pk)


@master_required
@require_http_methods(["GET", "HEAD", "POST"])
def user_delete(request, pk):
    person = get_object_or_404(User, pk=pk)
    if person == request.user or person.is_superuser:
        messages.error(request, "Konta administratora nie można usunąć z panelu.")
        return redirect("panel:user_detail", person.pk)
    if request.method == "POST":
        username = person.username
        person.delete()
        logger.info("Administrator %s usunął konto %s", request.user, username)
        messages.success(request, f"Usunięto konto „{username}”.")
        return redirect("panel:user_list")
    return render(request, "panel/user_delete.html", {"person": person})


# --- Kody rodzinne ----------------------------------------------------------


@master_required
@require_http_methods(["GET", "HEAD", "POST"])
def code_list(request):
    form = InviteCodeForm(request.POST or None, initial={"code": suggest_code()})
    if request.method == "POST":
        if not FamilyGroup.objects.exists():
            messages.error(request, "Najpierw utwórz grupę.")
            return redirect("panel:group_list")
        if form.is_valid():
            code = form.save(commit=False)
            code.created_by = request.user
            code.save()
            logger.info("Administrator %s utworzył kod dla grupy %s", request.user, code.group)
            messages.success(request, f"Utworzono kod „{code.code}” dla grupy {code.group}.")
            return redirect("panel:code_list")
    codes = InviteCode.objects.select_related("group").annotate(use_count=Count("joined_users"))
    return render(request, "panel/code_list.html", {"codes": codes, "form": form})


@master_required
@require_POST
def code_toggle_active(request, pk):
    code = get_object_or_404(InviteCode, pk=pk)
    code.is_active = not code.is_active
    code.save(update_fields=["is_active"])
    messages.success(request, f"Kod „{code.code}” jest teraz {'aktywny' if code.is_active else 'wyłączony'}.")
    return redirect("panel:code_list")


# --- Grupy ------------------------------------------------------------------


@master_required
@require_http_methods(["GET", "HEAD", "POST"])
def group_list(request):
    form = FamilyGroupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        group = form.save()
        messages.success(request, f"Utworzono grupę „{group.name}”.")
        return redirect("panel:group_list")
    groups = FamilyGroup.objects.prefetch_related(
        Prefetch("members", queryset=User.objects.order_by("username"))
    ).annotate(code_count=Count("invite_codes", distinct=True), album_count=Count("albums", distinct=True))
    return render(request, "panel/group_list.html", {"groups": groups, "form": form})


@master_required
@require_http_methods(["GET", "HEAD", "POST"])
def group_edit(request, pk):
    group = get_object_or_404(FamilyGroup, pk=pk)
    form = FamilyGroupForm(request.POST or None, instance=group)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Zapisano grupę.")
        return redirect("panel:group_list")
    return render(request, "panel/group_edit.html", {"group": group, "form": form})


# --- Albumy i uprawnienia ---------------------------------------------------


@master_required
def album_list(request):
    albums = Album.objects.prefetch_related("groups").select_related("cover")
    return render(
        request,
        "panel/album_list.html",
        {
            "albums": albums,
            "all_groups": FamilyGroup.objects.filter(sees_all_albums=True),
            "last_sync": SyncReport.objects.first(),
        },
    )


def _folder_size(path):
    try:
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    except OSError:
        return None


@master_required
@require_http_methods(["GET", "HEAD", "POST"])
def album_detail(request, pk):
    album = get_object_or_404(Album, pk=pk)
    form = AlbumForm(instance=album)
    groups = list(FamilyGroup.objects.all())
    if request.method == "POST":
        if request.POST.get("action") == "groups":
            editable = {g.pk for g in groups if not g.sees_all_albums}
            chosen = {int(v) for v in request.POST.getlist("groups") if v.isdigit() and int(v) in editable}
            album.groups.set(chosen)
            logger.info("Administrator %s zmienił grupy albumu %s", request.user, album.folder)
            messages.success(request, "Zapisano, kto widzi album.")
            return redirect("panel:album_detail", album.pk)
        form = AlbumForm(request.POST, instance=album)
        if form.is_valid():
            form.save()
            messages.success(request, "Zapisano album.")
            return redirect("panel:album_detail", album.pk)
    album_group_ids = set(album.groups.values_list("pk", flat=True))
    return render(
        request,
        "panel/album_detail.html",
        {
            "album": album,
            "form": form,
            "groups": groups,
            "album_group_ids": album_group_ids,
            "viewers": album.viewers(),
            "cover": album.cover_photo,
            "photos": album.photos.all(),
            "imports": album.imports.all()[:10],
            "disk_size": _folder_size(album.path),
        },
    )


@master_required
@require_POST
def album_set_cover(request, pk, photo_pk):
    album = get_object_or_404(Album, pk=pk)
    album.cover = get_object_or_404(album.photos, pk=photo_pk)
    album.save(update_fields=["cover", "updated_at"])
    messages.success(request, f"Okładka albumu: zdjęcie {album.cover.name}.")
    return redirect("panel:album_detail", album.pk)


def _renumber(albums):
    for number, album in enumerate(albums, start=1):
        if album.position != number:
            album.position = number
            album.save(update_fields=["position"])


@master_required
@require_POST
def album_move(request, pk, direction):
    """Przesuwa album o jedno miejsce w górę albo w dół listy."""
    albums = list(Album.objects.all())
    index = next((i for i, a in enumerate(albums) if a.pk == pk), None)
    if index is None:
        raise Http404
    target = index - 1 if direction == "up" else index + 1
    if 0 <= target < len(albums):
        albums[index], albums[target] = albums[target], albums[index]
    with transaction.atomic():
        _renumber(albums)
    return redirect(f"{reverse('panel:album_list')}#album-{pk}")


@master_required
@require_POST
def album_sort_by_folder(request):
    albums = sorted(Album.objects.all(), key=lambda a: natural_key(a.folder))
    with transaction.atomic():
        _renumber(albums)
    messages.success(request, "Ułożono albumy według nazw folderów.")
    return redirect("panel:album_list")


@master_required
@require_POST
def album_reprocess(request, pk):
    album = get_object_or_404(Album, pk=pk)
    album.reprocess_requested = True
    album.save(update_fields=["reprocess_requested"])
    messages.success(
        request,
        "Album trafi do ponownego przetworzenia w ciągu minuty. "
        f"Skany muszą leżeć w udziale w folderze „{album.folder}”.",
    )
    return redirect("panel:album_detail", pk=album.pk)


@master_required
@require_http_methods(["GET", "HEAD", "POST"])
def permissions(request):
    """Tabela albumy × grupy. Grupy „widzą wszystko” mają kolumnę zawsze zaznaczoną."""
    albums = list(Album.objects.prefetch_related("groups"))
    groups = list(FamilyGroup.objects.all())
    editable_ids = {g.pk for g in groups if not g.sees_all_albums}

    if request.method == "POST":
        with transaction.atomic():
            for album in albums:
                chosen = {
                    int(value)
                    for value in request.POST.getlist(f"album-{album.pk}")
                    if value.isdigit() and int(value) in editable_ids
                }
                album.groups.set(chosen)
        logger.info("Administrator %s zapisał uprawnienia do albumów", request.user)
        messages.success(request, "Zapisano uprawnienia.")
        return redirect("panel:permissions")

    rows = [{"album": album, "group_ids": {g.pk for g in album.groups.all()}} for album in albums]
    return render(request, "panel/permissions.html", {"rows": rows, "groups": groups})


@master_required
@require_http_methods(["GET", "HEAD", "POST"])
def sync(request):
    if request.method == "POST":
        report = sync_albums(triggered_by=request.user)
        if report.error:
            messages.error(request, report.error)
        else:
            messages.success(
                request,
                f"Synchronizacja zakończona: {report.albums_total} albumów, {report.photos_total} zdjęć, "
                f"nowe: {len(report.new_albums)}.",
            )
        return redirect("panel:sync")
    return render(
        request,
        "panel/sync.html",
        {
            "reports": SyncReport.objects.select_related("triggered_by")[:20],
            "albums_dir": albums_dir(),
            "import_dir": import_dir(),
            "imports": ImportJob.objects.select_related("album")[:20],
            "stable_minutes": settings.ARCHIVEHUB_IMPORT_STABLE_MINUTES,
        },
    )


# --- Tło strony logowania ---------------------------------------------------


@master_required
@require_http_methods(["GET", "HEAD", "POST"])
def login_photos(request):
    form = LoginPhotoUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        added, errors = 0, []
        for uploaded in form.cleaned_data["photos"]:
            try:
                save_login_photo(uploaded)
                added += 1
            except ValidationError as exc:
                errors.extend(exc.messages)
        if added:
            messages.success(request, f"Dodano zdjęcia: {added}.")
        for error in errors:
            messages.error(request, error)
        return redirect("panel:login_photos")
    return render(request, "panel/login_photos.html", {"form": form, "photos": LoginPhoto.objects.all()})


@master_required
@require_safe
def login_photo_preview(request, pk):
    """Podgląd w panelu, także zdjęć ukrytych (publiczny adres pokazuje tylko widoczne)."""
    photo = get_object_or_404(LoginPhoto, pk=pk)
    try:
        return FileResponse(photo.path.open("rb"), content_type="image/jpeg")
    except FileNotFoundError:
        raise Http404 from None


@master_required
@require_POST
def login_photo_toggle(request, pk):
    photo = get_object_or_404(LoginPhoto, pk=pk)
    photo.is_active = not photo.is_active
    photo.save(update_fields=["is_active"])
    return redirect("panel:login_photos")


@master_required
@require_POST
def login_photo_delete(request, pk):
    delete_login_photo(get_object_or_404(LoginPhoto, pk=pk))
    messages.success(request, "Usunięto zdjęcie z tła.")
    return redirect("panel:login_photos")


# Tyle najnowszych komentarzy pokazuje panel; starsze i tak widać pod zdjęciami.
COMMENTS_SHOWN = 200


@master_required
@require_safe
def comment_list(request):
    """Najnowsze komentarze ze wszystkich albumów, do przeglądania i usuwania."""
    comments = Comment.objects.select_related("author", "photo__album").order_by("-created_at", "-pk")
    return render(
        request,
        "panel/comment_list.html",
        {"comments": comments[:COMMENTS_SHOWN], "total": comments.count(), "shown": COMMENTS_SHOWN},
    )


@master_required
@require_POST
def comment_delete(request, pk):
    comment = get_object_or_404(Comment.objects.select_related("photo__album"), pk=pk)
    logger.info("Administrator %s usunął komentarz %s: %r", request.user, comment.pk, comment.text[:200])
    comment.delete()
    messages.success(request, "Usunięto komentarz.")
    return redirect("panel:comment_list")


CHANGES_SHOWN = 100
NAMED = {"osoby": Person, "tagi": Tag}


@master_required
@require_safe
def descriptions(request):
    """Osoby i tagi z opisów zdjęć (do poprawiania literówek) i ostatnie zmiany opisów."""
    changes = PhotoChange.objects.select_related("user", "photo__album").order_by("-created_at", "-pk")
    changes = list(changes[:CHANGES_SHOWN])
    for change in changes:
        change.rows = change_rows(change)
    return render(
        request,
        "panel/descriptions.html",
        {
            "named": [
                ("Osoby", "osoby", list(Person.objects.annotate(count=Count("photos")))),
                ("Tagi", "tagi", list(Tag.objects.annotate(count=Count("photos")))),
            ],
            "changes": changes,
            "shown": CHANGES_SHOWN,
        },
    )


@master_required
@require_POST
@transaction.atomic
def named_edit(request, kind, pk):
    """Zmiana nazwy osoby albo tagu. Nazwa, która już istnieje, łączy oba wpisy w jeden."""
    model = NAMED.get(kind)
    if model is None:
        raise Http404
    item = get_object_or_404(model, pk=pk)
    if request.POST.get("action") == "delete":
        logger.info("Administrator %s usunął %s %r", request.user, model._meta.verbose_name, item.name)
        item.delete()
        messages.success(request, f"Usunięto „{item.name}” ze wszystkich zdjęć.")
        return redirect("panel:descriptions")
    name = " ".join(request.POST.get("name", "").split())
    if not name or len(name) > model.MAX_LENGTH:
        messages.error(request, "Wpisz nazwę (najwyżej 100 znaków).")
        return redirect("panel:descriptions")
    other = model.objects.filter(key=name_key(name)).exclude(pk=item.pk).first()
    if other:
        for photo in item.photos.all():
            photo_items = getattr(photo, "people" if model is Person else "tags")
            photo_items.add(other)
        logger.info("Administrator %s połączył %r z %r", request.user, item.name, other.name)
        messages.success(request, f"Połączono „{item.name}” z „{other.name}”.")
        item.delete()
    else:
        old = item.name
        item.name = name
        item.save()
        messages.success(request, f"Zmieniono „{old}” na „{name}”.")
    return redirect("panel:descriptions")
