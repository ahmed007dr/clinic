"""Issue every owner group's subscription invoice whose date has come.

Run daily from cron (docs/10-deployment-runbook.md), e.g.:

    15 6 * * *  cd ~/app && ./venv/bin/python manage.py issue_platform_invoices

Groups that are suspended or cancelled are skipped; a group with neither a
plan nor a negotiated price is reported and skipped, not fatal.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from platform_admin import billing
from platform_admin.models import CommercialTerms


class Command(BaseCommand):
    help = "Issue the subscription invoices that are due today."

    def handle(self, *args, **options):
        today = timezone.now().date()
        issued = skipped = 0
        for terms in CommercialTerms.objects.filter(next_invoice_on__lte=today).select_related("customer"):
            customer = terms.customer
            if customer.status in ("suspended", "cancelled"):
                continue
            try:
                invoice = billing.issue_invoice(customer)
            except billing.BillingError as error:
                skipped += 1
                self.stderr.write(f"{customer.slug}: {error}")
                continue
            issued += 1
            self.stdout.write(f"{customer.slug}: {invoice.number} {invoice.total} {invoice.currency}")
        self.stdout.write(self.style.SUCCESS(f"Issued {issued}, skipped {skipped}."))
