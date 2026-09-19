"""E-mail tomorrow's bookings' reminders (docs/15, Phase 9). Run once a day from cron:

    python manage.py send_booking_reminders            # tomorrow, every running group
    python manage.py send_booking_reminders --date 2026-10-01

Each group is read in its own tenant context (row-level security hides the
others), a patient who cannot or does not want to be e-mailed is skipped, and
running it twice in a day sends nothing the second time (the e-mail log is the
record). A group with no mail server set up sends nothing.
"""

from datetime import date

from django.core.management.base import BaseCommand

from notifications.booking import send_reminders
from tenants.context import tenant_context
from tenants.models import Tenant


class Command(BaseCommand):
    help = "Send the day-before reminder e-mails for confirmed bookings."

    def add_arguments(self, parser):
        parser.add_argument("--date", help="The booking day, YYYY-MM-DD (default: tomorrow).")

    def handle(self, *args, **options):
        day = date.fromisoformat(options["date"]) if options.get("date") else None
        total = 0
        for tenant in Tenant.objects.all():
            if not tenant.is_usable:
                continue
            with tenant_context(tenant):
                sent = send_reminders(tenant, day)
            total += sent
            if sent:
                self.stdout.write(f"{tenant.slug}: {sent}")
        self.stdout.write(self.style.SUCCESS(f"Reminders sent: {total}"))
