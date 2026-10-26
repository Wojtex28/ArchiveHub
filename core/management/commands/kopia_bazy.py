from django.core.management.base import BaseCommand, CommandError

from core.backup import BackupError, make_backup


class Command(BaseCommand):
    help = "Robi kopię bazy teraz (np. przed aktualizacją). Codzienne kopie robi worker sam."

    def handle(self, *args, **options):
        try:
            backup = make_backup()
        except BackupError as exc:
            raise CommandError(f"Kopia się nie udała: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"Kopia gotowa: {backup.path} ({backup.size // 1024} kB)"))
