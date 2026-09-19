"""The doctor sets the real quantity inside the clinic (the group owner's request, 2026-09-19).

For a service sold by quantity that the Owner or an Admin marked "the doctor sets
the quantity", a booking carries an estimate and the doctor fixes the real
quantity while the patient is in the room. That fixes what the service comes to
(unit price × quantity), the front desk is told what is left to collect, and the
doctor never sees a price.
"""

from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from api.tests.test_quantity import QuantityBase
from appointments.models import Appointment
from billing.models import DiscountCoupon, DoctorServiceRate, Payment
from employees.models import Employee
from medical.models import Visit
from notifications.models import Notification
from services.models import Service


class DoctorQuantityBase(QuantityBase):
    def setUp(self):
        super().setUp()
        Service.all_objects.filter(pk=self.pulses.pk).update(doctor_sets_quantity=True)
        self.pulses.refresh_from_db()

    def booking(self, status="entered", quantity=None, **fields):
        """A booking made by the desk for Dr Ahmed, today, in the given state."""
        response = self.book(quantity=quantity, **fields)
        self.assertEqual(response.status_code, 201, response.content)
        appointment = Appointment.all_objects.get(uuid=response.json()["uuid"])
        Appointment.all_objects.filter(pk=appointment.pk).update(
            status=status, scheduled_date=timezone.now() + timedelta(minutes=5))
        return Appointment.all_objects.get(pk=appointment.pk)

    def set_quantity(self, user, appointment, quantity):
        self.login(user)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                reverse("api:appointment-set-quantity", args=[appointment.uuid]), {"quantity": quantity},
                content_type="application/json")

    def paid(self, appointment, amount):
        Payment.all_objects.create(
            tenant=self.tenant, appointment=appointment, patient=self.patient,
            receipt_number=f"R-{amount}-{appointment.pk}", amount=Decimal(amount), branch=self.a)


class BookingAsAnEstimateTests(DoctorQuantityBase):
    def test_a_booking_with_no_quantity_is_the_smallest_quantity_and_an_estimate(self):
        response = self.book(quantity=None)
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual((body["quantity"], body["price"], body["quantity_is_estimate"], body["doctor_sets_quantity"]),
                         ("10.00", "20.00", True, True))

    def test_a_quantity_asked_for_is_still_only_an_estimate_until_the_doctor_confirms(self):
        body = self.book(quantity="200").json()
        self.assertEqual((body["price"], body["quantity_is_estimate"]), ("400.00", True))

    def test_a_service_the_doctor_does_not_size_still_needs_its_quantity_at_booking(self):
        Service.all_objects.filter(pk=self.pulses.pk).update(doctor_sets_quantity=False)
        self.assertEqual(self.book(quantity=None).status_code, 400)
        body = self.book(quantity="200").json()
        self.assertEqual((body["quantity_is_estimate"], body["doctor_sets_quantity"]), (False, False))


class TheDoctorFixesTheQuantityTests(DoctorQuantityBase):
    def test_the_booked_doctor_sets_it_and_the_total_follows(self):
        appointment = self.booking()
        response = self.set_quantity("u-N1", appointment, "350")  # Dr Ahmed's own login
        self.assertEqual(response.status_code, 200, response.content)
        after = Appointment.all_objects.get(pk=appointment.pk)
        self.assertEqual((after.quantity, after.unit_price, after.price, after.quantity_is_estimate),
                         (Decimal("350.00"), Decimal("2.00"), Decimal("700.00"), False))

    def test_the_doctor_is_shown_the_quantity_and_never_a_paid_amount(self):
        body = self.set_quantity("u-N1", self.booking(), "350").json()
        self.assertEqual((body["quantity"], body["quantity_is_estimate"]), ("350.00", False))
        # A doctor sees no clinic money but their own share.
        self.assertIsNone(body["paid_total"])
        self.assertIsNone(body["amount_due"])

    def test_another_doctor_cannot_reach_it(self):
        appointment = self.booking()
        self.assertEqual(self.set_quantity("u-N2", appointment, "350").status_code, 404)
        self.assertEqual(Appointment.all_objects.get(pk=appointment.pk).quantity, Decimal("10.00"))

    def test_the_desk_cannot_but_management_can(self):
        appointment = self.booking()
        self.assertEqual(self.set_quantity("rec", appointment, "50").status_code, 403)
        for who, quantity in (("admin-a", "60"), ("owner", "70")):
            self.assertEqual(self.set_quantity(who, appointment, quantity).status_code, 200, who)
        self.assertEqual(Appointment.all_objects.get(pk=appointment.pk).quantity, Decimal("70.00"))

    def test_the_quantity_stays_inside_the_limits_management_set(self):
        appointment = self.booking()
        for bad in ("9", "501", "", None, "abc", "-5"):
            with self.subTest(quantity=bad):
                response = self.set_quantity("u-N1", appointment, bad)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn("quantity", response.json())
        self.assertEqual(Appointment.all_objects.get(pk=appointment.pk).quantity, Decimal("10.00"))

    def test_only_a_booking_that_is_confirmed_and_open_can_be_sized(self):
        for status in ("requested", "completed", "cancelled", "no_show"):
            with self.subTest(status=status):
                self.assertEqual(self.set_quantity("u-N1", self.booking(status=status), "50").status_code, 400)
        for status in ("waiting", "called", "entered"):
            with self.subTest(status=status):
                self.assertEqual(self.set_quantity("u-N1", self.booking(status=status), "50").status_code, 200)

    def test_a_service_the_doctor_does_not_size_refuses(self):
        appointment = self.booking(quantity="200")
        # Booked while the doctor sized it; management then turns that off.
        Service.all_objects.filter(pk=self.pulses.pk).update(doctor_sets_quantity=False)
        self.assertEqual(self.set_quantity("u-N1", appointment, "50").status_code, 400)
        plain = self.booking(service=str(self.laser.uuid), quantity=None)
        self.assertEqual(self.set_quantity("u-N1", plain, "5").status_code, 400)

    def test_the_booking_keeps_the_unit_price_it_was_made_with(self):
        appointment = self.booking()
        DoctorServiceRate.all_objects.filter(doctor=self.ahmed, service=self.pulses).update(price=Decimal("9"))
        self.set_quantity("u-N1", appointment, "100")
        self.assertEqual(Appointment.all_objects.get(pk=appointment.pk).price, Decimal("200.00"))  # 2 x 100, not 9 x 100

    def test_a_coupons_discount_can_never_exceed_the_new_total(self):
        coupon = DiscountCoupon.all_objects.create(
            tenant=self.tenant, patient=self.patient, amount=Decimal("100"), service=self.pulses)
        appointment = self.booking(coupon=str(coupon.uuid), quantity="100")  # total 200, discount 100
        self.set_quantity("u-N1", appointment, "10")  # total 20
        after = Appointment.all_objects.get(pk=appointment.pk)
        self.assertEqual((after.price, after.discount, after.net_price), (Decimal("20.00"), Decimal("20.00"), Decimal("0.00")))


class TheDeskHearsTests(DoctorQuantityBase):
    def notices(self, username):
        return [n for n in Notification.all_objects.filter(user__username=username, title="الطبيب حدد كمية الخدمة")]

    def test_the_desk_is_told_what_is_left_to_collect(self):
        appointment = self.booking(quantity="100")  # estimate 200
        self.paid(appointment, "200")
        self.set_quantity("u-N1", appointment, "350")  # now 700
        (notice,) = self.notices("rec")
        self.assertIn("350", notice.message)
        self.assertIn("500.00", notice.message)  # 700 - 200 still to collect
        (again,) = self.notices("admin-a")
        self.assertEqual(again.title, "الطبيب حدد كمية الخدمة")
        # The other clinic's desk hears nothing; a doctor gets no such notice.
        self.assertEqual(self.notices("u-N1"), [])

    def test_what_the_desk_sees_owed_follows_the_new_total(self):
        appointment = self.booking(quantity="100")
        self.paid(appointment, "200")
        self.set_quantity("u-N1", appointment, "350")
        self.login("rec")
        row = self.client.get(reverse("api:appointment-detail", args=[appointment.uuid])).json()
        self.assertEqual((row["price"], row["paid_total"], row["amount_due"], row["payment_status"]),
                         ("700.00", "200.00", "500.00", "partial"))

    def test_more_paid_than_the_new_total_says_to_return_the_difference(self):
        appointment = self.booking(quantity="200")
        self.paid(appointment, "400")
        self.set_quantity("u-N1", appointment, "50")  # now 100
        (notice,) = self.notices("rec")
        self.assertIn("رد الفرق", notice.message)
        self.login("rec")
        row = self.client.get(reverse("api:appointment-detail", args=[appointment.uuid])).json()
        self.assertEqual(row["amount_due"], "0.00")


class InTheRoomTests(DoctorQuantityBase):
    def test_the_doctors_room_carries_the_quantity_and_its_limits_and_no_money(self):
        appointment = self.booking()
        Visit.all_objects.get_or_create(tenant=self.tenant, appointment=appointment, defaults={
            "patient": self.patient, "doctor": self.ahmed, "branch": self.a})
        self.login("u-N1")
        (row,) = self.client.get(reverse("api:visit-in-room")).json()
        self.assertEqual(
            (row["service_name"], row["doctor_sets_quantity"], row["quantity"], row["quantity_unit"],
             row["quantity_min"], row["quantity_max"], row["quantity_is_estimate"]),
            ("Laser pulses", True, "10.00", "نبضة", "10.00", "500.00", True),
        )
        for money in ("price", "unit_price", "paid", "paid_total", "amount_due", "net_price", "discount"):
            self.assertNotIn(money, row)


class WhatTheDoctorRecordsStaysInsideTheLimitsTests(DoctorQuantityBase):
    def test_a_procedure_or_session_of_a_quantity_service_respects_its_limits(self):
        appointment = self.booking()
        visit = Visit.all_objects.filter(appointment=appointment).first() or Visit.all_objects.create(
            tenant=self.tenant, appointment=appointment, patient=self.patient, doctor=self.ahmed, branch=self.a)
        self.login("u-N1")
        body = {"name": "Laser", "visit": str(visit.uuid), "patient": str(self.patient.uuid),
                "service": str(self.pulses.uuid)}
        for quantity, expected in (("5", 400), ("501", 400), ("50", 201)):
            with self.subTest(quantity=quantity):
                response = self.client.post(reverse("api:procedure-list"), {**body, "quantity": quantity},
                                            content_type="application/json")
                self.assertEqual(response.status_code, expected, response.content)
        # A service sold as one thing is left exactly as it was.
        plain = self.client.post(reverse("api:procedure-list"), {**body, "service": str(self.laser.uuid), "quantity": "1"},
                                 content_type="application/json")
        self.assertEqual(plain.status_code, 201, plain.content)
