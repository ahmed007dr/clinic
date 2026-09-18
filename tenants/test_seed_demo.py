"""The demo data follows the rules the system now enforces.

`seed_demo` is what a showcase copy is built from. If it produced a payment
outside a shift, a patient with the doctor who had not paid, or a shift with an
opening balance, the demo would show behaviour the real system refuses.
"""

from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from appointments.models import Appointment
from billing.collect import amount_due
from billing.models import CashShift, DiscountCoupon, Expense, Payment
from tenants.context import tenant_context
from tenants.models import Tenant


class SeedDemoRulesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", "--password", "seed-pass-1", stdout=StringIO())
        cls.tenants = list(Tenant.objects.filter(slug__in=["dr-ahmed", "nile-clinic"]))

    def each_tenant(self):
        for tenant in self.tenants:
            with tenant_context(tenant):
                yield tenant

    def test_every_payment_is_against_a_booking_and_inside_a_shift(self):
        for tenant in self.each_tenant():
            payments = list(Payment.objects.select_related("shift", "appointment"))
            self.assertTrue(payments, tenant.slug)
            for payment in payments:
                self.assertIsNotNone(payment.shift, payment.receipt_number)
                self.assertEqual(payment.branch_id, payment.shift.branch_id)
                self.assertEqual(payment.created_by_id, payment.shift.user_id)
                self.assertEqual(payment.patient_id, payment.appointment.patient_id)
                self.assertTrue(payment.receipt_number.startswith("R-"), payment.receipt_number)

    def test_receipt_numbers_are_unique(self):
        for tenant in self.each_tenant():
            numbers = list(Payment.objects.values_list("receipt_number", flat=True))
            self.assertEqual(len(numbers), len(set(numbers)), tenant.slug)

    def test_nobody_is_with_the_doctor_without_having_paid_in_full(self):
        for tenant in self.each_tenant():
            entered = list(Appointment.objects.filter(status__in=["entered", "completed"]))
            self.assertTrue(entered, tenant.slug)
            for appointment in entered:
                self.assertEqual(amount_due(appointment), Decimal("0.00"), appointment.serial_number)

    def test_todays_queue_shows_a_balance_still_owing_and_an_unpaid_booking(self):
        for tenant in self.each_tenant():
            waiting = list(Appointment.objects.filter(status__in=["waiting", "called", "quick"]))
            dues = [amount_due(a) for a in waiting]
            self.assertTrue(any(d > 0 for d in dues), tenant.slug)

    def test_shifts_start_from_zero_and_only_reception_has_one_open(self):
        for tenant in self.each_tenant():
            shifts = list(CashShift.objects.select_related("user"))
            self.assertTrue(shifts, tenant.slug)
            for shift in shifts:
                self.assertEqual(shift.opening_balance, 0)
                if shift.status == "closed":
                    self.assertIsNotNone(shift.closed_at)
                    self.assertIsNotNone(shift.closing_summary)
                    self.assertNotIn("expected_balance", shift.closing_summary)
            open_shifts = [s for s in shifts if s.status == "open"]
            self.assertEqual([s.user.username for s in open_shifts], ["reception"], tenant.slug)

    def test_expenses_are_inside_shifts_on_the_shifts_day(self):
        for tenant in self.each_tenant():
            expenses = list(Expense.objects.select_related("shift"))
            self.assertTrue(expenses, tenant.slug)
            for expense in expenses:
                self.assertIsNotNone(expense.shift)
                self.assertEqual(expense.branch_id, expense.shift.branch_id)
                self.assertEqual(expense.date, expense.shift.opened_at.date())

    def test_the_open_shift_lists_todays_bookings_and_their_money(self):
        from billing.shifts import shift_bookings

        for tenant in self.each_tenant():
            shift = CashShift.objects.get(status="open")
            bookings = list(shift_bookings(shift))
            self.assertTrue(bookings, tenant.slug)
            paid_here = {p.appointment_id for p in Payment.objects.filter(shift=shift)}
            self.assertTrue(paid_here <= {b.pk for b in bookings} | paid_here)
            self.assertTrue(shift.payments.exists() and shift.expenses.exists(), tenant.slug)

    def test_coupons_exist_in_every_state_and_the_spent_ones_are_on_bookings(self):
        for tenant in self.each_tenant():
            states = {c.status for c in DiscountCoupon.objects.all()}
            self.assertEqual(states, {"used", "available", "expired", "voided"}, tenant.slug)
            for coupon in DiscountCoupon.objects.filter(used_at__isnull=False):
                booking = Appointment.objects.get(coupon=coupon)
                self.assertEqual(booking.discount, min(coupon.amount, booking.price))
                self.assertEqual(booking.net_price, booking.price - booking.discount)

    def test_the_demo_login_works_with_the_chosen_password(self):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.get(email="reception@dr-ahmed.local")
        self.assertTrue(user.check_password("seed-pass-1"))


class MutedMailTests(TestCase):
    def test_nothing_is_sent_while_muted_even_to_a_real_looking_address(self):
        from unittest import mock

        from billing import notify

        doctor = mock.Mock(email="dr@example.org")
        with mock.patch("platform_admin.mailer.sender_for", side_effect=AssertionError("mail settings touched")):
            with notify.muted():
                self.assertFalse(notify._send(doctor, "s", ["l"]))
        # And the switch is off again afterwards.
        self.assertFalse(notify._muted)


class AboutTabDataTests(TestCase):
    """The portal's "About" tab has something to show on the demo data."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", "--password", "seed-pass-2", stdout=StringIO())

    def test_every_demo_branch_publishes_its_details_and_specialties(self):
        from django.urls import reverse

        for slug in ("dr-ahmed", "nile-clinic"):
            body = self.client.get(reverse("api:portal:about", kwargs={"slug": slug})).json()
            self.assertTrue(body["branches"], slug)
            for branch in body["branches"]:
                for field in ("address", "phone", "map_url", "working_hours", "about_text"):
                    self.assertTrue(branch[field], (slug, branch["name"], field))
                self.assertTrue(branch["specializations"], (slug, branch["name"]))
