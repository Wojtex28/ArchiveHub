"""Stan serwera: czy działa wszystko, czego rodzina nie widzi, a co musi działać.

Te same sprawdzenia pokazuje Panel → Stan serwera i adres dla monitoringu (``/healthz/pelny``),
z którego zewnętrzna usługa (np. UptimeRobot) wysyła maila, gdy coś przestanie działać.
"""

import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.template.defaultfilters import filesizeformat

from . import backup

# Worker zapisuje znacznik życia po każdym przejściu (co 30 s) i przy każdym zdjęciu.
WORKER_STALE_SECONDS = 10 * 60
# Poniżej tego wolnego miejsca ostrzegamy (bajty i procent dysku).
DISK_WARN_BYTES = 5 * 1024**3
DISK_WARN_PERCENT = 5


@dataclass
class Check:
    key: str
    label: str
    ok: bool
    detail: str


def _ago(seconds):
    seconds = int(seconds)
    if seconds < 90:
        return "przed chwilą"
    if seconds < 90 * 60:
        return f"{seconds // 60} min temu"
    if seconds < 36 * 3600:
        return f"{seconds // 3600} godz. temu"
    return f"{seconds // 86400} dni temu"


def check_database():
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:  # noqa: BLE001
        return Check("baza", "Baza danych", False, f"nie odpowiada: {exc}")
    return Check("baza", "Baza danych", True, "odpowiada")


def check_worker(now=None):
    now = time.time() if now is None else now
    path = Path(settings.DATA_DIR) / "import-worker.heartbeat"
    try:
        age = now - path.stat().st_mtime
    except OSError:
        return Check("worker", "Worker (import, obroty, kopie)", False, "nie dał jeszcze znaku życia")
    ok = age < WORKER_STALE_SECONDS
    detail = f"ostatni znak życia {_ago(age)}"
    if not ok:
        detail += "; sprawdź: docker compose logs worker"
    return Check("worker", "Worker (import, obroty, kopie)", ok, detail)


def check_backup():
    status = backup.read_status()
    label = "Kopia bazy"
    if not status or not status.get("last"):
        return Check("kopia", label, False, "jeszcze nie powstała")
    detail = f"ostatnia {status['last']:%d.%m.%Y %H:%M}, kopii: {status.get('count')}"
    if status.get("error"):
        return Check("kopia", label, False, f"ostatnia próba nieudana: {status['error']}")
    if status.get("fallback"):
        return Check(
            "kopia", label, False, detail + "; folder kopii nie przyjmuje zapisu (kopie w wolumenie)"
        )
    if status["stale"]:
        return Check("kopia", label, False, detail + "; starsza niż półtorej doby")
    return Check("kopia", label, True, detail)


def check_disk():
    label = "Wolne miejsce na dane"
    try:
        usage = shutil.disk_usage(settings.DATA_DIR)
    except OSError as exc:
        return Check("dysk", label, False, f"nie da się sprawdzić: {exc}")
    percent = usage.free * 100 / usage.total if usage.total else 0
    ok = usage.free >= DISK_WARN_BYTES and percent >= DISK_WARN_PERCENT
    detail = f"{filesizeformat(usage.free)} z {filesizeformat(usage.total)} ({percent:.0f}%)"
    if not ok:
        detail += "; mało miejsca: nowe albumy mogą się nie zaimportować"
    return Check("dysk", label, ok, detail)


def all_checks():
    return [check_database(), check_worker(), check_backup(), check_disk()]
