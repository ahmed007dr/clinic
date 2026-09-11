"""Clear a platform operator's two-step sign-in — for a lost phone.

The next sign-in then enrols a new authenticator app from scratch (a new
secret and new recovery codes). Run it only after confirming, outside the
system, that the request really comes from that operator.

    python manage.py reset_platform_2fa operator@example.com
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

User = get_user_model()


class Command(BaseCommand):
    help = "Reset a platform operator's two-step sign-in so it is enrolled again."

    def add_arguments(self, parser):
        parser.add_argument("email")

    def handle(self, *args, **options):
        user = User.objects.filter(email__iexact=options["email"].strip(), is_platform_staff=True).first()
        if user is None:
            raise CommandError("No platform operator with that email.")
        user.totp_secret = ""
        user.totp_confirmed_at = None
        user.totp_recovery_codes = []
        user.save(update_fields=["totp_secret", "totp_confirmed_at", "totp_recovery_codes"])
        self.stdout.write(self.style.SUCCESS("Two-step sign-in reset; it will be set up again at the next sign-in."))
