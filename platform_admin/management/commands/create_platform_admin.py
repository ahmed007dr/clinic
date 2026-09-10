"""Create a platform operator — the account that opens the owner portal.

Without this the portal had no front door: `is_platform_staff` is not exposed
in Django admin (deliberately — ticking it in the wrong screen is how a clinic
user would acquire cross-clinic reach), so the only way to make an operator was
a hand-typed shell session.

An operator belongs to **no clinic**. `is_platform_staff` requires
`tenant_id is None`, and this command makes that true rather than trusting a
flag on its own.

    python manage.py create_platform_admin owner@example.com
"""

import sys

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.utils.crypto import get_random_string

from tenants.provisioning import PASSWORD_ALPHABET

User = get_user_model()


class Command(BaseCommand):
    help = "Create a platform operator account for the owner portal (/app/platform)."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("--username", default="owner")
        parser.add_argument(
            "--password",
            help="Omit to generate one. It is printed once and cannot be recovered.",
        )

    def handle(self, *args, **options):
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")

        email = options["email"].strip().lower()
        try:
            validate_email(email)
        except ValidationError:
            raise CommandError(f"{email!r} is not a valid email address.")
        if User.objects.filter(email__iexact=email).exists():
            raise CommandError(f"A user with email {email!r} already exists.")

        password = options["password"] or get_random_string(16, allowed_chars=PASSWORD_ALPHABET)
        User.objects.create_user(
            username=options["username"],
            email=email,
            password=password,
            tenant=None,
            is_platform_staff=True,
        )

        self.stdout.write(self.style.SUCCESS("Platform operator created."))
        self.stdout.write(f"  login    {email}")
        if not options["password"]:
            self.stdout.write(f"  password {password}")
            self.stdout.write(self.style.WARNING("           shown once — store it securely"))
        self.stdout.write("  portal   /app/platform")
