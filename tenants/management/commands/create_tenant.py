"""Onboard a new clinic (TENANT-008).

    python manage.py create_tenant "Nile Clinic" --admin-email admin@nile.example

Produces a tenant that is usable immediately: default roles, the Doctor
employee type, a first branch, and an admin who can log in. Everything runs in
one transaction — a half-provisioned tenant nobody can log into is worse than
no tenant at all.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction
from django.utils.text import slugify

from tenants.models import Tenant
from tenants.provisioning import (
    create_first_branch,
    create_tenant_admin,
    provision_tenant_defaults,
)

User = get_user_model()


def _force_utf8(wrapper):
    """Windows consoles default to cp1252, which cannot encode Arabic.

    Branch names here are usually Arabic, so without this the command dies
    mid-report — and it died *after* committing but *before* printing the
    generated password, which is not recoverable.
    """
    stream = getattr(wrapper, "_out", wrapper)
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


class Command(BaseCommand):
    help = "Provision a new tenant with its defaults, first branch and first admin user."

    def add_arguments(self, parser):
        parser.add_argument("name", help='Clinic business name, e.g. "Nile Clinic"')
        parser.add_argument("--slug", help="URL/subdomain identifier (defaults to a slug of the name)")
        parser.add_argument("--admin-email", required=True, help="Login for the first admin")
        parser.add_argument("--admin-username", default="admin", help="Display name for the first admin")
        parser.add_argument("--admin-password", help="Omit to have one generated and shown once")
        parser.add_argument("--branch", default="Main", help="Name of the first branch")
        parser.add_argument("--branch-code", help="Short code for the first branch")
        parser.add_argument(
            "--status",
            default=Tenant.Status.TRIAL,
            choices=[c[0] for c in Tenant.Status.choices],
        )

    def handle(self, *args, **options):
        _force_utf8(self.stdout)

        name = options["name"].strip()
        slug = (options["slug"] or slugify(name)).strip()
        email = options["admin_email"].strip().lower()

        if not slug:
            raise CommandError(
                "Could not derive a slug from that name (non-ASCII names produce an "
                "empty slug) — pass --slug explicitly."
            )

        try:
            validate_email(email)
        except ValidationError:
            raise CommandError(f"{email!r} is not a valid email address.")

        # Fail before creating anything, with a message rather than a traceback.
        if Tenant.objects.filter(slug=slug).exists():
            raise CommandError(f"A tenant with slug {slug!r} already exists.")
        if User.objects.filter(email__iexact=email).exists():
            raise CommandError(f"A user with email {email!r} already exists.")

        with transaction.atomic():
            tenant = Tenant.objects.create(name=name, slug=slug, status=options["status"])
            provision_tenant_defaults(tenant)
            branch = create_first_branch(tenant, options["branch"], options["branch_code"])
            admin, password = create_tenant_admin(
                tenant,
                email=email,
                password=options["admin_password"],
                username=options["admin_username"],
                branch=branch,
            )

        generated = not options["admin_password"]
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Tenant '{tenant.name}' provisioned."))

        # Credentials first: the generated password cannot be recovered, so it
        # must not sit behind anything that could fail to print.
        self.stdout.write(f"  login    {admin.email}")
        if generated:
            self.stdout.write(f"  password {password}")
            self.stdout.write(
                self.style.WARNING("           shown once — hand it over securely")
            )
        self.stdout.write(f"  slug     {tenant.slug}")
        self.stdout.write(f"  status   {tenant.status}")
        self.stdout.write(f"  branch   {branch.name} ({branch.code})")
        self.stdout.write("")
