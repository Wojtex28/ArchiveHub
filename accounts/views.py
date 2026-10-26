import logging
import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import (
    authenticate,
    get_user_model,
    login,
    logout,
    update_session_auth_hash,
)
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordChangeView
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods, require_POST

from core.login_photos import login_background

from . import ratelimit, totp
from .forms import (
    JoinCodeForm,
    JoinProfileForm,
    LoginForm,
    SecondFactorForm,
    TwoFactorConfirmForm,
    TwoFactorDisableForm,
)
from .models import InviteCode, RecoveryCode

logger = logging.getLogger(__name__)

BLOCKED_MESSAGE = "Za dużo nieudanych prób. Odczekaj kwadrans i spróbuj ponownie."
JOIN_SESSION_KEY = "join_code_id"
# Hasło się zgadza, czekamy na kod z aplikacji: {"user": pk, "backend": ..., "at": czas}.
PENDING_SESSION_KEY = "two_factor_pending"
PENDING_SECONDS = 5 * 60
# Sekret nowo włączanego logowania dwuskładnikowego, zanim osoba potwierdzi go pierwszym kodem.
SETUP_SESSION_KEY = "two_factor_setup_secret"
WRONG_CODE_MESSAGE = "Ten kod nie pasuje. Sprawdź, czy wpisujesz aktualny kod z aplikacji."


def needs_two_factor_setup(user):
    """Konto master bez logowania dwuskładnikowego: najpierw musi je włączyć."""
    return (
        settings.ARCHIVEHUB_MASTER_2FA
        and user.is_authenticated
        and user.is_superuser
        and not user.has_two_factor
    )


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
        if needs_two_factor_setup(request.user):
            return redirect("two_factor")
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
                logger.warning("Nieudane logowanie: %s z %s", username, ratelimit.client_ip(request))
                error = "Nieprawidłowy nick lub hasło."
            elif user.has_two_factor:
                ratelimit.clear("login", request, username)
                request.session[PENDING_SESSION_KEY] = {
                    "user": user.pk,
                    "backend": user.backend,
                    "at": time.time(),
                }
                target = reverse("login_two_factor")
                if next_url := request.POST.get("next"):
                    target += "?" + urlencode({"next": next_url})
                return redirect(target)
            else:
                ratelimit.clear("login", request, username)
                return _finish_login(request, user)

    return render(
        request,
        "accounts/login.html",
        {
            "form": form,
            "error": error,
            "next": request.GET.get("next", ""),
            "login_photos": login_background(),
        },
        status=429 if error == BLOCKED_MESSAGE else 200,
    )


def _finish_login(request, user, backend=None, method="hasło"):
    login(request, user, backend=backend)
    if user.is_superuser:
        request.session.set_expiry(settings.ARCHIVEHUB_MASTER_SESSION_DAYS * 24 * 60 * 60)
    logger.info("Logowanie: %s z %s (%s)", user.username, ratelimit.client_ip(request), method)
    if needs_two_factor_setup(user):
        return redirect("two_factor")
    return redirect(_safe_next(request))


def _pending_user(request):
    pending = request.session.get(PENDING_SESSION_KEY)
    if not pending or time.time() - pending.get("at", 0) > PENDING_SECONDS:
        request.session.pop(PENDING_SESSION_KEY, None)
        return None, None
    user = get_user_model().objects.filter(pk=pending["user"], is_active=True).first()
    return user, pending.get("backend")


def check_second_factor(user, raw_code):
    """Sprawdza kod z aplikacji albo kod zapasowy. Zwraca "totp", "recovery" albo None."""
    counter = totp.verify(user.totp_secret, raw_code, user.totp_last_counter)
    if counter is not None:
        # Warunek w zapytaniu: dwa równoczesne żądania z tym samym kodem nie przejdą oba.
        updated = get_user_model().objects.filter(pk=user.pk, totp_last_counter__lt=counter)
        if updated.update(totp_last_counter=counter):
            user.totp_last_counter = counter
            return "totp"
        return None
    code_hash = totp.hash_recovery_code(raw_code)
    if RecoveryCode.objects.filter(user=user, code_hash=code_hash, used_at=None).update(
        used_at=timezone.now()
    ):
        return "recovery"
    return None


@never_cache
@sensitive_post_parameters("code")
@require_http_methods(["GET", "HEAD", "POST"])
def login_two_factor_view(request):
    """Drugi krok logowania: kod z aplikacji w telefonie."""
    if request.user.is_authenticated:
        return redirect(_safe_next(request))
    user, backend = _pending_user(request)
    if user is None:
        messages.info(request, "Zaloguj się jeszcze raz: minęło zbyt dużo czasu.")
        return redirect("login")

    form = SecondFactorForm(request.POST or None)
    error = None
    if request.method == "POST" and form.is_valid():
        identifier = str(user.pk)
        if ratelimit.is_blocked("totp", request, identifier):
            error = BLOCKED_MESSAGE
            logger.warning("Zablokowany kod 2FA: %s z %s", user.username, ratelimit.client_ip(request))
        elif method := check_second_factor(user, form.cleaned_data["code"]):
            ratelimit.clear("totp", request, identifier)
            request.session.pop(PENDING_SESSION_KEY, None)
            if method == "recovery":
                left = user.recovery_codes.filter(used_at=None).count()
                messages.warning(
                    request,
                    f"Użyto kodu zapasowego. Zostało ich {left}. "
                    "Jeśli zgubiłeś(-aś) telefon, ustaw logowanie dwuskładnikowe od nowa.",
                )
            return _finish_login(request, user, backend=backend, method=f"hasło + {method}")
        else:
            ratelimit.record_failure("totp", request, identifier)
            logger.warning("Zły kod 2FA: %s z %s", user.username, ratelimit.client_ip(request))
            error = WRONG_CODE_MESSAGE

    return render(
        request,
        "accounts/login_two_factor.html",
        {"form": form, "error": error, "next": request.GET.get("next", "")},
        status=429 if error == BLOCKED_MESSAGE else 200,
    )


def _new_recovery_codes(user):
    codes = totp.new_recovery_codes()
    with transaction.atomic():
        user.recovery_codes.all().delete()
        RecoveryCode.objects.bulk_create(
            [RecoveryCode(user=user, code_hash=totp.hash_recovery_code(code)) for code in codes]
        )
    return codes


def _show_recovery_codes(request, codes):
    return render(request, "accounts/recovery_codes.html", {"codes": codes})


@never_cache
@login_required
@sensitive_post_parameters("code", "password")
@require_http_methods(["GET", "HEAD", "POST"])
def two_factor_view(request):
    """Włączanie i wyłączanie logowania dwuskładnikowego, nowe kody zapasowe."""
    user = request.user
    action = request.POST.get("action") if request.method == "POST" else None
    if user.has_two_factor:
        return _two_factor_manage(request, user, action)

    secret = request.session.get(SETUP_SESSION_KEY) or totp.new_secret()
    request.session[SETUP_SESSION_KEY] = secret
    form = TwoFactorConfirmForm(request.POST if action == "enable" else None)
    if action == "enable" and form.is_valid():
        counter = totp.verify(secret, form.cleaned_data["code"])
        if counter is None:
            form.add_error("code", WRONG_CODE_MESSAGE)
        else:
            user.totp_secret = secret
            user.totp_enabled_at = timezone.now()
            user.totp_last_counter = counter
            user.save(update_fields=["totp_secret", "totp_enabled_at", "totp_last_counter"])
            request.session.pop(SETUP_SESSION_KEY, None)
            # Nowy skrót sesji: inne urządzenia zostają wylogowane, to zostaje zalogowane.
            update_session_auth_hash(request, user)
            logger.info("Logowanie dwuskładnikowe włączone: %s", user.username)
            messages.success(request, "Logowanie dwuskładnikowe jest włączone.")
            return _show_recovery_codes(request, _new_recovery_codes(user))

    uri = totp.provisioning_uri(secret, user.username, settings.SITE_TITLE)
    return render(
        request,
        "accounts/two_factor_setup.html",
        {
            "form": form,
            "qr": totp.qr_data_uri(uri),
            "secret": totp.format_secret(secret),
            "required": needs_two_factor_setup(user),
        },
    )


def _two_factor_manage(request, user, action):
    codes_form = TwoFactorConfirmForm(request.POST if action == "codes" else None, prefix="codes")
    disable_form = TwoFactorDisableForm(request.POST if action == "disable" else None, prefix="disable")

    if action == "codes" and codes_form.is_valid():
        if check_second_factor(user, codes_form.cleaned_data["code"]) == "totp":
            logger.info("Nowe kody zapasowe: %s", user.username)
            messages.success(request, "Nowe kody zapasowe są gotowe. Poprzednie przestały działać.")
            return _show_recovery_codes(request, _new_recovery_codes(user))
        codes_form.add_error("code", WRONG_CODE_MESSAGE)

    if action == "disable" and disable_form.is_valid():
        if not user.check_password(disable_form.cleaned_data["password"]):
            disable_form.add_error("password", "To nie jest Twoje hasło.")
        elif not check_second_factor(user, disable_form.cleaned_data["code"]):
            disable_form.add_error("code", WRONG_CODE_MESSAGE)
        else:
            user.totp_secret = ""
            user.totp_enabled_at = None
            user.totp_last_counter = 0
            user.save(update_fields=["totp_secret", "totp_enabled_at", "totp_last_counter"])
            user.recovery_codes.all().delete()
            update_session_auth_hash(request, user)
            logger.warning("Logowanie dwuskładnikowe wyłączone: %s", user.username)
            messages.success(request, "Logowanie dwuskładnikowe jest wyłączone.")
            return redirect("two_factor")

    return render(
        request,
        "accounts/two_factor_manage.html",
        {
            "codes_form": codes_form,
            "disable_form": disable_form,
            "codes_left": user.recovery_codes.filter(used_at=None).count(),
            "master_required": settings.ARCHIVEHUB_MASTER_2FA and user.is_superuser,
        },
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


@login_required
@require_http_methods(["GET", "HEAD", "POST"])
def add_code_view(request):
    """„Mam kolejny kod”: zalogowana osoba dołącza do następnej grupy bez zakładania konta."""
    form = JoinCodeForm(request.POST or None)
    error = None
    if request.method == "POST" and form.is_valid():
        if ratelimit.is_blocked("code", request):
            error = BLOCKED_MESSAGE
        else:
            code = InviteCode.objects.filter(code=InviteCode.normalize(form.cleaned_data["code"])).first()
            if code is None or code.unusable_reason() is not None:
                ratelimit.record_failure("code", request)
                error = "Ten kod nie działa. Sprawdź pisownię albo poproś o nowy."
            elif request.user.family_groups.filter(pk=code.group_id).exists():
                messages.info(request, f"Już należysz do grupy „{code.group}”.")
                return redirect("archive")
            else:
                request.user.family_groups.add(code.group)
                logger.info("%s dołączył(a) kodem %s do grupy %s", request.user.username, code.pk, code.group)
                messages.success(request, f"Dołączono do grupy „{code.group}”. Jej albumy są już widoczne.")
                return redirect("archive")

    return render(
        request,
        "accounts/add_code.html",
        {"form": form, "error": error},
        status=429 if error == BLOCKED_MESSAGE else 200,
    )


class OwnPasswordChangeView(PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("archive")

    def form_valid(self, form):
        messages.success(self.request, "Hasło zostało zmienione.")
        return super().form_valid(form)
