import logging

from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.views import PasswordChangeView
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods, require_POST

from . import ratelimit
from .forms import JoinCodeForm, JoinProfileForm, LoginForm
from .models import InviteCode

logger = logging.getLogger(__name__)

BLOCKED_MESSAGE = "Za dużo nieudanych prób. Odczekaj kwadrans i spróbuj ponownie."
JOIN_SESSION_KEY = "join_code_id"


def _safe_next(request):
    candidate = request.POST.get("next") or request.GET.get("next") or ""
    if url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return reverse("archive")


@sensitive_post_parameters("password")
@require_http_methods(["GET", "HEAD", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect(_safe_next(request))

    form = LoginForm(request.POST or None)
    error = None
    if request.method == "POST" and form.is_valid():
        username = form.cleaned_data["username"]
        if ratelimit.is_blocked("login", request, username):
            error = BLOCKED_MESSAGE
            logger.warning("Zablokowane logowanie: %s z %s", username, ratelimit.client_ip(request))
        else:
            user = authenticate(request, username=username, password=form.cleaned_data["password"])
            if user is None:
                ratelimit.record_failure("login", request, username)
                error = "Nieprawidłowy nick lub hasło."
            else:
                ratelimit.clear("login", request, username)
                login(request, user)
                return redirect(_safe_next(request))

    return render(
        request,
        "accounts/login.html",
        {"form": form, "error": error, "next": request.GET.get("next", "")},
        status=429 if error == BLOCKED_MESSAGE else 200,
    )


@require_POST
def logout_view(request):
    logout(request)
    return redirect("landing")


@require_http_methods(["GET", "HEAD", "POST"])
def join_code_view(request):
    """Krok 1: kod rodzinny."""
    if request.user.is_authenticated:
        return redirect("archive")

    form = JoinCodeForm(request.POST or None)
    error = None
    if request.method == "POST" and form.is_valid():
        if ratelimit.is_blocked("code", request):
            error = BLOCKED_MESSAGE
        else:
            code = InviteCode.objects.filter(code=InviteCode.normalize(form.cleaned_data["code"])).first()
            if code is None or code.unusable_reason() is not None:
                ratelimit.record_failure("code", request)
                # Ten sam komunikat dla złego i nieaktywnego kodu: nie zdradzamy, które kody istnieją.
                error = "Ten kod nie działa. Sprawdź pisownię albo poproś o nowy."
            else:
                request.session[JOIN_SESSION_KEY] = code.pk
                return redirect("join_profile")

    return render(
        request,
        "accounts/join_code.html",
        {"form": form, "error": error},
        status=429 if error == BLOCKED_MESSAGE else 200,
    )


def _code_from_session(request):
    code_id = request.session.get(JOIN_SESSION_KEY)
    if not code_id:
        return None
    code = InviteCode.objects.filter(pk=code_id).select_related("group").first()
    if code is None or code.unusable_reason() is not None:
        request.session.pop(JOIN_SESSION_KEY, None)
        return None
    return code


@sensitive_post_parameters("password1", "password2")
@require_http_methods(["GET", "HEAD", "POST"])
def join_profile_view(request):
    """Krok 2: nick i własne hasło."""
    if request.user.is_authenticated:
        return redirect("archive")
    code = _code_from_session(request)
    if code is None:
        messages.info(request, "Zacznij od wpisania kodu rodzinnego.")
        return redirect("join")

    form = JoinProfileForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            nick = form.cleaned_data["nick"]
            user = get_user_model().objects.create_user(
                username=nick,
                password=form.cleaned_data["password1"],
                display_name=nick,
                joined_with_code=code,
            )
            user.family_groups.add(code.group)
        request.session.pop(JOIN_SESSION_KEY, None)
        login(request, user, backend="accounts.backends.CaseInsensitiveModelBackend")
        logger.info("Nowe konto %s (kod %s, grupa %s)", user.username, code.pk, code.group)
        messages.success(request, f"Witaj, {user}! Konto jest gotowe.")
        return redirect("archive")

    return render(request, "accounts/join_profile.html", {"form": form, "group": code.group})


class OwnPasswordChangeView(PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("archive")

    def form_valid(self, form):
        messages.success(self.request, "Hasło zostało zmienione.")
        return super().form_valid(form)
