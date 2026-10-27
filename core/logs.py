"""Dziennik zdarzeń w bazie: handler logowania, który zapisuje wybrane wpisy do :class:`core.models.Event`.

Zapisujemy ostrzeżenia i błędy z całej aplikacji oraz zwykłe wpisy z kont (logowania, 2FA).
Zapis nigdy nie może zepsuć żądania: każdy błąd handlera jest po cichu pomijany.
"""

import logging
import random
import threading
from datetime import timedelta

KEEP_DAYS = 90
KEEP_ROWS = 10_000
# Sprzątanie przy co mniej więcej pięćdziesiątym wpisie wystarcza, tabela i tak rośnie powoli.
PRUNE_CHANCE = 0.02
MAX_MESSAGE = 4000

_local = threading.local()


class DatabaseHandler(logging.Handler):
    def emit(self, record):
        if getattr(_local, "busy", False):
            return  # błąd zapisu sam coś zalogował: nie wpadamy w pętlę
        _local.busy = True
        try:
            from django.utils import timezone

            from .models import Event

            message = record.getMessage()
            if record.exc_info:
                message += "\n" + logging.Formatter().formatException(record.exc_info)
            Event.objects.create(
                level=record.levelno, source=record.name[:100], message=message[:MAX_MESSAGE]
            )
            if random.random() < PRUNE_CHANCE:  # noqa: S311 - to nie kryptografia
                prune(timezone.now())
        except Exception:  # noqa: BLE001, S110 - dziennik nie może zepsuć żądania
            pass
        finally:
            _local.busy = False


def prune(now):
    from .models import Event

    Event.objects.filter(created_at__lt=now - timedelta(days=KEEP_DAYS)).delete()
    cutoff = Event.objects.order_by("-pk").values_list("pk", flat=True)[KEEP_ROWS : KEEP_ROWS + 1]
    if cutoff:
        Event.objects.filter(pk__lte=cutoff[0]).delete()


class EventFilter(logging.Filter):
    """Do dziennika: ostrzeżenia i błędy zewsząd, a z kont także zwykłe wpisy (logowania)."""

    def filter(self, record):
        # „Nie znaleziono” to zwykle boty zgadujące adresy; zostaje tylko w logach Dockera.
        if getattr(record, "status_code", None) in (404, 405):
            return False
        # Serwer deweloperski loguje każde żądanie; a 503 z /healthz/pelny opisuje już Stan serwera.
        if record.name == "django.server":
            return False
        request = getattr(record, "request", None)
        if request is not None and getattr(request, "path", "").startswith("/healthz"):
            return False
        return record.levelno >= logging.WARNING or record.name.startswith("accounts")
