import sqlite3
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.utils import timezone

from core.backup import configured_dir, database_path, fallback_dir, list_backups


class Command(BaseCommand):
    help = (
        "Przywraca bazę z kopii. Najpierw zatrzymaj aplikację i workera (instrukcja w README)."
        " Obecna baza zostaje zachowana obok kopii jako archivehub-przed-przywroceniem-….sqlite3."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "plik", nargs="?", help="Nazwa pliku kopii lub pełna ścieżka. Bez nazwy: lista kopii."
        )
        parser.add_argument("--tak", action="store_true", help="Bez pytania o potwierdzenie.")

    def handle(self, *args, plik=None, tak=False, **options):
        directories = [configured_dir(), fallback_dir()]
        if not plik:
            for directory in directories:
                for backup in list_backups(directory):
                    self.stdout.write(f"{backup.path}  {backup.size // 1024} kB")
            return

        source = Path(plik)
        if not source.is_absolute():
            source = next((d / plik for d in directories if (d / plik).is_file()), source)
        if not source.is_file():
            raise CommandError(
                f"Nie ma pliku {plik}. Uruchom polecenie bez nazwy, żeby zobaczyć listę kopii."
            )

        check = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
        try:
            result = check.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            check.close()
        if result != "ok":
            raise CommandError(f"Plik kopii jest uszkodzony: {result}")

        target = database_path()
        if not tak:
            answer = input(f"Zastąpić bazę {target} kopią {source.name}? Wpisz „tak”: ")
            if answer.strip().lower() != "tak":
                raise CommandError("Przerwano, baza bez zmian.")

        connections.close_all()
        safety = (
            source.parent / f"archivehub-przed-przywroceniem-{timezone.localtime():%Y-%m-%d_%H%M%S}.sqlite3"
        )
        live = sqlite3.connect(target)
        src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
        try:
            if target.exists():
                with sqlite3.connect(safety) as copy:
                    live.backup(copy)
            # Kopiowanie przez SQLite, a nie podmiana pliku: pliki -wal i -shm zostają spójne.
            with live:
                src.backup(live)
        finally:
            src.close()
            live.close()
        self.stdout.write(self.style.SUCCESS(f"Przywrócono bazę z {source.name}. Poprzednia baza: {safety}"))
        self.stdout.write("Uruchom teraz aplikację: docker compose --profile tunnel up -d")
