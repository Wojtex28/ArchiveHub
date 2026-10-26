"""Codzienna kopia bazy danych.

Worker raz na dobę (po godzinie ``ARCHIVEHUB_BACKUP_HOUR``) robi spójną kopię bazy SQLite
przez wbudowane w SQLite kopiowanie na żywo: aplikacja działa dalej, a kopia jest
sprawdzana (``PRAGMA integrity_check``), zanim dostanie właściwą nazwę.

Rotacja: zostaje najnowsza kopia z każdego z ostatnich ``ARCHIVEHUB_BACKUP_DAILY`` dni,
w których powstała kopia, i najnowsza z każdego z ostatnich ``ARCHIVEHUB_BACKUP_MONTHLY``
miesięcy. Obok bazy trafiają zdjęcia tła logowania (mały folder, nie ma ich nigdzie indziej).

Folder kopii to na serwerze katalog na datasecie (``/kopie`` w kontenerze), więc obejmują
go snapshoty ZFS i zadanie Cloud Sync do Google Drive (instrukcja w README).
"""

import json
import logging
import os
import re
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

NAME_RE = re.compile(r"^archivehub-(\d{4}-\d{2}-\d{2})_(\d{4})\.sqlite3$")
LOGIN_PHOTOS_SUBDIR = "tlo-logowania"
STATUS_FILE = "kopia-bazy.json"
# Tyle godzin bez nowej kopii i panel pokazuje ostrzeżenie.
STALE_HOURS = 36


class BackupError(Exception):
    pass


@dataclass
class Backup:
    path: Path
    created: datetime

    @property
    def name(self):
        return self.path.name

    @property
    def size(self):
        return self.path.stat().st_size


def database_path():
    return Path(settings.DATABASES["default"]["NAME"])


def configured_dir():
    return Path(settings.ARCHIVEHUB_BACKUP_DIR)


def fallback_dir():
    return Path(settings.DATA_DIR) / "kopie"


def _writable(directory):
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".zapis-"):
            pass
    except OSError:
        return False
    return True


def target_dir():
    """Folder kopii i informacja, czy to awaryjny folder w wolumenie danych."""
    directory = configured_dir()
    if _writable(directory):
        return directory, False
    fallback = fallback_dir()
    if fallback != directory and _writable(fallback):
        return fallback, True
    raise BackupError(f"Nie mogę zapisać kopii ani w {directory}, ani w {fallback}.")


def list_backups(directory):
    backups = []
    if not directory.is_dir():
        return backups
    for path in directory.iterdir():
        if match := NAME_RE.match(path.name):
            created = datetime.strptime(f"{match[1]} {match[2]}", "%Y-%m-%d %H%M")
            backups.append(Backup(path, timezone.make_aware(created)))
    backups.sort(key=lambda backup: backup.created, reverse=True)
    return backups


def _copy_database(source, destination):
    """Spójna kopia bazy na żywo (SQLite backup API) i sprawdzenie, że się otwiera."""
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(destination)
    try:
        with dst:
            src.backup(dst)
        # Kopia ma być jednym plikiem, bez -wal i -shm obok (łatwiej ją przenieść i przywrócić).
        dst.execute("PRAGMA journal_mode=DELETE")
        result = dst.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        dst.close()
        src.close()
    if result != "ok":
        raise BackupError(f"Kopia bazy nie przeszła sprawdzenia: {result}")


def _mirror_login_photos(directory):
    source = Path(settings.ARCHIVEHUB_LOGIN_PHOTOS_DIR)
    target = directory / LOGIN_PHOTOS_SUBDIR
    if not source.is_dir():
        return
    target.mkdir(exist_ok=True)
    wanted = {path.name for path in source.iterdir() if path.is_file()}
    for name in wanted:
        if not (target / name).exists():
            shutil.copy2(source / name, target / name)
    for path in target.iterdir():
        if path.is_file() and path.name not in wanted:
            path.unlink()


def prune(directory, daily=None, monthly=None):
    """Usuwa kopie spoza rotacji. Zwraca listę usuniętych nazw."""
    daily = settings.ARCHIVEHUB_BACKUP_DAILY if daily is None else daily
    monthly = settings.ARCHIVEHUB_BACKUP_MONTHLY if monthly is None else monthly
    keep, days, months = set(), set(), set()
    for backup in list_backups(directory):  # od najnowszej
        local = timezone.localtime(backup.created)
        day, month = local.date(), (local.year, local.month)
        if day not in days and len(days) < daily:
            keep.add(backup.path)
        if month not in months and len(months) < monthly:
            keep.add(backup.path)
        days.add(day)
        months.add(month)
    removed = []
    for backup in list_backups(directory):
        if backup.path not in keep:
            backup.path.unlink()
            removed.append(backup.name)
    return removed


def _status_path():
    return Path(settings.DATA_DIR) / STATUS_FILE


def write_status(**data):
    path = _status_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    os.replace(tmp, path)


def read_status():
    """Stan ostatniej kopii dla panelu: słownik albo None, gdy kopii jeszcze nie było."""
    try:
        data = json.loads(_status_path().read_text())
    except (OSError, ValueError):
        return None
    for key in ("last", "attempt"):
        if data.get(key):
            data[key] = datetime.fromisoformat(data[key])
    last = data.get("last")
    data["stale"] = last is None or timezone.now() - last > timedelta(hours=STALE_HOURS)
    return data


def make_backup(now=None):
    """Robi kopię bazy, sprząta stare kopie i zapisuje stan dla panelu. Zwraca :class:`Backup`."""
    now = timezone.localtime(now)
    previous = read_status() or {}
    try:
        directory, fallback = target_dir()
        final = directory / f"archivehub-{now:%Y-%m-%d_%H%M}.sqlite3"
        tmp = directory / f".{final.name}.tmp"
        try:
            _copy_database(database_path(), tmp)
            os.replace(tmp, final)
        finally:
            tmp.unlink(missing_ok=True)
        _mirror_login_photos(directory)
        removed = prune(directory)
    except (OSError, sqlite3.Error, BackupError) as exc:
        logger.exception("Kopia bazy: błąd")
        write_status(
            last=previous.get("last") and previous["last"].isoformat(),
            file=previous.get("file"),
            dir=previous.get("dir"),
            size=previous.get("size"),
            count=previous.get("count"),
            fallback=previous.get("fallback", False),
            attempt=now.isoformat(),
            error=str(exc),
        )
        raise BackupError(str(exc)) from exc

    backups = list_backups(directory)
    backup = Backup(final, now)
    write_status(
        last=now.isoformat(),
        file=final.name,
        dir=str(directory),
        size=backup.size,
        count=len(backups),
        fallback=fallback,
        attempt=now.isoformat(),
        error=None,
    )
    if fallback:
        logger.warning(
            "Kopia bazy: brak zapisu w %s, kopia trafiła do %s (wolumen danych)", configured_dir(), directory
        )
    logger.info(
        "Kopia bazy: %s (%s kB), kopii: %s, usunięte: %s",
        final.name,
        backup.size // 1024,
        len(backups),
        ", ".join(removed) or "brak",
    )
    return backup


def backup_due(now=None):
    """Czy pora na dzisiejszą kopię: po ustalonej godzinie i jeszcze bez kopii z tego dnia."""
    now = timezone.localtime(now)
    if now.hour < settings.ARCHIVEHUB_BACKUP_HOUR:
        return False
    status = read_status()
    if status and status.get("attempt") and status.get("error"):
        # Po błędzie próbujemy ponownie najwcześniej za godzinę, żeby nie zasypać logów.
        if now - status["attempt"] < timedelta(hours=1):
            return False
    last = status and status.get("last")
    return not last or timezone.localtime(last).date() < now.date()


def run_scheduled_backup(now=None):
    if not backup_due(now):
        return None
    try:
        return make_backup(now)
    except BackupError:
        return None
