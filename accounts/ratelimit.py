"""Prosty limit nieudanych prób (logowanie, kody rodzinne).

Liczymy nieudane próby w bazie, osobno dla adresu IP i dla loginu/kodu.
Baza jest wspólna dla wszystkich procesów Gunicorna, więc limit działa
niezależnie od tego, który proces obsłuży żądanie.
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import FailedAttempt

WINDOW = timedelta(minutes=15)

# (zakres, rodzaj klucza) -> maksymalna liczba nieudanych prób w oknie
LIMITS = {
    ("login", "ip"): 20,
    ("login", "user"): 8,
    ("code", "ip"): 10,
}


def client_ip(request):
    header = getattr(settings, "ARCHIVEHUB_CLIENT_IP_HEADER", "")
    if header:
        value = request.META.get(header, "").strip()
        if value:
            return value
    return request.META.get("REMOTE_ADDR", "")


def _keys(scope, request, identifier=None):
    keys = [("ip", client_ip(request))]
    if identifier is not None and (scope, "user") in LIMITS:
        keys.append(("user", identifier.strip().lower()))
    return keys


def is_blocked(scope, request, identifier=None):
    since = timezone.now() - WINDOW
    for kind, value in _keys(scope, request, identifier):
        limit = LIMITS.get((scope, kind))
        if limit is None:
            continue
        count = FailedAttempt.objects.filter(
            scope=f"{scope}:{kind}", key=value, created_at__gte=since
        ).count()
        if count >= limit:
            return True
    return False


def record_failure(scope, request, identifier=None):
    now = timezone.now()
    FailedAttempt.objects.bulk_create(
        [
            FailedAttempt(scope=f"{scope}:{kind}", key=value[:200], created_at=now)
            for kind, value in _keys(scope, request, identifier)
        ]
    )
    # Sprzątanie starych wpisów, żeby tabela nie rosła bez końca.
    FailedAttempt.objects.filter(created_at__lt=now - WINDOW * 4).delete()


def clear(scope, request, identifier=None):
    for kind, value in _keys(scope, request, identifier):
        if kind == "user":
            FailedAttempt.objects.filter(scope=f"{scope}:{kind}", key=value).delete()
