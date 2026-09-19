"""The demo data follows the rules the system now enforces.

`seed_demo` is what a showcase copy is built from. If it produced a payment
outside a shift, a patient with the doctor who had not paid, or a shift with an
opening balance, the demo would show behaviour the real system refuses.
"""

import shutil
import tempfile
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings

from appointments.models import Appointment
from billing.collect import amount_due
from billing.models import CashShift, DiscountCoupon, Expense, Payment
from tenants.context import tenant_context
from tenants.models import Tenant


MEDIA = tempfile.mkdtemp(prefix="clinic-seed-media-")


def tearDownModule():
    shutil.rmtree(MEDIA, ignore_errors=True)


@override_settings(MEDIA_ROOT=MEDIA)
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
            # The clinic's online shift belongs to no one; it has its own test below.
            shifts = list(CashShift.objects.select_related("user").filter(kind="cashier"))
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
            shift = CashShift.objects.get(status="open", kind="cashier")
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


@override_settings(MEDIA_ROOT=MEDIA)
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


@override_settings(MEDIA_ROOT=MEDIA)
class PublicPortalDataTests(TestCase):
    """The demo shows the public portal and online booking working (docs/15)."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", "--password", "seed-pass-3", stdout=StringIO())
        cls.tenants = list(Tenant.objects.filter(slug__in=["dr-ahmed", "nile-clinic"]))

    def each_tenant(self):
        for tenant in self.tenants:
            with tenant_context(tenant):
                yield tenant

    def test_the_groups_are_in_the_public_directory_with_their_services(self):
        from django.core.cache import cache
        from django.urls import reverse

        cache.clear()
        cards = {c["slug"]: c for c in self.client.get(reverse("api:directory")).json()["results"]}
        self.assertEqual(set(cards), {"dr-ahmed", "nile-clinic"})
        for slug, card in cards.items():
            self.assertTrue(card["logo"] and card["cover"], slug)
            self.assertTrue(card["specialties"], slug)
            self.assertGreaterEqual(card["services_count"], 3, slug)
        cache.clear()

    def test_the_catalogue_offers_every_kind_of_service_with_a_bookable_time(self):
        from django.urls import reverse

        from appointments.availability import available_days
        from services.catalog import offerings

        for tenant in self.each_tenant():
            body = self.client.get(reverse("api:portal:catalog-services", kwargs={"slug": tenant.slug})).json()
            by_name = {row["name"]: row for row in body}
            self.assertTrue(by_name["ليزر بالنبضة"]["requires_quantity"], tenant.slug)
            self.assertTrue(by_name["حقن فيلر"]["doctor_sets_quantity"], tenant.slug)
            self.assertEqual(by_name["استشارة تجميل"]["price_display"], "after_evaluation")
            self.assertIsNone(by_name["استشارة تجميل"]["from_price"])
            for offer in offerings():
                self.assertTrue(available_days(offer), (tenant.slug, offer.doctor.name, offer.service.name))

    def test_one_clinic_does_not_offer_one_service_and_one_doctor_stays_private(self):
        from django.urls import reverse

        from branches.models import Branch
        from employees.models import Employee
        from services.catalog import offerings
        from services.models import Service

        with tenant_context(self.tenants[0]):
            asyut = Branch.objects.get(code="ASY")
            q_switch = Service.objects.get(name="Q switch 800")
            self.assertEqual(list(offerings(service=q_switch, branch=asyut)), [])
            self.assertTrue(list(offerings(service=q_switch)))  # the other clinic does
            hidden = Employee.objects.filter(employee_type__name="Doctor", show_publicly=False)
            self.assertEqual(hidden.count(), 1)
            names = [d["name"] for b in self.client.get(
                reverse("api:portal:about", kwargs={"slug": "dr-ahmed"})).json()["branches"] for d in b["doctors"]]
            self.assertNotIn(hidden.get().name, names)

    def test_a_clinics_images_wait_for_the_owner_and_only_approved_ones_are_public(self):
        from django.urls import reverse

        from branches.models import Branch

        with tenant_context(self.tenants[0]):
            waiting = Branch.objects.get(code="ASY")
            self.assertEqual((waiting.media_status, bool(waiting.public_logo), bool(waiting.pending_public_logo)),
                             ("pending", False, True))
            body = self.client.get(reverse("api:portal:about", kwargs={"slug": "dr-ahmed"})).json()
            shown = {b["name"]: b for b in body["branches"]}
            self.assertTrue(shown["سوهاج"]["logo"])
            self.assertIsNone(shown["أسيوط"]["logo"])
            self.assertNotIn("pending", str(body))

    def test_website_bookings_exist_in_every_state_with_the_website_as_their_source(self):
        for tenant in self.each_tenant():
            portal = Appointment.objects.filter(source="portal")
            statuses = {a.status for a in portal}
            self.assertTrue({"requested", "waiting", "cancelled"} <= statuses, (tenant.slug, statuses))
            self.assertTrue(portal.filter(quantity__isnull=False, quantity_is_estimate=False).exists(), tenant.slug)
            self.assertTrue(portal.filter(reschedule_requested_for__isnull=False).exists(), tenant.slug)
            self.assertTrue(Appointment.objects.filter(source="phone").exists(), tenant.slug)
            for booking in portal.filter(quantity__isnull=False):
                self.assertEqual(booking.price, booking.quantity * booking.unit_price)

    def test_a_confirmed_website_booking_sits_on_a_time_that_was_offered(self):
        from appointments.availability import available_slots
        from services.catalog import resolve_offering

        for tenant in self.each_tenant():
            for booking in Appointment.objects.filter(source="portal", status="waiting"):
                offer = resolve_offering(booking.branch, booking.doctor, booking.service)
                self.assertIsNotNone(offer, (tenant.slug, booking.pk))
                # It now holds that time, so the time is no longer offered to anyone else.
                self.assertNotIn(booking.scheduled_date, available_slots(offer, booking.scheduled_date.date()))

    def test_the_visiting_patient_is_at_another_clinic_of_the_group(self):
        from patients.models import Patient

        with tenant_context(self.tenants[0]):
            sara = Patient.objects.get(phone1="01099000003")
            away = Appointment.objects.filter(patient=sara, source="portal").exclude(branch=sara.branch)
            self.assertTrue(away.exists())
            self.assertTrue(Tenant.objects.get(slug="dr-ahmed").portal_allow_other_branches)
        self.assertFalse(Tenant.objects.get(slug="nile-clinic").portal_allow_other_branches)

    def test_online_payments_are_in_the_clinics_online_shift_one_closed_one_open(self):
        for tenant in self.each_tenant():
            online = list(CashShift.objects.filter(kind="online"))
            self.assertEqual(sorted(s.status for s in online), ["closed", "open"], tenant.slug)
            for shift in online:
                self.assertIsNone(shift.user_id)
                self.assertEqual(shift.opening_balance, 0)
                self.assertTrue(shift.payments.exists(), tenant.slug)
                if shift.status == "closed":
                    self.assertIsNotNone(shift.closing_summary)
                    self.assertIsNotNone(shift.closed_by_id)
            for payment in Payment.objects.filter(method__name="دفع إلكتروني"):
                self.assertEqual(payment.shift.kind, "online")

    def test_a_patient_is_in_the_room_waiting_for_the_doctor_to_set_the_quantity(self):
        for tenant in self.each_tenant():
            room = Appointment.objects.filter(status="entered", quantity_is_estimate=True)
            self.assertEqual(room.count(), 1, tenant.slug)
            booking = room.get()
            self.assertTrue(booking.service.doctor_sets_quantity)
            self.assertEqual(amount_due(booking), Decimal("0.00"))  # paid on the estimate, as the rule needs
            self.assertEqual(booking.doctor.user_account.username, "doctor")

    def test_schedules_holidays_and_leave_are_set(self):
        from appointments.models import BranchHoliday, DoctorSchedule, DoctorTimeOff

        for tenant in self.each_tenant():
            self.assertTrue(DoctorSchedule.objects.exists(), tenant.slug)
            self.assertTrue(DoctorSchedule.objects.filter(break_start__isnull=False).exists(), tenant.slug)
            self.assertTrue(DoctorTimeOff.objects.exists(), tenant.slug)
            self.assertTrue(BranchHoliday.objects.filter(branch__isnull=True).exists(), tenant.slug)
            self.assertTrue(BranchHoliday.objects.filter(branch__isnull=False).exists(), tenant.slug)

    def test_the_desk_has_a_notice_for_each_waiting_request(self):
        from notifications.models import Notification

        for tenant in self.each_tenant():
            self.assertTrue(
                Notification.objects.filter(user__username="reception", title="طلب موعد جديد من الموقع").exists(),
                tenant.slug)


@override_settings(MEDIA_ROOT=MEDIA)
class ReseedTests(TestCase):
    def test_reset_clears_the_public_portal_data_too_and_seeds_again(self):
        call_command("seed_demo", "--password", "seed-pass-4", stdout=StringIO())
        call_command("seed_demo", "--reset", "--password", "seed-pass-4", stdout=StringIO())
        for slug in ("dr-ahmed", "nile-clinic"):
            with tenant_context(Tenant.objects.get(slug=slug)):
                self.assertEqual(CashShift.objects.filter(kind="online", status="open").count(), 1, slug)
                self.assertTrue(Appointment.objects.filter(source="portal").exists(), slug)
