from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Wyłącza logowanie dwuskładnikowe wskazanego konta (zgubiony telefon i kody zapasowe)."
        " Po zalogowaniu samym hasłem trzeba je włączyć od nowa."
    )

    def add_arguments(self, parser):
        parser.add_argument("nick", help="Nick konta, np. wojtek.")

    def handle(self, *args, nick, **options):
        user = get_user_model().objects.filter(username__iexact=nick).first()
        if user is None:
            raise CommandError(f"Nie ma konta „{nick}”.")
        if not user.has_two_factor:
            self.stdout.write(f"Konto {user.username} nie ma włączonego logowania dwuskładnikowego.")
            return
        user.totp_secret = ""
        user.totp_enabled_at = None
        user.totp_last_counter = 0
        user.save(update_fields=["totp_secret", "totp_enabled_at", "totp_last_counter"])
        user.recovery_codes.all().delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Wyłączono logowanie dwuskładnikowe konta {user.username}. Zaloguj się hasłem"
                " i od razu włącz je ponownie (panel o to poprosi)."
            )
        )
