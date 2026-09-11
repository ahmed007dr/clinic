"""Who may see which money (billing.access), through every door.

Before this, any member of a branch could list its payments and expenses for
any period and open the financial report: a receptionist could read the year's
takings, a doctor every colleague's patients' payments. Each test below is one
of the ways that used to be possible — the API lists, the report, the
dashboard, the patient timeline, and the older server-rendered screens.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from appointments.models import Appointment
from billing.models import CashShift, Expense, Payment
from branches.models import Branch
from patients.models import Patient
from tenants.context import tenant_context
from tenants.models import Tenant

User = get_user_model()

ROLES = ("Owner", "Admin", "Reception", "Doctor")


class FinanceVisibilityTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            self.branch = Branch.all_objects.create(tenant=self.tenant, name="Money", code="MN")
            roles = {
                name: ClinicRole.all_objects.get_or_create(tenant=self.tenant, name=name)[0]
                for name in ROLES
            }
            self.patient = Patient.all_objects.create(
                tenant=self.tenant, name="Payer", branch=self.branch
            )
            appointment = Appointment.all_objects.create(
                tenant=self.tenant, patient=self.patient, branch=self.branch,
                scheduled_date=timezone.now(), price=100,
            )
            self.today_payment = Payment.all_objects.create(
                tenant=self.tenant, appointment=appointment, patient=self.patient,
                receipt_number="TODAY", amount=100, branch=self.branch,
            )
            self.old_payment = Payment.all_objects.create(
                tenant=self.tenant, appointment=appointment, patient=self.patient,
                receipt_number="OLD", amount=900, branch=self.branch,
            )
            # `date` is auto_now_add, so it can only be moved after the fact.
            Payment.all_objects.filter(pk=self.old_payment.pk).update(
                date=timezone.now() - timedelta(days=30)
            )
            today = timezone.now().date()
            Expense.all_objects.create(
                tenant=self.tenant, branch=self.branch, amount=50, date=today
            )
            Expense.all_objects.create(
                tenant=self.tenant, branch=self.branch, amount=500,
                date=today - timedelta(days=30),
            )
        for name in ROLES:
            User.objects.create_user(
                username=f"{name.lower()}-fin", email=f"{name.lower()}-fin@t.local",
                password="pass12345", tenant=self.tenant,
                role=roles[name], branch=self.branch,
            )
        # Reception's money is whatever is in their own open shift: today's
        # payment and expense are in it, the month-old ones are not.
        with tenant_context(self.tenant):
            self.shift = CashShift.all_objects.create(
                tenant=self.tenant, branch=self.branch,
                user=User.objects.get(email="reception-fin@t.local"),
            )
            Payment.all_objects.filter(pk=self.today_payment.pk).update(shift=self.shift)
            Expense.all_objects.filter(amount=50).update(shift=self.shift)

    def login(self, role):
        self.client.logout()
        self.assertTrue(
            self.client.login(email=f"{role.lower()}-fin@t.local", password="pass12345")
        )

    def receipts(self):
        response = self.client.get(reverse("api:payment-list"))
        self.assertEqual(response.status_code, 200, response.content)
        return {row["receipt_number"] for row in response.json()["results"]}

    # ------------------------------------------------------------ API lists

    def test_payments_list_by_role(self):
        for role, expected in (
            ("Owner", {"TODAY", "OLD"}),
            ("Admin", {"TODAY", "OLD"}),
            ("Reception", {"TODAY"}),
            ("Doctor", set()),
        ):
            with self.subTest(role=role):
                self.login(role)
                self.assertEqual(self.receipts(), expected)

    def test_a_closed_shift_disappears_for_reception(self):
        with tenant_context(self.tenant):
            CashShift.all_objects.filter(pk=self.shift.pk).update(status="closed")
        self.login("Reception")
        self.assertEqual(self.receipts(), set())

    def test_reception_cannot_widen_the_list_with_a_date_range(self):
        self.login("Reception")
        start = (timezone.now() - timedelta(days=60)).date().isoformat()
        response = self.client.get(reverse("api:payment-list"), {"from": start})
        self.assertEqual(
            {row["receipt_number"] for row in response.json()["results"]}, {"TODAY"}
        )

    def test_reception_cannot_open_an_old_payment_directly(self):
        self.login("Reception")
        response = self.client.get(reverse("api:payment-detail", args=[self.old_payment.uuid]))
        self.assertEqual(response.status_code, 404)

    def test_a_doctor_cannot_record_a_payment(self):
        self.login("Doctor")
        response = self.client.post(
            reverse("api:payment-list"),
            {
                "appointment": str(self.today_payment.appointment.uuid),
                "patient": str(self.patient.uuid),
                "receipt_number": "DOC-1",
                "amount": "10.00",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_expenses_list_by_role(self):
        for role, expected in (("Admin", 2), ("Reception", 1)):
            with self.subTest(role=role):
                self.login(role)
                response = self.client.get(reverse("api:expense-list"))
                self.assertEqual(response.json()["count"], expected)

    # ----------------------------------------------------- report, dashboard

    def test_financial_report_is_management_only(self):
        for role, expected in (
            ("Owner", 200), ("Admin", 200), ("Reception", 403), ("Doctor", 403),
        ):
            with self.subTest(role=role):
                self.login(role)
                response = self.client.get(reverse("api:financialreport-list"))
                self.assertEqual(response.status_code, expected)

    def test_admin_report_totals_every_date(self):
        self.login("Admin")
        data = self.client.get(reverse("api:financialreport-list")).json()
        self.assertEqual(float(data["revenue"]), 1000.0)
        self.assertEqual(float(data["expenses"]), 550.0)

    def test_dashboard_money_by_role(self):
        self.login("Admin")
        admin = self.client.get(reverse("api:dashboard")).json()
        self.assertEqual(float(admin["revenue"]["today"]), 100.0)
        self.assertEqual(float(admin["revenue"]["month"]) >= 100.0, True)
        self.assertIn("revenue_series", admin)
        self.assertIn("expenses", admin)

        self.login("Reception")
        reception = self.client.get(reverse("api:dashboard")).json()
        self.assertEqual(float(reception["revenue"]["today"]), 100.0)
        self.assertNotIn("month", reception["revenue"])
        self.assertNotIn("revenue_series", reception)
        self.assertNotIn("expenses", reception)

        self.login("Doctor")
        doctor = self.client.get(reverse("api:dashboard")).json()
        self.assertNotIn("revenue", doctor)
        self.assertNotIn("revenue_series", doctor)

    def test_session_flags_follow_the_rule(self):
        for role, expected in (("Admin", True), ("Reception", False), ("Doctor", False)):
            with self.subTest(role=role):
                self.login(role)
                user = self.client.get(reverse("api:session")).json()["user"]
                self.assertIs(user["permissions"]["view_finance"], expected)

    # ------------------------------------------------------------- timeline

    def test_timeline_does_not_route_round_the_rule(self):
        # A doctor does not reach this patient at all — not theirs
        # (test_doctor_scoping) — so only the desk and management are counted.
        url = reverse("api:patient-timeline", args=[self.patient.uuid])
        for role, expected in (("Admin", 2), ("Reception", 1)):
            with self.subTest(role=role):
                self.login(role)
                entries = self.client.get(url).json()["entries"]
                payments = [e for e in entries if e["kind"] == "payment"]
                self.assertEqual(len(payments), expected)

    # ------------------------------------------- server-rendered screens

    def test_old_money_screens_refuse_non_admins(self):
        paths = [
            reverse("billing:payment_list"),
            reverse("billing:payment_detail", args=[self.today_payment.uuid]),
            reverse("billing:expense_list"),
            reverse("billing:financial_report"),
        ]
        for role in ("Reception", "Doctor"):
            self.login(role)
            for path in paths:
                with self.subTest(role=role, path=path):
                    # user_passes_test redirects to the login page.
                    self.assertEqual(self.client.get(path).status_code, 302)
