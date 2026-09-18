"""Cash shifts, end to end (billing.shifts, api/views/shifts.py).

The rules under test are the group owner's: money is recorded only inside
one's own open shift; the closing report is per payment method; a closed shift
vanishes for the person who ran it; only management reviews and reopens.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from appointments.models import Appointment
from billing.models import CashShift, Expense, Payment, PaymentMethod
from branches.models import Branch
from patients.models import Patient
from tenants.context import tenant_context
from tenants.models import Tenant

User = get_user_model()


class ShiftTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            self.branch = Branch.all_objects.create(tenant=self.tenant, name="Desk", code="DS")
            self.other = Branch.all_objects.create(tenant=self.tenant, name="Other", code="OT")
            roles = {
                name: ClinicRole.all_objects.get_or_create(tenant=self.tenant, name=name)[0]
                for name in ("Owner", "Admin", "Reception", "Doctor")
            }
            self.cash = PaymentMethod.all_objects.create(tenant=self.tenant, name="Cash-S")
            self.card = PaymentMethod.all_objects.create(tenant=self.tenant, name="Card-S")
            self.patient = Patient.all_objects.create(tenant=self.tenant, name="P", branch=self.branch)
            self.appointment = Appointment.all_objects.create(
                tenant=self.tenant, patient=self.patient, branch=self.branch,
                scheduled_date=timezone.now(), price=300,
            )
        self.users = {}
        for key, role, branch in (
            ("owner", "Owner", self.branch), ("admin", "Admin", self.branch),
            ("desk", "Reception", self.branch), ("desk2", "Reception", self.branch),
            ("far", "Admin", self.other), ("doc", "Doctor", self.branch),
        ):
            self.users[key] = User.objects.create_user(
                username=key, email=f"{key}@sh.local", password="pass12345",
                tenant=self.tenant, role=roles[role], branch=branch,
            )
        self.receipt = 0

    def login(self, key):
        self.client.logout()
        self.assertTrue(self.client.login(email=f"{key}@sh.local", password="pass12345"))

    def post(self, name, data=None, args=None):
        return self.client.post(reverse(name, args=args), data or {}, content_type="application/json")

    def open(self, balance="100"):
        return self.post("api:shift-open", {"opening_balance": balance})

    def pay(self, amount, method):
        self.receipt += 1
        return self.post("api:payment-list", {
            "appointment": str(self.appointment.uuid), "patient": str(self.patient.uuid),
            "receipt_number": f"SH-{self.receipt}", "amount": amount, "method": str(method.uuid),
        })

    def spend(self, amount, method):
        return self.post("api:expense-list", {"amount": amount, "method": str(method.uuid)})

    # ------------------------------------------------------------ recording

    def test_no_money_without_an_open_shift(self):
        self.login("desk")
        response = self.pay("50.00", self.cash)
        self.assertEqual(response.status_code, 400)
        self.assertIn("وردية", response.json()["detail"])
        self.assertEqual(self.spend("10.00", self.cash).status_code, 400)

    def test_money_is_filed_under_the_recorders_shift(self):
        self.login("desk")
        shift_uuid = self.open().json()["uuid"]
        self.assertEqual(self.pay("50.00", self.cash).status_code, 201)
        expense = self.spend("10.00", self.cash)
        self.assertEqual(expense.status_code, 201, expense.content)
        # Date and clinic come from the shift, not the form.
        self.assertEqual(expense.json()["date"], timezone.now().date().isoformat())
        self.assertEqual(expense.json()["branch"], str(self.branch.uuid))
        with tenant_context(self.tenant):
            shift = CashShift.all_objects.get(uuid=shift_uuid)
            self.assertEqual(Payment.all_objects.get(shift=shift).created_by, self.users["desk"])
            self.assertEqual(Expense.all_objects.filter(shift=shift).count(), 1)

    def test_one_open_shift_per_person(self):
        self.login("desk")
        self.assertEqual(self.open().status_code, 201)
        self.assertEqual(self.open().status_code, 400)

    def test_the_owner_needs_a_shift_too_and_doctors_have_none(self):
        # The group owner's rule (2026-09-18): nobody records money outside a
        # shift — the Owner used to, and that was the unreconcilable drawer.
        self.login("owner")
        refused = self.pay("20.00", self.cash)
        self.assertEqual(refused.status_code, 400)
        self.assertIn("وردية", refused.json()["detail"])
        self.assertEqual(self.spend("5.00", self.cash).status_code, 400)
        self.assertEqual(self.open().status_code, 201)
        self.assertEqual(self.pay("20.00", self.cash).status_code, 201)
        self.assertEqual(self.spend("5.00", self.cash).status_code, 201)
        self.login("doc")
        self.assertEqual(self.open().status_code, 400)
        self.assertFalse(self.client.get(reverse("api:shift-current")).json()["works_in_shifts"])

    def test_the_owner_chooses_the_clinic_a_shift_is_at_others_cannot(self):
        self.login("owner")
        opened = self.post("api:shift-open", {"opening_balance": "0", "branch": str(self.other.uuid)})
        self.assertEqual(opened.status_code, 201, opened.content)
        self.assertEqual(opened.json()["branch_name"], "Other")
        # The payment lands in that clinic's drawer.
        self.pay("40.00", self.cash)
        with tenant_context(self.tenant):
            self.assertEqual(Payment.all_objects.get(receipt_number=f"SH-{self.receipt}").branch, self.other)
        # A receptionist naming another clinic is ignored: theirs is theirs.
        self.login("desk")
        own = self.post("api:shift-open", {"opening_balance": "0", "branch": str(self.other.uuid)})
        self.assertEqual(own.json()["branch_name"], "Desk")

    def test_every_payment_and_expense_says_whose_shift_it_is_in(self):
        self.login("desk")
        self.open()
        self.pay("50.00", self.cash)
        self.spend("10.00", self.cash)
        payment = self.client.get(reverse("api:payment-list")).json()["results"][0]
        expense = self.client.get(reverse("api:expense-list")).json()["results"][0]
        for row in (payment, expense):
            self.assertEqual(row["shift_user_name"], "desk")
            self.assertEqual(row["shift_status"], "open")
            self.assertTrue(row["shift_opened_at"])
            self.assertIsNone(row["shift_closed_at"])

    # ------------------------------------------------------- printing

    def test_the_shift_report_prints_for_its_cashier_admin_and_owner_only(self):
        self.login("desk")
        uuid = self.open().json()["uuid"]
        self.pay("50.00", self.cash)
        self.spend("10.00", self.cash)
        url = reverse("billing:shift_print", args=[uuid])
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        for text in ("تقرير وردية", "SH-", "50.00", "10.00"):
            self.assertContains(page, text)
        # A colleague cannot print someone else's shift.
        self.login("desk2")
        self.assertEqual(self.client.get(url).status_code, 404)
        # Management can, and so can the Owner.
        for key in ("admin", "owner"):
            self.login(key)
            self.assertEqual(self.client.get(url).status_code, 200, key)
        # An Admin of another clinic cannot.
        self.login("far")
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_a_cashier_can_print_only_in_the_handover_window_after_closing(self):
        from datetime import timedelta

        self.login("desk")
        uuid = self.open().json()["uuid"]
        self.post("api:shift-close", args=[uuid])
        url = reverse("billing:shift_print", args=[uuid])
        self.assertEqual(self.client.get(url).status_code, 200)
        with tenant_context(self.tenant):
            CashShift.all_objects.filter(uuid=uuid).update(closed_at=timezone.now() - timedelta(hours=2))
        self.assertEqual(self.client.get(url).status_code, 404)
        self.login("admin")
        self.assertEqual(self.client.get(url).status_code, 200)

    # ------------------------------------------------------------- summary

    def test_the_closing_report_is_per_payment_method(self):
        self.login("desk")
        uuid = self.open("100").json()["uuid"]
        self.pay("200.00", self.cash)
        self.pay("80.00", self.card)
        self.spend("30.00", self.cash)
        closed = self.post("api:shift-close", args=[uuid])
        self.assertEqual(closed.status_code, 200, closed.content)
        summary = closed.json()["closing_summary"]
        rows = {row["method"]: row for row in summary["by_method"]}
        self.assertEqual(rows["Cash-S"]["revenue"], "200.00")
        self.assertEqual(rows["Cash-S"]["expenses"], "30.00")
        self.assertEqual(rows["Cash-S"]["net"], "170.00")
        self.assertEqual(rows["Card-S"]["net"], "80.00")
        self.assertEqual(summary["net"], "250.00")
        # A shift starts from zero: no opening balance, no "expected" balance.
        self.assertNotIn("expected_balance", summary)
        self.assertNotIn("opening_balance", summary)

    # ------------------------------------------------------- after closing

    def test_a_closed_shift_vanishes_for_its_cashier(self):
        self.login("desk")
        uuid = self.open().json()["uuid"]
        self.pay("50.00", self.cash)
        self.assertEqual(len(self.client.get(reverse("api:payment-list")).json()["results"]), 1)
        self.post("api:shift-close", args=[uuid])
        self.assertEqual(self.client.get(reverse("api:payment-list")).json()["results"], [])
        self.assertIsNone(self.client.get(reverse("api:shift-current")).json()["shift"])
        self.assertEqual(self.client.get(reverse("api:shift-detail", args=[uuid])).status_code, 404)
        self.assertEqual(self.client.get(reverse("api:shift-list")).json()["results"], [])

    def test_reception_cannot_reopen_or_touch_a_colleagues_shift(self):
        self.login("desk2")
        other = self.open().json()["uuid"]
        self.login("desk")
        self.assertEqual(self.post("api:shift-close", args=[other]).status_code, 404)
        mine = self.open().json()["uuid"]
        self.post("api:shift-close", args=[mine])
        self.assertEqual(self.post("api:shift-reopen", args=[mine]).status_code, 404)

    def test_management_reviews_closes_and_reopens(self):
        self.login("desk")
        uuid = self.open().json()["uuid"]
        self.pay("50.00", self.cash)

        self.login("admin")
        listed = self.client.get(reverse("api:shift-list")).json()["results"]
        self.assertEqual([row["uuid"] for row in listed], [uuid])
        detail = self.client.get(reverse("api:shift-detail", args=[uuid])).json()
        self.assertEqual(len(detail["payments"]), 1)
        self.assertEqual(self.post("api:shift-close", args=[uuid]).json()["status"], "closed")
        reopened = self.post("api:shift-reopen", args=[uuid])
        self.assertEqual(reopened.status_code, 200)
        self.assertEqual(reopened.json()["status"], "open")

        # Reopened means the cashier sees it again.
        self.login("desk")
        self.assertEqual(self.client.get(reverse("api:shift-current")).json()["shift"]["uuid"], uuid)

    def test_reopening_is_refused_while_the_cashier_has_another_open(self):
        self.login("desk")
        first = self.open().json()["uuid"]
        self.post("api:shift-close", args=[first])
        self.open()
        self.login("admin")
        self.assertEqual(self.post("api:shift-reopen", args=[first]).status_code, 400)

    def test_an_admin_sees_only_their_clinics_shifts(self):
        self.login("desk")
        self.open()
        self.login("far")
        self.assertEqual(self.client.get(reverse("api:shift-list")).json()["results"], [])
        self.login("owner")
        self.assertEqual(len(self.client.get(reverse("api:shift-list")).json()["results"]), 1)
