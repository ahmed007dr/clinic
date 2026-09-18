"""Portal: sign-in code by email, ticket number, and choosing a doctor/service.

The sign-in code has to be as hard to abuse as the password it sits beside
(no oracle, single use, limited guesses); the booking choice has to follow the
same rules as the front desk's form (a doctor of the patient's clinic, a
service that doctor is under contract for, the contract's price).
"""

from datetime import timedelta

from django.core import mail
from django.core.cache import cache
from django.utils import timezone

from appointments.models import Appointment
from billing.models import DoctorServiceRate
from branches.models import Branch
from employees.models import Employee, EmployeeType, Specialization
from services.models import Service
from tenants.context import tenant_context

from .models import CODE_MAX_ATTEMPTS, PatientAccount, PortalLoginCode
from .tests import PASSWORD, PortalBase


class OtpTests(PortalBase):
    def setUp(self):
        super().setUp()
        with tenant_context(self.a):
            self.alice.email = "Alice@Example.com"
            self.alice.save()
        self.enrol(self.alice)
        self.client.post(self.url("logout"))
        mail.outbox.clear()

    def request_code(self, identifier="01000000001"):
        return self.client.post(
            self.url("otp-request"), {"identifier": identifier}, content_type="application/json"
        )

    def verify(self, code, identifier="01000000001"):
        return self.client.post(
            self.url("otp-verify"), {"identifier": identifier, "code": code}, content_type="application/json"
        )

    def sent_code(self):
        return next(line for line in mail.outbox[-1].body.splitlines() if line.strip().isdigit()).strip()

    def test_a_code_signs_the_patient_in_once(self):
        self.assertEqual(self.request_code().status_code, 200)
        self.assertEqual(mail.outbox[-1].to, ["Alice@Example.com"])
        code = self.sent_code()
        self.assertEqual(self.verify(code).status_code, 200)
        self.assertEqual(self.client.get(self.url("me")).json()["name"], "Alice")
        self.client.post(self.url("logout"))
        self.assertEqual(self.verify(code).status_code, 400)

    def test_the_email_address_works_as_the_identifier_too(self):
        self.request_code("alice@example.com")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(self.verify(self.sent_code(), "alice@example.com").status_code, 200)

    def test_the_answer_is_the_same_with_or_without_an_account_or_an_email(self):
        known = self.request_code()
        unknown = self.request_code("01999999999")
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known.json(), unknown.json())
        # Bob has an account but no email: nothing is sent, nothing differs.
        self.enrol(self.bob)
        self.client.post(self.url("logout"))
        mail.outbox.clear()
        cache.clear()
        no_email = self.request_code("01000000002")
        self.assertEqual(no_email.json(), known.json())
        self.assertEqual(mail.outbox, [])

    def test_a_wrong_code_is_refused_and_guesses_are_limited(self):
        self.request_code()
        code = self.sent_code()
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(CODE_MAX_ATTEMPTS):
            self.assertEqual(self.verify(wrong).status_code, 400)
        cache.clear()
        # The account is locked for a while (as after five bad passwords), and
        # the code itself was spent by the guesses: the right one no longer works.
        with tenant_context(self.a):
            self.assertFalse(PortalLoginCode.objects.get().is_usable)
            PatientAccount.objects.update(locked_until=None)
        self.assertEqual(self.verify(code).status_code, 400)

    def test_a_code_is_not_reissued_within_a_minute(self):
        self.request_code()
        self.request_code()
        self.assertEqual(len(mail.outbox), 1)

    def test_an_expired_code_is_refused(self):
        self.request_code()
        code = self.sent_code()
        with tenant_context(self.a):
            PortalLoginCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.verify(code).status_code, 400)

    def test_a_stopped_account_gets_no_code(self):
        with tenant_context(self.a):
            PatientAccount.objects.update(is_active=False)
        self.request_code()
        self.assertEqual(mail.outbox, [])

    def test_the_password_still_works(self):
        self.assertEqual(self.login("01000000001", PASSWORD).status_code, 200)


class BookingTests(PortalBase):
    def setUp(self):
        super().setUp()
        with tenant_context(self.a):
            doctor_type, _ = EmployeeType.all_objects.get_or_create(tenant=self.a, name="Doctor")
            self.derma = Specialization.all_objects.create(tenant=self.a, name="Derma")
            self.dr = self._doctor(doctor_type, "Dr Home", self.branch, "111")
            self.dr.specializations.add(self.derma)
            other_branch = Branch.all_objects.create(tenant=self.a, name="Elsewhere", code="EL")
            self.dr_away = self._doctor(doctor_type, "Dr Away", other_branch, "222")
            self.laser = Service.all_objects.create(
                tenant=self.a, name="Laser", base_price=100, specialization=self.derma
            )
            self.peel = Service.all_objects.create(tenant=self.a, name="Peel", base_price=50)
            DoctorServiceRate.all_objects.create(
                tenant=self.a, doctor=self.dr, service=self.laser, price=150, commission_percent=40
            )
            DoctorServiceRate.all_objects.create(tenant=self.a, doctor=self.dr_away, service=self.peel)
        self.enrol(self.alice)

    def _doctor(self, doctor_type, name, branch, national_id):
        return Employee.all_objects.create(
            tenant=self.a, name=name, branch=branch, employee_type=doctor_type,
            national_id=national_id, salary_value=0,
        )

    def request(self, **extra):
        when = (timezone.now() + timedelta(days=2)).isoformat()
        return self.client.post(
            self.url("appointments"), {"scheduled_date": when, **extra}, content_type="application/json"
        )

    def test_options_offer_only_this_clinics_doctors_and_their_contracted_services(self):
        body = self.client.get(self.url("booking-options")).json()
        self.assertEqual([d["name"] for d in body["doctors"]], ["Dr Home"])
        self.assertEqual([s["name"] for s in body["specializations"]], ["Derma"])
        services = body["doctors"][0]["services"]
        self.assertEqual([(s["name"], s["price"]) for s in services], [("Laser", "150.00")])
        # A doctor's share is never sent to a patient.
        self.assertNotIn("commission", str(body))

    def test_a_request_carries_the_doctor_service_and_contract_price(self):
        response = self.request(doctor=str(self.dr.uuid), service=str(self.laser.uuid))
        self.assertEqual(response.status_code, 201, response.content)
        with tenant_context(self.a):
            booking = Appointment.objects.get(uuid=response.json()["uuid"])
        self.assertEqual(booking.status, "requested")
        self.assertEqual(booking.doctor_id, self.dr.pk)
        self.assertEqual(booking.service_id, self.laser.pk)
        self.assertEqual(booking.specialization_id, self.derma.pk)
        self.assertEqual(float(booking.price), 150.0)

    def test_a_service_outside_the_doctors_contract_is_refused(self):
        response = self.request(doctor=str(self.dr.uuid), service=str(self.peel.uuid))
        self.assertEqual(response.status_code, 400)
        self.assertIn("service", response.json())

    def test_a_doctor_of_another_clinic_is_refused(self):
        response = self.request(doctor=str(self.dr_away.uuid))
        self.assertEqual(response.status_code, 400)
        self.assertIn("doctor", response.json())

    def test_a_specialty_the_doctor_does_not_have_is_refused(self):
        with tenant_context(self.a):
            other = Specialization.all_objects.create(tenant=self.a, name="Dental")
        response = self.request(doctor=str(self.dr.uuid), specialization=str(other.uuid))
        self.assertEqual(response.status_code, 400)
        self.assertIn("specialization", response.json())

    def test_a_request_with_no_choices_is_still_accepted(self):
        response = self.request()
        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.json()["doctor_name"])

    def test_todays_waiting_booking_shows_its_ticket_number_and_place(self):
        with tenant_context(self.a):
            first = Appointment.all_objects.create(
                tenant=self.a, patient=self.bob, doctor=self.dr, branch=self.branch,
                status="waiting", scheduled_date=timezone.now(),
            )
            mine = Appointment.all_objects.create(
                tenant=self.a, patient=self.alice, doctor=self.dr, branch=self.branch,
                status="waiting", scheduled_date=timezone.now() + timedelta(minutes=1),
            )
        rows = {row["uuid"]: row for row in self.client.get(self.url("appointments")).json()}
        card = rows[str(mine.uuid)]
        self.assertEqual(card["ticket_number"], mine.serial_number)
        self.assertEqual(card["ahead_count"], 1)
        self.assertEqual(card["queue_position"], 2)
        # Bob's booking is not in Alice's list at all.
        self.assertNotIn(str(first.uuid), rows)

    def test_a_future_booking_has_no_ticket_yet(self):
        response = self.request()
        self.assertIsNone(response.json()["ticket_number"])
