# ruff: noqa: F811  (fikstura dirs z test_import)
from collections import namedtuple
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from albums import importer
from albums.importer import queue_summary, scan_import_dir, share_overview
from albums.models import Album, ImportJob
from panel.views import human_duration

from .test_import import dirs, scan  # noqa: F401

Usage = namedtuple("Usage", "total used free")


def ready(dirs, *names, photos=2):
    for name in names:
        for i in range(photos):
            scan(dirs.ARCHIVEHUB_IMPORT_DIR / name, f"{i:03}.jpg", color=(30 * i, 40, 80))
        scan(dirs.ARCHIVEHUB_IMPORT_DIR / name, "000_r.jpg", color=(9, 9, 9))
    start = timezone.now() - timedelta(minutes=30)
    scan_import_dir(now=start)
    return start + timedelta(minutes=dirs.ARCHIVEHUB_IMPORT_STABLE_MINUTES)


def test_one_album_per_pass(dirs):
    later = ready(dirs, "01_Album", "02_Album", "10_Album")
    assert [j.folder for j in scan_import_dir(now=later)] == ["01_Album"]
    assert [j.folder for j in scan_import_dir(now=later)] == ["02_Album"]
    assert [j.folder for j in scan_import_dir(now=later)] == ["10_Album"]
    assert scan_import_dir(now=later) == []
    job = ImportJob.objects.get(folder="01_Album")
    assert (job.photos_total, job.photos_added, job.reverses_added) == (2, 2, 1)
    assert job.started_at <= job.finished_at


def test_reprocess_also_takes_the_whole_pass(dirs):
    later = ready(dirs, "01_Album")
    scan_import_dir(now=later)
    scan(dirs.ARCHIVEHUB_IMPORT_DIR / "02_Album", "001.jpg")
    scan_import_dir(now=later)  # 02 zauważony
    Album.objects.update(reprocess_requested=True)
    [job] = scan_import_dir(now=later + timedelta(minutes=30))
    assert job.is_reprocess
    [job] = scan_import_dir(now=later + timedelta(minutes=30))
    assert job.folder == "02_Album"


def test_waits_for_disk_space(dirs, monkeypatch, caplog):
    later = ready(dirs, "01_Album")
    monkeypatch.setattr(
        importer.shutil, "disk_usage", lambda p: Usage(100 * 1024**3, 98 * 1024**3, 2 * 1024**3)
    )
    assert scan_import_dir(now=later) == []
    assert scan_import_dir(now=later) == []
    job = ImportJob.objects.get()
    assert job.status == ImportJob.WAITING
    assert "Czeka na miejsce na dysku" in job.note
    assert caplog.text.count("czeka na miejsce na dysku") == 1  # bez powtarzania co 30 s

    monkeypatch.setattr(
        importer.shutil, "disk_usage", lambda p: Usage(600 * 1024**3, 100 * 1024**3, 500 * 1024**3)
    )
    [job] = scan_import_dir(now=later)
    assert job.status == ImportJob.DONE
    assert job.note == ""


def test_share_overview_and_queue_summary(dirs):
    later = ready(dirs, "01_Album", "02_Album", photos=3)
    scan_import_dir(now=later)
    scan(dirs.ARCHIVEHUB_IMPORT_DIR / "03_Nowy", "001.jpg")
    scan(dirs.ARCHIVEHUB_IMPORT_DIR / "03_Nowy", "007_r.jpg")

    folders, needed = share_overview()
    states = {f.name: f.state_label for f in folders}
    assert states == {"01_Album": "zaimportowany", "02_Album": "w kolejce", "03_Nowy": "nowy"}
    nowy = folders[2]
    assert (nowy.photos, nowy.reverses, nowy.orphan_reverses) == (1, 1, ["007_r.jpg"])
    pending_bytes = folders[1].size + folders[2].size
    assert needed == int(pending_bytes * importer.OUTPUT_RATIO)

    summary = queue_summary(folders)
    assert (summary["folders"], summary["photos"], summary["done"]) == (2, 4, 1)
    assert summary["seconds"] is not None  # tempo z zakończonego importu


def test_seconds_left():
    now = timezone.now()
    job = ImportJob(
        status=ImportJob.PROCESSING, photos_total=100, photos_added=25, started_at=now - timedelta(minutes=5)
    )
    assert round(job.seconds_left(now)) == 15 * 60
    assert ImportJob(status=ImportJob.WAITING).seconds_left() is None


def test_human_duration():
    assert human_duration(None) == ""
    assert human_duration(20) == "ok. 1 min"
    assert human_duration(45 * 60) == "ok. 45 min"
    assert human_duration(3 * 3600 + 22 * 60) == "ok. 3 godz. 20 min"
    assert human_duration(2 * 3600 + 2 * 60) == "ok. 2 godz."


def test_sync_page_shows_share_and_progress(master_client, dirs):
    later = ready(dirs, "01_Album", "02_Album")
    scan_import_dir(now=later)
    ImportJob.objects.filter(folder="02_Album").update(
        status=ImportJob.PROCESSING,
        photos_total=40,
        photos_added=10,
        started_at=timezone.now() - timedelta(minutes=2),
    )
    page = master_client.get(reverse("panel:sync")).content.decode()
    assert "Foldery w udziale (2)" in page
    assert "Teraz:</strong> 02_Album, 10 z 40 zdjęć, ok. 6 min do końca" in page
    assert "zaimportowany" in page
    assert "Miejsce:" in page
