import logging
import os
import time
from collections import namedtuple

import pytest
from django.urls import reverse
from django.utils import timezone

from core import backup, logs, status
from core.models import Event

Usage = namedtuple("Usage", "total used free")


@pytest.fixture
def data_dir(tmp_path, settings):
    settings.DATA_DIR = tmp_path
    settings.ARCHIVEHUB_BACKUP_DIR = tmp_path / "kopie"
    return tmp_path


def fresh_backup():
    backup.write_status(
        last=timezone.now().isoformat(),
        file="archivehub-x.sqlite3",
        dir="/kopie",
        size=1024,
        count=3,
        fallback=False,
        attempt=timezone.now().isoformat(),
        error=None,
    )


def heartbeat(data_dir, age=0):
    path = data_dir / "import-worker.heartbeat"
    path.touch()
    os.utime(path, (time.time() - age, time.time() - age))


@pytest.fixture
def healthy(data_dir, monkeypatch):
    heartbeat(data_dir)
    fresh_backup()
    monkeypatch.setattr(
        status.shutil, "disk_usage", lambda path: Usage(500 * 1024**3, 100 * 1024**3, 400 * 1024**3)
    )
    return data_dir


# --- Sprawdzenia ------------------------------------------------------------


@pytest.mark.django_db
def test_all_ok(healthy):
    checks = status.all_checks()
    assert [c.key for c in checks] == ["baza", "worker", "kopia", "dysk"]
    assert all(c.ok for c in checks), [c.detail for c in checks]
    assert "400,0" in checks[3].detail


@pytest.mark.django_db
def test_stale_worker(healthy):
    heartbeat(healthy, age=20 * 60)
    check = status.check_worker()
    assert not check.ok
    assert "20 min temu" in check.detail


@pytest.mark.django_db
def test_missing_worker_and_backup(data_dir):
    assert not status.check_worker().ok
    assert status.check_backup().detail == "jeszcze nie powstała"


@pytest.mark.django_db
def test_low_disk(healthy, monkeypatch):
    monkeypatch.setattr(
        status.shutil, "disk_usage", lambda path: Usage(500 * 1024**3, 497 * 1024**3, 3 * 1024**3)
    )
    check = status.check_disk()
    assert not check.ok
    assert "mało miejsca" in check.detail


# --- Adres dla monitoringu --------------------------------------------------


def test_full_health_hidden_without_token(client, settings):
    settings.ARCHIVEHUB_STATUS_TOKEN = ""
    assert client.get("/healthz/pelny?klucz=").status_code == 404


@pytest.mark.django_db
def test_full_health_wrong_token(client, settings):
    settings.ARCHIVEHUB_STATUS_TOKEN = "dobry-klucz"
    assert client.get("/healthz/pelny?klucz=zly").status_code == 404


@pytest.mark.django_db
def test_full_health_ok_and_problem(client, settings, healthy):
    settings.ARCHIVEHUB_STATUS_TOKEN = "dobry-klucz"
    response = client.get("/healthz/pelny?klucz=dobry-klucz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "problemy": []}
    assert response["Cache-Control"] == "no-store"

    heartbeat(healthy, age=3600)
    response = client.get("/healthz/pelny?klucz=dobry-klucz")
    assert response.status_code == 503
    assert response.json() == {"status": "problem", "problemy": ["worker"]}
    # Co 5 minut z monitoringu: to nie zaśmieca dziennika.
    assert not Event.objects.exists()


# --- Dziennik ---------------------------------------------------------------


@pytest.mark.django_db
def test_log_handler_saves_logins_and_problems():
    logging.getLogger("accounts.views").info("Logowanie: karolina z 1.2.3.4")
    logging.getLogger("albums.importer").info("Import: zwykły wpis")  # nie trafia do dziennika
    logging.getLogger("albums.importer").warning("Import: zły plik")
    try:
        raise ValueError("bum")
    except ValueError:
        logging.getLogger("django.request").exception("Internal Server Error: /x/")
    logging.getLogger("django.request").warning("Not Found: /wp-admin/", extra={"status_code": 404})
    logging.getLogger("django.server").warning('"GET /x HTTP/1.1" 500')

    events = list(Event.objects.order_by("pk").values_list("source", "level"))
    assert events == [("accounts.views", 20), ("albums.importer", 30), ("django.request", 40)]
    assert "ValueError: bum" in Event.objects.get(source="django.request").message


def test_log_handler_never_breaks_without_database():
    # Bez dostępu do bazy (tu: test bez django_db) zapis po cichu się nie udaje.
    logging.getLogger("albums.importer").warning("Import: bez bazy")


@pytest.mark.django_db
def test_prune_keeps_recent(monkeypatch):
    monkeypatch.setattr(logs, "KEEP_ROWS", 3)
    for i in range(5):
        Event.objects.create(level=30, source="t", message=str(i))
    old = Event.objects.create(level=30, source="t", message="stary")
    Event.objects.filter(pk=old.pk).update(created_at=timezone.now() - timezone.timedelta(days=100))
    logs.prune(timezone.now())
    assert list(Event.objects.order_by("pk").values_list("message", flat=True)) == ["2", "3", "4"]


# --- Panel ------------------------------------------------------------------


@pytest.mark.django_db
def test_status_page(master_client, healthy):
    Event.objects.create(level=30, source="albums.importer", message="Import: zły plik")
    Event.objects.create(level=20, source="accounts.views", message="Logowanie: karolina")
    response = master_client.get(reverse("panel:server_status"))
    content = response.content.decode()
    assert response.status_code == 200
    assert "Worker (import, obroty, kopie)" in content
    assert "Import: zły plik" in content
    assert "Logowanie: karolina" not in content  # domyślnie same problemy

    content = master_client.get(reverse("panel:server_status") + "?rodzaj=logowania").content.decode()
    assert "Logowanie: karolina" in content
    assert "Import: zły plik" not in content


@pytest.mark.django_db
def test_status_page_only_for_master(client, make_user):
    client.force_login(make_user("karolina"))
    assert client.get(reverse("panel:server_status")).status_code == 404


@pytest.mark.django_db
def test_dashboard_warns_about_problems(master_client, data_dir):
    content = master_client.get(reverse("panel:dashboard")).content.decode()
    assert "Coś na serwerze wymaga uwagi" in content
    assert "worker" in content
