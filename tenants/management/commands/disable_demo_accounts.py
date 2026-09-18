"""Switch off the demo dataset's logins before a clinic starts real work.

The system is delivered with `seed_demo` data, so its logins — `admin@…`,
`clinicadmin@…`, `reception@…` and `doctor@…` on a `.local` domain — exist on
the production server, and so do the two demo patients' portal logins
(`patient1@…`, `patient2@…`). They must not outlive the handover: whoever saw the
seeder's output can sign in with them.

    python manage.py disable_demo_accounts --dry-run   # list, change nothing
    python manage.py disable_demo_accounts

Deactivated, not deleted: the demo appointments, payments and audit entries
still point at these users, and deleting them would either fail on a PROTECT
or orphan that history. A deactivated account cannot sign in, and a session
it already had stops working on its next request.
"""

import re

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

# The exact addresses seed_demo creates: "<role>@<tenant-slug>.local". Matched
# precisely rather than by ".local" alone, so a real account that happens to
# use a .local address is never swept up with the demo ones.
DEMO_LOCAL_PARTS = ("admin", "clinicadmin", "reception", "doctor")
DEMO_EMAIL = re.compile(
    rf"^(?:{'|'.join(DEMO_LOCAL_PARTS)})@[a-z0-9-]+\.local$", re.IGNORECASE
)


# The demo patients' portal logins: "patient1@<slug>.local", "patient2@<slug>.local".
DEMO_PATIENT_EMAIL = re.compile(r"^patient[12]@[a-z0-9-]+\.local$", re.IGNORECASE)


def demo_patient_accounts():
    """Active portal logins of the demo patients, across every clinic.

    Portal accounts are tenant-owned (row-level security), so each clinic is
    entered in turn; a real patient is never matched, because the address must
    be exactly one seed_demo gives its demo patients.
    """
    from portal.models import PatientAccount
    from tenants.context import tenant_context
    from tenants.models import Tenant

    found = []
    for tenant in Tenant.objects.all():
        with tenant_context(tenant):
            for account in PatientAccount.objects.filter(
                is_active=True, patient__email__iendswith=".local"
            ).select_related("patient"):
                if DEMO_PATIENT_EMAIL.match(account.patient.email or ""):
                    found.append((tenant, account.pk, account.patient.phone1, account.patient.email))
    return found


def demo_accounts():
    """Active clinic users whose address is one seed_demo creates.

    `accounts_user` is not under row-level security (authentication has to find
    a user before any tenant is known), so this sees every clinic's users
    without binding one.
    """
    User = get_user_model()
    candidates = (
        User.objects.filter(email__iendswith=".local", is_active=True)
        .filter(is_superuser=False, is_platform_staff=False)
        .exclude(tenant=None)
        .order_by("email")
    )
    return [user for user in candidates if DEMO_EMAIL.match(user.email)]


class Command(BaseCommand):
    help = "Deactivate the demo accounts created by seed_demo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List the accounts that would be deactivated and change nothing.",
        )

    def handle(self, *args, **options):
        accounts = demo_accounts()
        patients = demo_patient_accounts()
        if not accounts and not patients:
            self.stdout.write("No active demo accounts found.")
            return

        for user in accounts:
            self.stdout.write(f"  {user.email}")
        for tenant, _pk, phone, _email in patients:
            self.stdout.write(f"  portal {tenant.slug}: {phone}")

        if options["dry_run"]:
            self.stdout.write(
                f"Dry run: {len(accounts) + len(patients)} account(s) would be deactivated."
            )
            return

        self._deactivate_patients(patients)

        User = get_user_model()
        count = User.objects.filter(pk__in=[user.pk for user in accounts]).update(
            is_active=False
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Deactivated {count + len(patients)} demo account(s). Their records are kept."
            )
        )

    def _deactivate_patients(self, patients):
        """Stop the demo patients' portal logins and end their live sessions."""
        from portal.models import PatientAccount
        from tenants.context import tenant_context

        for tenant, pk, _phone, _email in patients:
            with tenant_context(tenant):
                account = PatientAccount.objects.filter(pk=pk).first()
                if account is not None:
                    account.is_active = False
                    account.save(update_fields=["is_active"])
                    account.revoke_sessions()
