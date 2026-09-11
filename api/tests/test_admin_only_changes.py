"""Changes only an admin may make, refused to everyone else by the server.

Hiding a button is not a control: before these rules, a receptionist could
edit or delete any payment, and any member could delete a patient, a booking
or a visit, by calling the API directly. The server-rendered screens already
refused all of that; the API was the looser door.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from appointments.models import Appointment
from billing.models import Payment
from branches.models import Branch
from medical.models import Visit
from patients.models import Patient
from tenants.context import tenant_context
from tenants.models import Tenant
from tenants.testing import link_doctor

User = get_user_model()

ROLES = ("Owner", "Admin", "Reception", "Doctor")


class AdminOnlyChangeTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            self.branch = Branch.all_objects.create(
                tenant=self.tenant, name="Desk", code="DK"
            )
            roles = {
                name: ClinicRole.all_objects.get_or_create(tenant=self.tenant, name=name)[0]
                for name in ROLES
            }
        for name in ROLES:
            User.objects.create_user(
                username=f"{name.lower()}-ch", email=f"{name.lower()}-ch@t.local",
                password="pass12345", tenant=self.tenant,
                role=roles[name], branch=self.branch,
            )
        self.doctor = link_doctor(User.objects.get(email="doctor-ch@t.local"))

    def login(self, role):
        self.assertTrue(
            self.client.login(email=f"{role.lower()}-ch@t.local", password="pass12345")
        )

    # ------------------------------------------------------------- fixtures

    def make_patient(self, name="P"):
        with tenant_context(self.tenant):
            return Patient.all_objects.create(tenant=self.tenant, name=name, branch=self.branch)

    def make_appointment(self, patient=None):
        with tenant_context(self.tenant):
            return Appointment.all_objects.create(
                tenant=self.tenant, patient=patient or self.make_patient(),
                branch=self.branch, scheduled_date=timezone.now(), price=100,
            )

    def make_payment(self, receipt):
        appointment = self.make_appointment()
        with tenant_context(self.tenant):
            return Payment.all_objects.create(
                tenant=self.tenant, appointment=appointment, patient=appointment.patient,
                receipt_number=receipt, amount=100, branch=self.branch,
            )

    def make_visit(self):
        with tenant_context(self.tenant):
            return Visit.all_objects.create(
                tenant=self.tenant, patient=self.make_patient(), branch=self.branch,
                visit_date=timezone.now(), diagnosis="d", doctor=self.doctor,
            )

    def exists(self, model, pk):
        with tenant_context(self.tenant):
            return model.all_objects.filter(pk=pk).exists()

    # ------------------------------------------------------------- payments

    def test_reception_may_still_record_a_payment(self):
        appointment = self.make_appointment()
        self.login("Reception")
        self.client.post(reverse("api:shift-open"), {"opening_balance": "0"},
                         content_type="application/json")
        response = self.client.post(
            reverse("api:payment-list"),
            {
                "appointment": str(appointment.uuid),
                "patient": str(appointment.patient.uuid),
                "receipt_number": "NEW-1",
                "amount": "100.00",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)

    def test_only_an_admin_may_edit_a_payment(self):
        for role, expected in (
            ("Reception", 403), ("Doctor", 403), ("Admin", 200), ("Owner", 200),
        ):
            with self.subTest(role=role):
                payment = self.make_payment(f"E-{role}")
                self.login(role)
                response = self.client.patch(
                    reverse("api:payment-detail", args=[payment.uuid]),
                    {"amount": "1.00"},
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, expected, response.content)
                with tenant_context(self.tenant):
                    payment.refresh_from_db()
                self.assertEqual(float(payment.amount), 1.0 if expected == 200 else 100.0)

    def test_only_an_admin_may_delete_a_payment(self):
        for role, expected in (
            ("Reception", 403), ("Doctor", 403), ("Admin", 204), ("Owner", 204),
        ):
            with self.subTest(role=role):
                payment = self.make_payment(f"D-{role}")
                self.login(role)
                response = self.client.delete(
                    reverse("api:payment-detail", args=[payment.uuid])
                )
                self.assertEqual(response.status_code, expected)
                self.assertEqual(self.exists(Payment, payment.pk), expected != 204)

    # ------------------------------------------- patients, bookings, visits

    def test_only_an_admin_may_delete_a_patient(self):
        for role, expected in (
            ("Reception", 403), ("Doctor", 403), ("Admin", 204), ("Owner", 204),
        ):
            with self.subTest(role=role):
                patient = self.make_patient(f"del-{role}")
                self.login(role)
                response = self.client.delete(
                    reverse("api:patient-detail", args=[patient.uuid])
                )
                self.assertEqual(response.status_code, expected)
                self.assertEqual(self.exists(Patient, patient.pk), expected != 204)

    def test_only_an_admin_may_delete_a_booking(self):
        for role, expected in (
            ("Reception", 403), ("Doctor", 403), ("Admin", 204), ("Owner", 204),
        ):
            with self.subTest(role=role):
                appointment = self.make_appointment()
                self.login(role)
                response = self.client.delete(
                    reverse("api:appointment-detail", args=[appointment.uuid])
                )
                self.assertEqual(response.status_code, expected)
                self.assertEqual(self.exists(Appointment, appointment.pk), expected != 204)

    def test_reception_may_still_edit_a_booking(self):
        """The delete rule must not spread to edits: moving a booking's time is
        the front desk's everyday work."""
        appointment = self.make_appointment()
        self.login("Reception")
        response = self.client.patch(
            reverse("api:appointment-detail", args=[appointment.uuid]),
            {"notes": "moved"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)

    def test_a_doctor_may_write_a_visit_but_not_delete_one(self):
        visit = self.make_visit()
        self.login("Doctor")
        edited = self.client.patch(
            reverse("api:visit-detail", args=[visit.uuid]),
            {"diagnosis": "revised"},
            content_type="application/json",
        )
        self.assertEqual(edited.status_code, 200, edited.content)

        deleted = self.client.delete(reverse("api:visit-detail", args=[visit.uuid]))
        self.assertEqual(deleted.status_code, 403)
        self.assertTrue(self.exists(Visit, visit.pk))

    def test_an_admin_may_delete_a_visit(self):
        visit = self.make_visit()
        self.login("Admin")
        response = self.client.delete(reverse("api:visit-detail", args=[visit.uuid]))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(self.exists(Visit, visit.pk))

    # -------------------------------------------------------------- expenses

    def test_the_expense_ledger_is_front_desk_only(self):
        """Matches the screen: `manage_billing` hides it from doctors, and now
        the API refuses them too instead of answering a direct call."""
        for role, expected in (
            ("Doctor", 403), ("Reception", 200), ("Admin", 200), ("Owner", 200),
        ):
            with self.subTest(role=role):
                self.login(role)
                self.assertEqual(
                    self.client.get(reverse("api:expense-list")).status_code, expected
                )
