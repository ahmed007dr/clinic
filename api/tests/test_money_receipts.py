"""Printing a receipt when money is recorded — a payment or an expense (the
group owner's rule, 2026-09-12). Reprintable any time, for whoever may still
see that row at all (billing.access): management always, reception only while
the shift holding it is still open, a doctor never. A voided entry has no
receipt — it is not money that happened."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from appointments.models import Appointment
from billing.models import CashShift, Expense, ExpenseCategory, Payment, PaymentMethod
from billing.voiding import void
from branches.models import Branch
from patients.models import Patient
from tenants.context import tenant_context
from tenants.models import Tenant

User = get_user_model()
PASSWORD = "pass12345"
ROLES = ("Owner", "Admin", "Reception", "Doctor")


class ReceiptTestsBase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            self.branch = Branch.all_objects.create(tenant=self.tenant, name="Receipts", code="RC")
            roles = {
                name: ClinicRole.all_objects.get_or_create(tenant=self.tenant, name=name)[0]
                for name in ROLES
            }
            self.patient = Patient.all_objects.create(tenant=self.tenant, name="Nour", branch=self.branch)
            method = PaymentMethod.all_objects.create(tenant=self.tenant, name="Cash")
            appointment = Appointment.all_objects.create(
                tenant=self.tenant, patient=self.patient, branch=self.branch,
                scheduled_date=timezone.now(), price=200,
            )
            self.recent = Payment.all_objects.create(
                tenant=self.tenant, appointment=appointment, patient=self.patient, method=method,
                receipt_number="RC-1", amount=200, branch=self.branch,
            )
            self.old = Payment.all_objects.create(
                tenant=self.tenant, appointment=appointment, patient=self.patient, method=method,
                receipt_number="RC-2", amount=900, branch=self.branch,
            )
            Payment.all_objects.filter(pk=self.old.pk).update(date=timezone.now() - timedelta(days=30))
            category = ExpenseCategory.all_objects.create(tenant=self.tenant, name="Supplies")
            self.recent_expense = Expense.all_objects.create(
                tenant=self.tenant, branch=self.branch, category=category, method=method,
                amount=50, date=timezone.now().date(),
            )
            self.old_expense = Expense.all_objects.create(
                tenant=self.tenant, branch=self.branch, category=category, method=method,
                amount=500, date=timezone.now().date() - timedelta(days=30),
            )
        for name in ROLES:
            User.objects.create_user(
                username=f"{name.lower()}-rc", email=f"{name.lower()}-rc@t.local", password=PASSWORD,
                tenant=self.tenant, role=roles[name], branch=self.branch,
            )
        with tenant_context(self.tenant):
            self.shift = CashShift.all_objects.create(
                tenant=self.tenant, branch=self.branch, user=User.objects.get(email="reception-rc@t.local"),
            )
            Payment.all_objects.filter(pk=self.recent.pk).update(shift=self.shift)
            Expense.all_objects.filter(pk=self.recent_expense.pk).update(shift=self.shift)

    def login(self, role):
        self.client.logout()
        self.assertTrue(self.client.login(email=f"{role.lower()}-rc@t.local", password=PASSWORD))

    def payment_url(self, payment):
        return reverse("billing:payment_print", args=[payment.uuid])

    def expense_url(self, expense):
        return reverse("billing:expense_print", args=[expense.uuid])


class PaymentReceiptTests(ReceiptTestsBase):
    def test_admin_prints_any_payment(self):
        self.login("Admin")
        for payment in (self.recent, self.old):
            body = self.client.get(self.payment_url(payment)).content.decode()
            self.assertIn(payment.receipt_number, body)
            self.assertIn("Nour", body)
            self.assertIn("Cash", body)

    def test_reception_prints_only_their_open_shifts_payment(self):
        self.login("Reception")
        self.assertEqual(self.client.get(self.payment_url(self.recent)).status_code, 200)
        self.assertEqual(self.client.get(self.payment_url(self.old)).status_code, 404)

    def test_a_closed_shift_hides_the_receipt_from_reception(self):
        with tenant_context(self.tenant):
            CashShift.all_objects.filter(pk=self.shift.pk).update(status="closed")
        self.login("Reception")
        self.assertEqual(self.client.get(self.payment_url(self.recent)).status_code, 404)

    def test_a_doctor_sees_no_receipts_at_all(self):
        self.login("Doctor")
        self.assertEqual(self.client.get(self.payment_url(self.recent)).status_code, 404)

    def test_a_voided_payment_has_no_receipt(self):
        self.login("Admin")
        void(User.objects.get(email="admin-rc@t.local"), self.recent, "خطأ في القيد")
        self.assertEqual(self.client.get(self.payment_url(self.recent)).status_code, 404)

    def test_an_anonymous_visitor_is_redirected_to_login(self):
        self.assertEqual(self.client.get(self.payment_url(self.recent)).status_code, 302)


class ExpenseReceiptTests(ReceiptTestsBase):
    def test_admin_prints_any_expense(self):
        self.login("Admin")
        for expense in (self.recent_expense, self.old_expense):
            body = self.client.get(self.expense_url(expense)).content.decode()
            self.assertIn("Supplies", body)

    def test_reception_prints_only_their_open_shifts_expense(self):
        self.login("Reception")
        self.assertEqual(self.client.get(self.expense_url(self.recent_expense)).status_code, 200)
        self.assertEqual(self.client.get(self.expense_url(self.old_expense)).status_code, 404)

    def test_a_voided_expense_has_no_receipt(self):
        self.login("Admin")
        void(User.objects.get(email="admin-rc@t.local"), self.recent_expense, "خطأ في القيد")
        self.assertEqual(self.client.get(self.expense_url(self.recent_expense)).status_code, 404)


class ReceiptDesignTests(ReceiptTestsBase):
    """The Admin/Owner controls paper size and a footer note for money
    receipts — api/views/print_settings.py."""

    def test_paper_width_and_note_are_honoured_on_both_receipts(self):
        with tenant_context(self.tenant):
            self.branch.receipt_paper_width = "58mm"
            self.branch.receipt_note = "شكراً لزيارتكم"
            self.branch.save(update_fields=["receipt_paper_width", "receipt_note"])
        self.login("Admin")
        payment_body = self.client.get(self.payment_url(self.recent)).content.decode()
        expense_body = self.client.get(self.expense_url(self.recent_expense)).content.decode()
        for body in (payment_body, expense_body):
            self.assertIn("58mm", body)
            self.assertIn("شكراً لزيارتكم", body)
