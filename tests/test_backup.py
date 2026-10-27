import sqlite3
from datetime import datetime, timedelta

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from core import backup


def local(*args):
    return timezone.make_aware(datetime(*args))


@pytest.fixture
def live_db(tmp_path, monkeypatch, settings):
    """Osobna baza SQLite udająca bazę produkcyjną (testy używają bazy w pamięci)."""
    path = tmp_path / "db" / "archivehub.sqlite3"
    path.parent.mkdir()
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE zdjecia (opis TEXT)")
        conn.execute("INSERT INTO zdjecia VALUES ('wesele 1962')")
    monkeypatch.setattr(backup, "database_path", lambda: path)
    settings.DATA_DIR = tmp_path / "data"
    settings.DATA_DIR.mkdir()
    settings.ARCHIVEHUB_BACKUP_DIR = tmp_path / "kopie"
    settings.ARCHIVEHUB_LOGIN_PHOTOS_DIR = tmp_path / "data" / "tlo-logowania"
    return path


def rows(path):
    with sqlite3.connect(path) as conn:
        return [row[0] for row in conn.execute("SELECT opis FROM zdjecia")]


def test_backup_copies_database(live_db, settings):
    made = backup.make_backup(local(2026, 10, 26, 3, 0))
    assert made.path == settings.ARCHIVEHUB_BACKUP_DIR / "archivehub-2026-10-26_0300.sqlite3"
    assert rows(made.path) == ["wesele 1962"]
    # Bez plików tymczasowych.
    assert [p.name for p in settings.ARCHIVEHUB_BACKUP_DIR.iterdir()] == [made.name]

    status = backup.read_status()
    assert status["file"] == made.name
    assert status["count"] == 1
    assert status["error"] is None
    assert status["fallback"] is False


def test_backup_mirrors_login_photos(live_db, settings):
    photos = settings.ARCHIVEHUB_LOGIN_PHOTOS_DIR
    photos.mkdir()
    (photos / "1.jpg").write_bytes(b"a")
    (photos / "2.jpg").write_bytes(b"b")
    backup.make_backup(local(2026, 10, 26, 3, 0))
    (photos / "2.jpg").unlink()
    backup.make_backup(local(2026, 10, 27, 3, 0))
    mirrored = settings.ARCHIVEHUB_BACKUP_DIR / "tlo-logowania"
    assert sorted(p.name for p in mirrored.iterdir()) == ["1.jpg"]


def test_rotation_keeps_days_and_months(tmp_path):
    for day in range(60):
        when = local(2026, 8, 1, 3, 0) + timedelta(days=day)
        (tmp_path / f"archivehub-{when:%Y-%m-%d_%H%M}.sqlite3").write_bytes(b"")
    # Druga kopia tego samego dnia (np. ręczna przed aktualizacją): zostaje nowsza.
    (tmp_path / "archivehub-2026-09-29_1800.sqlite3").write_bytes(b"")
    (tmp_path / "notatka.txt").write_text("nie ruszać")

    backup.prune(tmp_path, daily=14, monthly=12)
    left = sorted(p.name for p in tmp_path.iterdir())
    assert "notatka.txt" in left
    names = [n for n in left if n.endswith(".sqlite3")]
    # 14 ostatnich dni (16.09–29.09) + najnowsze z sierpnia.
    assert len(names) == 15
    assert "archivehub-2026-08-31_0300.sqlite3" in names
    assert "archivehub-2026-09-29_1800.sqlite3" in names
    assert "archivehub-2026-09-29_0300.sqlite3" not in names
    assert "archivehub-2026-09-15_0300.sqlite3" not in names


def test_falls_back_when_folder_not_writable(live_db, settings, monkeypatch):
    blocked = settings.ARCHIVEHUB_BACKUP_DIR
    real = backup._writable
    monkeypatch.setattr(backup, "_writable", lambda d: d != blocked and real(d))
    made = backup.make_backup(local(2026, 10, 26, 3, 0))
    assert made.path.parent == settings.DATA_DIR / "kopie"
    assert backup.read_status()["fallback"] is True


def test_due_once_a_day_after_hour(live_db, settings):
    settings.ARCHIVEHUB_BACKUP_HOUR = 3
    assert not backup.backup_due(local(2026, 10, 26, 2, 59))
    assert backup.backup_due(local(2026, 10, 26, 3, 0))
    assert backup.run_scheduled_backup(local(2026, 10, 26, 3, 0)) is not None
    assert not backup.backup_due(local(2026, 10, 26, 23, 0))
    assert backup.backup_due(local(2026, 10, 27, 9, 0))


def test_failure_is_recorded_and_retried_later(live_db, monkeypatch):
    def broken(source, destination):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(backup, "_copy_database", broken)
    assert backup.run_scheduled_backup(local(2026, 10, 26, 3, 0)) is None
    status = backup.read_status()
    assert "disk I/O error" in status["error"]
    assert not backup.backup_due(local(2026, 10, 26, 3, 30))
    assert backup.backup_due(local(2026, 10, 26, 4, 1))


def test_stale_status(live_db):
    backup.make_backup(timezone.now() - timedelta(hours=40))
    assert backup.read_status()["stale"] is True
    backup.make_backup()
    assert backup.read_status()["stale"] is False


def test_manual_command_and_restore(live_db, settings, capsys):
    call_command("kopia_bazy")
    made = backup.list_backups(settings.ARCHIVEHUB_BACKUP_DIR)[0]

    with sqlite3.connect(live_db) as conn:
        conn.execute("DELETE FROM zdjecia")
    assert rows(live_db) == []

    call_command("przywroc_baze", made.name, "--tak")
    assert rows(live_db) == ["wesele 1962"]
    safety = list(settings.ARCHIVEHUB_BACKUP_DIR.glob("archivehub-przed-przywroceniem-*.sqlite3"))
    assert len(safety) == 1
    assert rows(safety[0]) == []
    # Kopia bezpieczeństwa nie podlega rotacji.
    backup.prune(settings.ARCHIVEHUB_BACKUP_DIR, daily=0, monthly=0)
    assert safety[0].exists()


def test_dashboard_shows_backup_and_2fa(master_client, live_db):
    response = master_client.get(reverse("panel:dashboard"))
    content = response.content.decode()
    assert "Logowanie dwuskładnikowe włączone" in content
    assert "jeszcze nie powstała" in content

    backup.make_backup()
    content = master_client.get(reverse("panel:dashboard")).content.decode()
    assert "kopii: 1" in content
    assert "is-danger" not in content.split("Bezpieczeństwo")[1].split("Ostatnie zdarzenia")[0]
