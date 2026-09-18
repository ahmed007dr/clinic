"""`POST /api/my-report/email/` — a person's own report, to their own address.

Two things matter: the address can never be chosen by the caller, and the
report holds no more than that role's own screens show.
"""

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from appointments.models import Appointment
from billing.models import DoctorCommission, Expense, ExpenseCategory, Payment, PaymentMethod
from branches.models import Branch
from patients.models import Patient
from services.models import Service
from tenants.context import tenant_context
from tenants.models import Tenant
from tenants.testing import link_doctor

User = get_user_model()
PASSWORD = "pass12345"


class MyReportTests(TestCase):
    def setUp(self):
        cache.clear()
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            self.branch = Branch.all_objects.create(tenant=self.tenant, name="Rep", code="RP")
            roles = {
                n: ClinicRole.all_objects.get_or_create(tenant=self.tenant, name=n)[0]
                for n in ("Doctor", "Reception", "Admin")
            }
            self.patient = Patient.all_objects.create(tenant=self.tenant, name="Sara", branch=self.branch)
            self.service = Service.all_objects.create(tenant=self.tenant, name="Rep-Laser", base_price=100)
            self.method = PaymentMethod.all_objects.create(tenant=self.tenant, name="Cash-Rep")
            category = ExpenseCategory.all_objects.create(tenant=self.tenant, name="Rent-Rep")
        self.users = {}
        for key in ("Doctor", "Reception", "Admin"):
            self.users[key] = User.objects.create_user(
                username=f"rep-{key}", email=f"rep-{key.lower()}@x.local", password=PASSWORD,
                tenant=self.tenant, role=roles[key], branch=self.branch,
            )
        self.employee = link_doctor(self.users["Doctor"], self.patient)
        with tenant_context(self.tenant):
            Employee = type(self.employee)
            Employee.all_objects.filter(pk=self.employee.pk).update(email="dr-own@x.local")
            booking = Appointment.all_objects.get(patient=self.patient, doctor=self.employee)
            payment = Payment.all_objects.create(
                tenant=self.tenant, appointment=booking, patient=self.patient, method=self.method,
                receipt_number="RCP-REP-1", amount=200, branch=self.branch,
            )
            DoctorCommission.all_objects.filter(payment=payment).delete()
            DoctorCommission.all_objects.create(
                tenant=self.tenant, doctor=self.employee, branch=self.branch, appointment=booking,
                patient=self.patient, service=self.service, description="Rep-Laser", original_price=200,
                paid_amount=200, percent=40, amount=80, payment=payment,
            )
            Expense.all_objects.create(
                tenant=self.tenant, branch=self.branch, category=category, amount=30, date=timezone.now().date()
            )
        mail.outbox.clear()

    def send(self, key, data=None):
        self.client.logout()
        self.assertTrue(self.client.login(email=f"rep-{key.lower()}@x.local", password=PASSWORD))
        return self.client.post(reverse("api:my-report-email"), data or {}, content_type="application/json")

    def test_a_doctor_gets_their_bookings_and_share_at_their_own_address(self):
        response = self.send("Doctor")
        self.assertEqual(response.status_code, 200, response.content)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["dr-own@x.local"])
        self.assertIn("Sara", message.body)
        self.assertIn("80.00", message.body)

    def test_the_recipient_cannot_be_chosen(self):
        self.send("Doctor", {"to": "attacker@evil.local", "email": "attacker@evil.local"})
        self.assertEqual(mail.outbox[0].to, ["dr-own@x.local"])

    def test_a_login_with_no_staff_email_record_falls_back_to_the_login_address(self):
        self.send("Admin")
        self.assertEqual(mail.outbox[0].to, ["rep-admin@x.local"])

    def test_the_front_desk_sees_no_expenses_and_only_its_own_shift_takings(self):
        self.send("Reception")
        body = mail.outbox[0].body
        self.assertNotIn("المصروفات", body)
        self.assertNotIn("Rent-Rep", body)
        # The payment was not taken in this receptionist's open shift.
        self.assertNotIn("Cash-Rep", body)

    def test_an_admin_gets_takings_and_expenses(self):
        self.send("Admin")
        body = mail.outbox[0].body
        self.assertIn("Cash-Rep", body)
        self.assertIn("Rent-Rep", body)

    def test_a_second_request_within_the_cooldown_is_refused(self):
        self.assertEqual(self.send("Admin").status_code, 200)
        self.assertEqual(self.send("Admin").status_code, 429)
        self.assertEqual(len(mail.outbox), 1)

    def test_a_backwards_period_is_refused(self):
        response = self.send("Admin", {"from": "2026-09-10", "to": "2026-09-01"})
        self.assertEqual(response.status_code, 400)

    def test_it_needs_a_login(self):
        self.client.logout()
        response = self.client.post(reverse("api:my-report-email"), {}, content_type="application/json")
        self.assertIn(response.status_code, (401, 403))
