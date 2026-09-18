"""Payment with the booking, "paid in full to go in", and discount coupons.

The group owner's rules (2026-09-18):

* A booking and its payment are one step, into the desk's open shift; a payment
  always belongs to a booking and cannot exceed what it still owes.
* A patient goes in to the doctor only once the booking is paid in full —
  unless management gave them a discount coupon, which lowers what is owed.
* Coupons are issued by an Admin or the Owner, in a patient's name, for a
  service or a specialty; spent once.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from appointments.models import Appointment
from billing.models import DiscountCoupon, Payment, PaymentMethod
from branches.models import Branch
from employees.models import Employee, EmployeeType, Specialization
from patients.models import Patient
from services.models import Service
from tenants.context import tenant_context
from tenants.models import Tenant

User = get_user_model()


class BookingPaymentTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            self.branch = Branch.all_objects.create(tenant=self.tenant, name="Bk", code="BK")
            roles = {
                n: ClinicRole.all_objects.get_or_create(tenant=self.tenant, name=n)[0]
                for n in ("Owner", "Admin", "Reception", "Doctor")
            }
            doctor_type = EmployeeType.all_objects.get_or_create(tenant=self.tenant, name="Doctor")[0]
            self.doctor = Employee.all_objects.create(
                tenant=self.tenant, name="Dr Bk", branch=self.branch, employee_type=doctor_type,
                national_id="BK-1", salary_value=0,
            )
            self.derma = Specialization.all_objects.create(tenant=self.tenant, name="Derma-Bk")
            self.consult = Service.all_objects.create(
                tenant=self.tenant, name="Consult-Bk", base_price=300, specialization=self.derma
            )
            self.laser = Service.all_objects.create(tenant=self.tenant, name="Laser-Bk", base_price=1000)
            self.cash = PaymentMethod.all_objects.create(tenant=self.tenant, name="Cash-Bk")
            self.patient = Patient.all_objects.create(tenant=self.tenant, name="Mona", branch=self.branch)
            self.other_patient = Patient.all_objects.create(tenant=self.tenant, name="Sara", branch=self.branch)
        for key, role in (("desk", "Reception"), ("admin", "Admin")):
            User.objects.create_user(
                username=key, email=f"{key}@bk.local", password="pass12345",
                tenant=self.tenant, role=roles[role], branch=self.branch,
            )

    # -------------------------------------------------------------- helpers

    def login(self, key):
        self.client.logout()
        self.assertTrue(self.client.login(email=f"{key}@bk.local", password="pass12345"))

    def post(self, name, data=None, args=None):
        return self.client.post(reverse(name, args=args), data or {}, content_type="application/json")

    def open_shift(self):
        self.assertEqual(self.post("api:shift-open").status_code, 201)

    def booking(self, service=None, patient=None, **extra):
        return self.post("api:appointment-list", {
            "patient": str((patient or self.patient).uuid),
            "doctor": str(self.doctor.uuid),
            "service": str((service or self.consult).uuid),
            "scheduled_date": timezone.now().isoformat(),
            **extra,
        })

    def paying(self, amount, **extra):
        return self.booking(paid_amount=str(amount), payment_method=str(self.cash.uuid), **extra)

    def payments(self):
        with tenant_context(self.tenant):
            return list(Payment.all_objects.filter(voided_at__isnull=True))

    def go_in(self, uuid):
        return self.post("api:appointment-set-status", {"status": "entered"}, args=[uuid])

    def collect(self, uuid, amount):
        return self.post("api:payment-list", {
            "appointment": uuid, "amount": str(amount), "method": str(self.cash.uuid),
        })

    def coupon(self, amount="100", service=None, specialization=None, patient=None, **extra):
        body = {"patient": str((patient or self.patient).uuid), "amount": amount, **extra}
        if service is not None:
            body["service"] = str(service.uuid)
        if specialization is not None:
            body["specialization"] = str(specialization.uuid)
        return self.post("api:coupon-list", body)

    # -------------------------------------------------- booking and payment

    def test_a_booking_and_its_payment_are_one_step_in_the_desks_shift(self):
        self.login("desk")
        self.open_shift()
        response = self.paying(300)
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["paid_total"], "300.00")
        self.assertEqual(body["payment_status"], "paid")
        self.assertEqual(body["amount_due"], "0.00")
        self.assertTrue(body["receipt_uuid"])
        (payment,) = self.payments()
        self.assertEqual(str(payment.appointment.uuid), body["uuid"])
        self.assertEqual(payment.method, self.cash)
        self.assertEqual(payment.created_by.username, "desk")
        self.assertIsNotNone(payment.shift)
        # The system issues the receipt number.
        self.assertTrue(payment.receipt_number.startswith("R-"))

    def test_the_open_shift_shows_the_booking_and_its_payment_at_once(self):
        self.login("desk")
        self.open_shift()
        self.paying(200)
        shift = self.client.get(reverse("api:shift-current")).json()["shift"]
        self.assertEqual(len(shift["bookings"]), 1)
        booking = shift["bookings"][0]
        self.assertEqual(booking["paid_total"], "200.00")
        self.assertEqual(booking["amount_due"], "100.00")
        self.assertEqual(len(shift["payments"]), 1)
        self.assertEqual(shift["summary"]["revenue"], "200.00")

    def test_the_shift_lists_bookings_payments_and_expenses_newest_first(self):
        self.login("desk")
        self.open_shift()
        first = self.paying(100).json()
        second = self.booking(patient=self.other_patient, paid_amount="150", payment_method=str(self.cash.uuid)).json()
        for amount in ("5.00", "9.00"):
            self.post("api:expense-list", {"amount": amount, "method": str(self.cash.uuid)})
        shift = self.client.get(reverse("api:shift-current")).json()["shift"]
        self.assertEqual([b["uuid"] for b in shift["bookings"]], [second["uuid"], first["uuid"]])
        self.assertEqual([p["amount"] for p in shift["payments"]], ["150.00", "100.00"])
        self.assertEqual([e["amount"] for e in shift["expenses"]], ["9.00", "5.00"])

    def test_a_shift_starts_from_zero_with_no_expected_balance(self):
        self.login("desk")
        opened = self.post("api:shift-open", {"opening_balance": "500"})
        self.assertEqual(opened.status_code, 201)
        summary = opened.json()["summary"]
        self.assertEqual(summary["net"], "0.00")
        self.assertNotIn("opening_balance", summary)
        self.assertNotIn("expected_balance", summary)
        self.assertNotIn("opening_balance", opened.json())

    def test_paying_at_booking_without_a_shift_keeps_nothing(self):
        self.login("desk")
        response = self.paying(300)
        self.assertEqual(response.status_code, 400)
        self.assertIn("وردية", str(response.json()))
        with tenant_context(self.tenant):
            self.assertEqual(Appointment.all_objects.count(), 0)
        self.assertEqual(self.payments(), [])

    def test_booking_without_paying_needs_no_shift(self):
        self.login("desk")
        self.assertEqual(self.booking().status_code, 201)
        self.assertEqual(self.payments(), [])

    def test_the_payment_is_checked_against_the_price_and_needs_a_method(self):
        self.login("desk")
        self.open_shift()
        too_much = self.paying(301)
        self.assertEqual(too_much.status_code, 400)
        self.assertIn("paid_amount", too_much.json())
        no_method = self.booking(paid_amount="100")
        self.assertEqual(no_method.status_code, 400)
        self.assertIn("payment_method", no_method.json())
        with tenant_context(self.tenant):
            self.assertEqual(Appointment.all_objects.count(), 0)

    def test_receipt_numbers_are_issued_in_sequence_and_never_repeat(self):
        self.login("desk")
        self.open_shift()
        first = self.paying(100).json()
        second = self.booking(patient=self.other_patient, paid_amount="100", payment_method=str(self.cash.uuid)).json()
        numbers = {p.receipt_number for p in self.payments()}
        self.assertEqual(len(numbers), 2, (first, second))

    # ------------------------------------------------- collecting the rest

    def test_the_rest_is_collected_against_the_booking_and_never_more(self):
        self.login("desk")
        self.open_shift()
        uuid = self.paying(100).json()["uuid"]
        over = self.collect(uuid, 201)
        self.assertEqual(over.status_code, 400)
        self.assertIn("amount", over.json())
        ok = self.collect(uuid, 200)
        self.assertEqual(ok.status_code, 201, ok.content)
        self.assertTrue(ok.json()["receipt_number"].startswith("R-"))
        booking = self.client.get(reverse("api:appointment-detail", args=[uuid])).json()
        self.assertEqual(booking["payment_status"], "paid")
        # Fully paid: nothing more can be taken.
        self.assertEqual(self.collect(uuid, 1).status_code, 400)

    def test_the_collect_screen_lists_only_bookings_that_still_owe(self):
        self.login("desk")
        self.open_shift()
        owing = self.paying(100).json()["uuid"]          # 200 left
        self.paying(300, service=self.consult, patient=self.other_patient)  # paid in full
        never_paid = self.booking(patient=self.other_patient).json()["uuid"]
        cancelled = self.booking(patient=self.other_patient).json()["uuid"]
        self.client.patch(
            reverse("api:appointment-detail", args=[cancelled]), {"status": "cancelled"}, content_type="application/json"
        )
        found = self.client.get(reverse("api:appointment-list"), {"owing": "1"}).json()["results"]
        self.assertEqual({row["uuid"] for row in found}, {owing, never_paid})
        # And it can be found by the patient's name.
        by_name = self.client.get(reverse("api:appointment-list"), {"owing": "1", "search": "Mona"}).json()["results"]
        self.assertEqual([row["uuid"] for row in by_name], [owing])
        self.assertEqual(by_name[0]["patient_name"], "Mona")

    # ----------------------------------------------- paid in full to go in

    def test_an_unpaid_patient_cannot_go_in_to_the_doctor(self):
        self.login("desk")
        uuid = self.booking().json()["uuid"]
        refused = self.go_in(uuid)
        self.assertEqual(refused.status_code, 400)
        self.assertIn("300.00", str(refused.json()))

    def test_a_part_paid_patient_cannot_go_in_until_the_rest_is_paid(self):
        self.login("desk")
        self.open_shift()
        uuid = self.paying(100).json()["uuid"]
        refused = self.go_in(uuid)
        self.assertEqual(refused.status_code, 400)
        self.assertIn("200.00", str(refused.json()))
        self.collect(uuid, 200)
        self.assertEqual(self.go_in(uuid).status_code, 200)

    def test_the_form_edit_cannot_slip_past_the_rule_either(self):
        self.login("desk")
        uuid = self.booking().json()["uuid"]
        response = self.client.patch(
            reverse("api:appointment-detail", args=[uuid]), {"status": "entered"}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("status", response.json())

    def test_a_new_booking_created_as_entered_needs_full_payment_in_the_same_step(self):
        self.login("desk")
        self.open_shift()
        self.assertEqual(self.booking(status="entered").status_code, 400)
        self.assertEqual(self.paying(100, status="entered").status_code, 400)
        self.assertEqual(self.paying(300, status="entered").status_code, 201)

    def test_a_free_booking_can_go_in(self):
        self.login("admin")
        free = self.post("api:appointment-list", {
            "patient": str(self.patient.uuid), "doctor": str(self.doctor.uuid),
            "scheduled_date": timezone.now().isoformat(), "price": "0",
        }).json()
        self.assertEqual(self.go_in(free["uuid"]).status_code, 200)

    # --------------------------------------------------------------- coupons

    def test_only_management_issues_coupons(self):
        self.login("desk")
        self.assertEqual(self.coupon(service=self.consult).status_code, 403)
        self.login("admin")
        made = self.coupon(service=self.consult)
        self.assertEqual(made.status_code, 201, made.content)
        self.assertEqual(made.json()["status"], "available")

    def test_a_coupon_needs_a_service_or_a_specialty(self):
        self.login("admin")
        self.assertEqual(self.coupon().status_code, 400)
        self.assertEqual(self.coupon(specialization=self.derma).status_code, 201)

    def test_a_coupon_lowers_what_is_owed_and_lets_the_patient_in_when_that_is_paid(self):
        self.login("admin")
        self.coupon(amount="100", service=self.consult)
        self.login("desk")
        self.open_shift()
        available = self.client.get(reverse("api:coupon-list"), {"patient": str(self.patient.uuid), "available": "1"})
        (coupon,) = available.json()["results"]
        booked = self.paying(200, coupon=coupon["uuid"])
        self.assertEqual(booked.status_code, 201, booked.content)
        body = booked.json()
        self.assertEqual(body["price"], "300.00")
        self.assertEqual(body["discount"], "100.00")
        self.assertEqual(body["net_price"], "200.00")
        self.assertEqual(body["payment_status"], "paid")
        self.assertEqual(self.go_in(body["uuid"]).status_code, 200)

    def test_a_coupon_is_spent_once(self):
        self.login("admin")
        coupon = self.coupon(amount="100", service=self.consult).json()["uuid"]
        self.login("desk")
        self.assertEqual(self.booking(coupon=coupon).status_code, 201)
        second = self.booking(coupon=coupon)
        self.assertEqual(second.status_code, 400)
        self.assertIn("coupon", second.json())
        self.login("admin")
        self.assertEqual(
            self.client.get(reverse("api:coupon-list"), {"available": "1"}).json()["results"], []
        )

    def test_a_coupon_only_fits_its_patient_and_its_service_or_specialty(self):
        self.login("admin")
        coupon = self.coupon(amount="100", service=self.consult).json()["uuid"]
        by_specialty = self.coupon(amount="50", specialization=self.derma, patient=self.patient).json()["uuid"]
        self.login("desk")
        # Someone else's patient.
        self.assertEqual(self.booking(patient=self.other_patient, coupon=coupon).status_code, 400)
        # Another service.
        self.assertEqual(self.booking(service=self.laser, coupon=coupon).status_code, 400)
        # A specialty coupon fits any service of that specialty.
        fits = self.booking(coupon=by_specialty)
        self.assertEqual(fits.status_code, 201, fits.content)
        self.assertEqual(fits.json()["discount"], "50.00")

    def test_a_discount_never_exceeds_the_price(self):
        self.login("admin")
        coupon = self.coupon(amount="5000", service=self.consult).json()["uuid"]
        self.login("desk")
        body = self.booking(coupon=coupon).json()
        self.assertEqual(body["discount"], "300.00")
        self.assertEqual(body["net_price"], "0.00")
        self.assertEqual(self.go_in(body["uuid"]).status_code, 200)

    def test_an_expired_or_cancelled_coupon_cannot_be_used(self):
        self.login("admin")
        expired = self.coupon(amount="100", service=self.consult).json()["uuid"]
        cancelled = self.coupon(amount="100", service=self.consult).json()["uuid"]
        self.assertEqual(self.post("api:coupon-void", args=[cancelled]).status_code, 200)
        with tenant_context(self.tenant):
            DiscountCoupon.all_objects.filter(uuid=expired).update(expires_on=timezone.now().date() - timedelta(days=1))
        self.login("desk")
        self.assertEqual(self.booking(coupon=expired).status_code, 400)
        self.assertEqual(self.booking(coupon=cancelled).status_code, 400)

    def test_a_spent_coupon_cannot_be_cancelled_and_the_desk_cannot_cancel_any(self):
        self.login("admin")
        coupon = self.coupon(amount="100", service=self.consult).json()["uuid"]
        self.login("desk")
        self.assertEqual(self.post("api:coupon-void", args=[coupon]).status_code, 403)
        self.booking(coupon=coupon)
        self.login("admin")
        self.assertEqual(self.post("api:coupon-void", args=[coupon]).status_code, 400)

    def test_a_failed_booking_does_not_spend_the_coupon(self):
        self.login("admin")
        coupon = self.coupon(amount="100", service=self.consult).json()["uuid"]
        self.login("desk")
        # Paying with no open shift is refused — and the coupon stays whole.
        self.assertEqual(self.paying(200, coupon=coupon).status_code, 400)
        self.open_shift()
        self.assertEqual(self.paying(200, coupon=coupon).status_code, 201)

    def test_the_doctors_share_follows_what_was_actually_paid(self):
        """A discount lowers the payment, so the share — a percentage of what
        is paid — falls with it; nothing to change in the commission rules."""
        from billing.models import DoctorCommission, DoctorServiceRate

        with tenant_context(self.tenant):
            DoctorServiceRate.all_objects.create(
                tenant=self.tenant, doctor=self.doctor, service=self.consult, commission_percent=Decimal("50"),
            )
        self.login("admin")
        coupon = self.coupon(amount="100", service=self.consult).json()["uuid"]
        self.login("desk")
        self.open_shift()
        self.assertEqual(self.paying(200, coupon=coupon).status_code, 201)
        with tenant_context(self.tenant):
            (commission,) = DoctorCommission.all_objects.all()
        self.assertEqual(commission.amount, Decimal("100.00"))
