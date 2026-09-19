"""A patient managing their own bookings (docs/15, Phase 6): details, cancel, ask to reschedule.

The clinic's rules decide what a patient may do; the server enforces them, and a
patient only ever reaches their own bookings.
"""

import uuid as uuid_module
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from appointments.models import Appointment
from billing.models import Payment, PaymentMethod
from branches.models import Branch
from tenants.context import tenant_context

from .test_booking import BookingBase

User = get_user_model()


class MyBookingBase(BookingBase):
    def make(self, status="requested", hours_ahead=72, **fields):
        """A booking of Alice's with the catalogue's doctor, `hours_ahead` from now."""
        when = timezone.now().replace(microsecond=0) + timedelta(hours=hours_ahead)
        if when.date() == self.day:
            # Keep the doctor's offered Monday free of this fixture, so the
            # times the tests ask for are never taken by chance.
            when += timedelta(days=1)
        with tenant_context(self.a):
            return Appointment.objects.create(
                tenant=self.a, patient=self.alice, branch=self.branch, doctor=self.dr_main, service=self.service,
                status=status, scheduled_date=when, price=Decimal("150"), source="portal", **fields,
            )

    def pay(self, appointment, amount="50"):
        with tenant_context(self.a):
            method = PaymentMethod.objects.get_or_create(tenant=self.a, name="Cash")[0]
            return Payment.objects.create(
                tenant=self.a, appointment=appointment, patient=self.alice, method=method,
                receipt_number=f"R-{uuid_module.uuid4().hex[:6]}", amount=Decimal(amount), branch=self.branch,
            )

    def cancel(self, appointment, client=None):
        return (client or self.client).post(self.url("appointment-cancel", uuid=appointment.uuid))

    def reschedule(self, appointment, slot, client=None, **extra):
        return (client or self.client).post(
            self.url("appointment-reschedule", uuid=appointment.uuid), {"slot": slot, **extra},
            content_type="application/json",
        )

    def reload(self, appointment):
        with tenant_context(self.a):
            return Appointment.objects.get(pk=appointment.pk)


class DetailTests(MyBookingBase):
    def test_the_patient_sees_the_booking_what_is_owed_and_what_was_paid(self):
        booking = self.make(status="waiting")
        self.pay(booking, "50")
        body = self.client.get(self.url("appointment-detail", uuid=booking.uuid)).json()
        self.assertEqual((body["price"], body["paid"], body["due"]), ("150.00", "50.00", "100.00"))
        self.assertEqual([p["amount"] for p in body["payments"]], ["50.00"])
        self.assertEqual((body["doctor_name"], body["service_name"], body["branch_name"]), ("Dr Main", "Laser", "Main"))

    def test_another_patients_booking_is_a_404_like_a_missing_one(self):
        booking = self.make()
        other = Client()
        self.enrol(self.bob, client=other)
        real = other.get(self.url("appointment-detail", uuid=booking.uuid))
        missing = other.get(self.url("appointment-detail", uuid=uuid_module.uuid4()))
        self.assertEqual((real.status_code, real.content), (missing.status_code, missing.content))
        self.assertEqual(self.cancel(booking, client=other).status_code, 404)
        self.assertEqual(self.reschedule(booking, "2999-01-01 09:00", client=other).status_code, 404)
        self.assertEqual(self.reload(booking).status, "requested")

    def test_it_needs_a_portal_sign_in(self):
        booking = self.make()
        self.assertIn(Client().get(self.url("appointment-detail", uuid=booking.uuid)).status_code, (401, 403))
        self.assertIn(self.cancel(booking, client=Client()).status_code, (401, 403))


class CancelTests(MyBookingBase):
    def test_an_unconfirmed_request_can_always_be_withdrawn(self):
        booking = self.make(status="requested", hours_ahead=1)  # even an hour before
        response = self.cancel(booking)
        self.assertEqual(response.status_code, 200, response.content)
        after = self.reload(booking)
        self.assertEqual(after.status, "cancelled")
        self.assertIn("[ألغاه المريض من البوابة]", after.notes)

    def test_a_confirmed_booking_needs_the_clinics_notice(self):
        soon = self.make(status="waiting", hours_ahead=5)
        refused = self.cancel(soon)
        self.assertEqual(refused.status_code, 400)
        self.assertIn("24", refused.json()["detail"])
        self.assertEqual(self.reload(soon).status, "waiting")
        later = self.make(status="waiting", hours_ahead=48)
        self.assertEqual(self.cancel(later).status_code, 200)

    def test_the_notice_is_the_clinics_to_set(self):
        soon = self.make(status="waiting", hours_ahead=5)
        Branch.all_objects.filter(pk=self.branch.pk).update(online_cancel_notice_hours=2)
        self.assertEqual(self.cancel(soon).status_code, 200)
        soon = self.make(status="waiting", hours_ahead=1)
        Branch.all_objects.filter(pk=self.branch.pk).update(online_cancel_notice_hours=0)
        self.assertEqual(self.cancel(soon).status_code, 200)

    def test_a_booking_that_already_took_place_or_is_past_cannot_be_cancelled(self):
        past = self.make(status="waiting", hours_ahead=-5)
        self.assertEqual(self.cancel(past).status_code, 400)

    def test_a_booking_the_patient_has_been_called_in_for_or_that_is_closed_is_the_clinics_alone(self):
        for status in ("called", "entered", "completed", "cancelled", "no_show"):
            with self.subTest(status=status):
                booking = self.make(status=status, hours_ahead=72)
                self.assertEqual(self.cancel(booking).status_code, 400)
                self.assertEqual(self.reload(booking).status, status)

    def test_money_paid_on_it_sends_the_patient_to_the_clinic(self):
        booking = self.make(status="waiting", hours_ahead=72)
        self.pay(booking)
        response = self.cancel(booking)
        self.assertEqual(response.status_code, 400)
        self.assertIn("العيادة", response.json()["detail"])
        self.assertEqual(self.reload(booking).status, "waiting")

    def test_cancelling_clears_a_pending_request_to_move_it(self):
        booking = self.make(status="requested", reschedule_requested_for=timezone.now() + timedelta(days=5),
                            reschedule_note="later please")
        self.cancel(booking)
        after = self.reload(booking)
        self.assertEqual((after.status, after.reschedule_requested_for, after.reschedule_note), ("cancelled", None, ""))

    def test_the_list_says_what_may_be_done_and_why_not(self):
        free = self.make(status="waiting", hours_ahead=72)
        soon = self.make(status="waiting", hours_ahead=3)
        paid = self.make(status="waiting", hours_ahead=96)
        self.pay(paid)
        rows = {r["uuid"]: r for r in self.client.get(self.url("appointments")).json()}
        self.assertTrue(rows[str(free.uuid)]["can_cancel"] and rows[str(free.uuid)]["can_reschedule"])
        self.assertFalse(rows[str(soon.uuid)]["can_cancel"])
        self.assertIn("ساعة", rows[str(soon.uuid)]["cancel_blocked_reason"])
        self.assertFalse(rows[str(paid.uuid)]["can_cancel"])
        self.assertTrue(rows[str(paid.uuid)]["can_reschedule"])  # money stays, the time may move


class RescheduleTests(MyBookingBase):
    def offered(self, hhmm):
        return f"{self.day.isoformat()} {hhmm}"

    def test_a_request_records_the_wish_and_moves_nothing(self):
        booking = self.make(status="waiting", hours_ahead=72)
        before = self.reload(booking).scheduled_date
        response = self.reschedule(booking, self.offered("09:45"), notes="  morning is better ")
        self.assertEqual(response.status_code, 200, response.content)
        after = self.reload(booking)
        self.assertEqual(after.scheduled_date, before)
        self.assertEqual(after.reschedule_requested_for, datetime.combine(self.day, time(9, 45)))
        self.assertEqual(after.reschedule_note, "morning is better")
        self.assertEqual(response.json()["reschedule_requested_for"][:16], f"{self.day.isoformat()}T09:45")

    def test_the_wished_time_must_be_one_the_doctor_is_offered(self):
        booking = self.make(status="waiting", hours_ahead=72)
        for slot in (self.offered("10:10"), self.offered("23:00")):
            self.assertEqual(self.reschedule(booking, slot).status_code, 409)
        self.assertIsNone(self.reload(booking).reschedule_requested_for)

    def test_bad_times_are_refused(self):
        booking = self.make(status="waiting", hours_ahead=72)
        past = (timezone.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
        for slot in ("", "soon", past):
            with self.subTest(slot=slot):
                self.assertEqual(self.reschedule(booking, slot).status_code, 400)

    def test_asking_for_the_time_it_already_has_is_refused(self):
        with tenant_context(self.a):
            booking = Appointment.objects.create(
                tenant=self.a, patient=self.alice, branch=self.branch, doctor=self.dr_main, service=self.service,
                status="waiting", scheduled_date=datetime.combine(self.day, time(9, 0)), price=1,
            )
        self.assertEqual(self.reschedule(booking, self.offered("09:00")).status_code, 400)

    def test_the_clinics_notice_and_status_rules_apply_here_too(self):
        soon = self.make(status="waiting", hours_ahead=3)
        self.assertEqual(self.reschedule(soon, self.offered("09:45")).status_code, 400)
        entered = self.make(status="entered", hours_ahead=72)
        self.assertEqual(self.reschedule(entered, self.offered("09:45")).status_code, 400)

    def test_an_older_booking_with_no_doctor_may_ask_for_any_future_time(self):
        with tenant_context(self.a):
            legacy = Appointment.objects.create(
                tenant=self.a, patient=self.alice, status="requested",
                scheduled_date=timezone.now() + timedelta(days=4),
            )
        when = (timezone.now() + timedelta(days=9)).strftime("%Y-%m-%d %H:%M")
        self.assertEqual(self.reschedule(legacy, when).status_code, 200)

    def test_asking_again_replaces_the_earlier_wish(self):
        booking = self.make(status="waiting", hours_ahead=72)
        self.reschedule(booking, self.offered("09:45"))
        self.reschedule(booking, self.offered("11:15"))
        self.assertEqual(self.reload(booking).reschedule_requested_for, datetime.combine(self.day, time(11, 15)))


class StaffSideTests(MyBookingBase):
    def setUp(self):
        super().setUp()
        with tenant_context(self.a):
            role = ClinicRole.all_objects.get_or_create(tenant=self.a, name="Reception")[0]
        for name, branch in (("rec", self.branch), ("rec-second", self.second)):
            User.objects.create_user(username=name, email=f"{name}@t.local", password="pass12345",
                                     tenant=self.a, role=role, branch=branch)
        self.staff = Client()
        self.staff.login(email="rec@t.local", password="pass12345")
        self.booking = self.make(status="waiting", hours_ahead=72)
        self.reschedule(self.booking, f"{self.day.isoformat()} 09:45", notes="prefers mornings")

    def row(self):
        rows = self.staff.get(reverse("api:appointment-list")).json()["results"]
        return next(r for r in rows if r["uuid"] == str(self.booking.uuid))

    def test_reception_sees_the_request_beside_the_booking(self):
        row = self.row()
        self.assertEqual(row["reschedule_note"], "prefers mornings")
        self.assertTrue(row["reschedule_requested_for"].startswith(f"{self.day.isoformat()}T09:45"))

    def test_moving_the_booking_settles_the_request(self):
        new_time = (timezone.now() + timedelta(days=6)).strftime("%Y-%m-%d %H:%M")
        response = self.staff.patch(reverse("api:appointment-detail", args=[self.booking.uuid]),
                                    {"scheduled_date": new_time}, content_type="application/json")
        self.assertEqual(response.status_code, 200, response.content)
        after = self.reload(self.booking)
        self.assertEqual((after.reschedule_requested_for, after.reschedule_note), (None, ""))

    def test_an_edit_that_leaves_the_time_alone_keeps_the_request(self):
        response = self.staff.patch(reverse("api:appointment-detail", args=[self.booking.uuid]),
                                    {"notes": "called, no answer"}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(self.reload(self.booking).reschedule_requested_for)

    def test_reception_can_dismiss_it_without_moving_the_booking(self):
        before = self.reload(self.booking).scheduled_date
        response = self.staff.post(reverse("api:appointment-dismiss-reschedule", args=[self.booking.uuid]))
        self.assertEqual(response.status_code, 200, response.content)
        after = self.reload(self.booking)
        self.assertEqual((after.scheduled_date, after.reschedule_requested_for), (before, None))

    def test_the_request_is_not_the_staffs_to_forge_and_another_clinics_desk_cannot_touch_it(self):
        forged = self.staff.patch(reverse("api:appointment-detail", args=[self.booking.uuid]),
                                  {"reschedule_requested_for": "2999-01-01T09:00"}, content_type="application/json")
        self.assertEqual(forged.status_code, 200)
        self.assertNotEqual(self.reload(self.booking).reschedule_requested_for, datetime(2999, 1, 1, 9, 0))
        other = Client()
        other.login(email="rec-second@t.local", password="pass12345")
        self.assertEqual(other.post(reverse("api:appointment-dismiss-reschedule", args=[self.booking.uuid])).status_code, 404)

    def test_a_patient_cancelling_shows_as_cancelled_to_the_desk(self):
        self.cancel(self.booking)
        self.assertEqual(self.row()["status"], "cancelled")


class ManagerFlowTests(MyBookingBase):
    """Phase 7: website bookings arrive in the clinic's own screens — counted on the
    dashboard, filterable by source, confirmed or declined by the desk — with no
    separate booking admin."""

    def setUp(self):
        super().setUp()
        with tenant_context(self.a):
            role = ClinicRole.all_objects.get_or_create(tenant=self.a, name="Reception")[0]
        for name, branch in (("rec", self.branch), ("rec-second", self.second)):
            User.objects.create_user(username=name, email=f"{name}@t.local", password="pass12345",
                                     tenant=self.a, role=role, branch=branch)
        self.staff = Client()
        self.staff.login(email="rec@t.local", password="pass12345")

    def counts(self, client=None):
        return (client or self.staff).get(reverse("api:dashboard")).json()["appointments"]["online_requests"]

    def test_the_dashboard_counts_website_requests_waiting_for_the_desk(self):
        self.assertEqual(self.counts(), 0)
        self.book()
        self.book(slot=self.slot("09:45"))
        # A request made at the desk, and a confirmed website booking, are not "waiting for us".
        with tenant_context(self.a):
            Appointment.objects.create(tenant=self.a, patient=self.bob, branch=self.branch, status="requested",
                                       scheduled_date=timezone.now() + timedelta(days=2), source="reception")
        self.make(status="waiting")
        self.assertEqual(self.counts(), 2)

    def test_each_clinic_counts_only_its_own_requests(self):
        self.book()
        other = Client()
        other.login(email="rec-second@t.local", password="pass12345")
        self.assertEqual(self.counts(other), 0)

    def test_the_desk_confirms_a_request_and_it_leaves_the_count(self):
        self.book()
        (row,) = self.staff.get(reverse("api:appointment-list"), {"status": "requested", "source": "portal"}).json()["results"]
        confirmed = self.staff.post(reverse("api:appointment-set-status", args=[row["uuid"]]), {"status": "waiting"},
                                    content_type="application/json")
        self.assertEqual(confirmed.status_code, 200, confirmed.content)
        self.assertEqual((confirmed.json()["status"], confirmed.json()["source"]), ("waiting", "portal"))
        self.assertEqual(self.counts(), 0)

    def test_the_desk_can_decline_a_request(self):
        self.book()
        (row,) = self.staff.get(reverse("api:appointment-list"), {"status": "requested"}).json()["results"]
        declined = self.staff.post(reverse("api:appointment-set-status", args=[row["uuid"]]), {"status": "cancelled"},
                                   content_type="application/json")
        self.assertEqual(declined.status_code, 200)
        self.assertEqual(self.counts(), 0)
        # The patient sees it as cancelled.
        self.assertEqual([r["status"] for r in self.client.get(self.url("appointments")).json()], ["cancelled"])

    def test_the_desk_can_give_a_request_the_doctor_and_time_settled_by_phone(self):
        self.book()
        (row,) = self.staff.get(reverse("api:appointment-list"), {"source": "portal"}).json()["results"]
        moved = (timezone.now() + timedelta(days=5)).strftime("%Y-%m-%d %H:%M")
        response = self.staff.patch(reverse("api:appointment-detail", args=[row["uuid"]]),
                                    {"scheduled_date": moved, "status": "waiting"}, content_type="application/json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["source"], "portal")  # still known as a website booking


class PaymentLineTests(MyBookingBase):
    """Phase 8: payment is its own thing beside the booking — the patient sees
    what it costs, what was paid and that the rest is paid at the clinic."""

    def row(self, booking):
        rows = {r["uuid"]: r for r in self.client.get(self.url("appointments")).json()}
        return rows[str(booking.uuid)]

    def test_an_unpaid_booking_is_paid_at_the_clinic_by_default(self):
        row = self.row(self.make(status="waiting"))
        self.assertEqual((row["payment_status"], row["pay_at_clinic"], row["price"], row["paid"]),
                         ("unpaid", True, "150.00", "0.00"))
        self.assertFalse(row["can_pay_online"])  # this clinic has no gateway

    def test_part_paid_then_paid_in_full(self):
        booking = self.make(status="waiting")
        self.pay(booking, "50")
        self.assertEqual(self.row(booking)["payment_status"], "partial")
        self.pay(booking, "100")
        row = self.row(booking)
        self.assertEqual((row["payment_status"], row["pay_at_clinic"], row["due"]), ("paid", False, "0.00"))

    def test_a_request_shows_what_it_will_cost_and_no_amount_due_yet(self):
        row = self.row(self.make(status="requested"))
        self.assertEqual((row["payment_status"], row["price"], row["due"]), ("unpaid", "150.00", "0"))

    def test_a_free_booking_or_a_cancelled_one_owes_nothing_at_the_clinic(self):
        with tenant_context(self.a):
            free = Appointment.objects.create(
                tenant=self.a, patient=self.alice, status="waiting", price=0,
                scheduled_date=timezone.now() + timedelta(days=3),
            )
        self.assertEqual((self.row(free)["payment_status"], self.row(free)["pay_at_clinic"]), ("free", False))
        cancelled = self.make(status="cancelled")
        self.assertFalse(self.row(cancelled)["pay_at_clinic"])

    def test_a_payment_of_another_patient_never_shows(self):
        booking = self.make(status="waiting")
        with tenant_context(self.a):
            other = Appointment.objects.create(
                tenant=self.a, patient=self.bob, status="waiting", price=100,
                scheduled_date=timezone.now() + timedelta(days=3),
            )
            method = PaymentMethod.objects.get_or_create(tenant=self.a, name="Cash")[0]
            Payment.objects.create(tenant=self.a, appointment=other, patient=self.bob, method=method,
                                   receipt_number="R-BOB-1", amount=Decimal("100"), branch=self.branch)
        self.assertEqual(self.row(booking)["paid"], "0.00")
        self.assertEqual(self.client.get(self.url("payments")).json(), [])
