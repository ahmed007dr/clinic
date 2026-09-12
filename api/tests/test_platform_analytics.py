"""Developer portal, phase 5: the platform's figures."""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment
from billing.models import Payment
from branches.models import Branch
from patients.models import Patient
from platform_admin import billing
from platform_admin.analytics import month_keys
from platform_admin.models import SignupRequest
from subscriptions.models import Plan, Subscription
from tenants.context import tenant_context
from tenants.models import Tenant
from tenants.testing import login_platform

User = get_user_model()


def group(slug, plan, status="active", custom=None, cycle="monthly"):
    tenant = Tenant.objects.create(name=slug, slug=slug, status=status)
    with tenant_context(tenant):
        branch = Branch.all_objects.create(tenant=tenant, name=slug, code=slug[:4].upper())
        Subscription.all_objects.create(tenant=tenant, plan=Plan.objects.get(code=plan), status="active")
    terms = billing.terms_for(tenant)
    terms.custom_price, terms.cycle = custom, cycle
    terms.save()
    return tenant, branch


class AnalyticsTests(TestCase):
    def setUp(self):
        cache.clear()
        Tenant.objects.update(status="trial")  # the default fixture group is out of these sums
        self.basic, branch = group("an-basic", "basic")                          # 500 a month
        group("an-yearly", "basic", custom=Decimal("6000"), cycle="yearly")     # 500 a month
        group("an-trial", "professional", status="trial")                       # not revenue yet
        invoice = billing.issue_invoice(self.basic, period_start=timezone.now().date().replace(day=1))
        billing.record_payment(self.basic, "300", "cash", invoice=invoice)
        SignupRequest.objects.create(group_name="A", owner_name="a", email="a@x.test", phone="1", status="approved")
        SignupRequest.objects.create(group_name="B", owner_name="b", email="b@x.test", phone="1", status="rejected")
        SignupRequest.objects.create(group_name="C", owner_name="c", email="c@x.test", phone="1")
        with tenant_context(self.basic):
            patient = Patient.all_objects.create(tenant=self.basic, name="P", branch=branch)
            visit = Appointment.all_objects.create(tenant=self.basic, patient=patient, branch=branch,
                                                   scheduled_date=timezone.now(), price=200)
            Payment.all_objects.create(tenant=self.basic, appointment=visit, patient=patient, receipt_number="AN1",
                                       amount=200, branch=branch)
        User.objects.create_user(username="root", email="root@ops.local", password="pass12345", tenant=None,
                                 is_platform_staff=True, platform_role="support")
        login_platform(self.client, "root@ops.local")

    def test_the_platform_figures(self):
        data = self.client.get(reverse("api:platform-analytics"), {"months": 6}).json()
        totals = data["totals"]
        self.assertEqual((totals["mrr"], totals["arr"]), ("1000.00", "12000.00"))
        self.assertEqual((totals["invoiced"], totals["collected"], totals["outstanding"]),
                         ("500.00", "300.00", "200.00"))
        self.assertEqual((totals["signups_pending"], totals["conversion_percent"]), (1, 50))
        self.assertEqual(totals["clinic_revenue_this_month"], "200.00")
        self.assertEqual(len(data["months"]), 6)
        self.assertEqual(data["series"]["collected"][-1]["value"], "300.00")
        self.assertEqual(data["groups"][0]["name"], "an-basic")

    def test_months_run_oldest_first_to_this_month(self):
        keys = month_keys(3, today=date(2026, 1, 15))
        self.assertEqual(keys, [date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1)])
