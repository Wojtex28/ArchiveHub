import logging
import signal
import time

from django.conf import settings
from django.core.management.base import BaseCommand

from albums.importer import import_dir, reset_interrupted, scan_import_dir, touch_heartbeat

logger = logging.getLogger("albums.importer")


class Command(BaseCommand):
    help = "Pilnuje udziału import: gotowe foldery zamienia w albumy. Działa w osobnym kontenerze."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Jedno przejście i koniec.")
        parser.add_argument("--interval", type=int, default=30, help="Sekundy między przejściami.")

    def handle(self, *args, once=False, interval=30, **options):
        self._stop = False
        signal.signal(signal.SIGTERM, self._request_stop)
        signal.signal(signal.SIGINT, self._request_stop)

        if reset_interrupted():
            logger.info("Import: wznawiam przerwane importy")
        logger.info(
            "Import: pilnuję %s (folder gotowy po %s min bez zmian)",
            import_dir(),
            settings.ARCHIVEHUB_IMPORT_STABLE_MINUTES,
        )
        while not self._stop:
            try:
                scan_import_dir()
            except Exception:
                logger.exception("Import: nieoczekiwany błąd przejścia")
            touch_heartbeat()
            if once:
                break
            for _ in range(interval):
                if self._stop:
                    break
                time.sleep(1)

    def _request_stop(self, *_):
        self._stop = True
