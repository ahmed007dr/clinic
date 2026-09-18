"""A doctor looks things up; the desk books and registers.

The group owner's rules (2026-09-19): a doctor receives the bookings made for
them and looks up their own patients and their queue. They do not book, move
the queue, or register a patient — and on a treatment plan they work the
course but do not re-point it (patient, doctor, branch, service, start date).
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from appointments.models import Appointment
from branches.models import Branch
from medical.models import TreatmentPlan
from patients.models import Patient
from services.models import Service
from tenants.context import tenant_context
from tenants.models import Tenant
from tenants.testing import link_doctor

User = get_user_model()
PASSWORD = "pass12345"


class DoctorReadOnlyTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            self.branch = Branch.all_objects.create(tenant=self.tenant, name="Dr", code="DR")
            roles = {
                n: ClinicRole.all_objects.get_or_create(tenant=self.tenant, name=n)[0]
                for n in ("Doctor", "Reception")
            }
            self.patient = Patient.all_objects.create(tenant=self.tenant, name="Mona", branch=self.branch)
            self.service = Service.all_objects.create(tenant=self.tenant, name="Laser-Dr", base_price=100)
            self.other_service = Service.all_objects.create(tenant=self.tenant, name="Peel-Dr", base_price=50)
        self.doc = User.objects.create_user(
            username="doc-ro", email="doc-ro@x.local", password=PASSWORD,
            tenant=self.tenant, role=roles["Doctor"], branch=self.branch,
        )
        self.employee = link_doctor(self.doc, self.patient)
        self.desk = User.objects.create_user(
            username="desk-ro", email="desk-ro@x.local", password=PASSWORD,
            tenant=self.tenant, role=roles["Reception"], branch=self.branch,
        )
        with tenant_context(self.tenant):
            self.booking = Appointment.all_objects.create(
                tenant=self.tenant, patient=self.patient, doctor=self.employee, branch=self.branch,
                status="waiting", scheduled_date=timezone.now() + timedelta(minutes=5),
            )
            self.plan = TreatmentPlan.all_objects.create(
                tenant=self.tenant, patient=self.patient, doctor=self.employee, branch=self.branch,
                service=self.service, title="Course", planned_sessions=4,
                start_date=timezone.now().date(),
            )

    def as_(self, key):
        self.client.logout()
        self.assertTrue(self.client.login(email=f"{key}@x.local", password=PASSWORD))

    def send(self, method, name, data=None, args=None):
        return getattr(self.client, method)(
            reverse(name, args=args), data or {}, content_type="application/json"
        )

    # ------------------------------------------------------------ bookings

    def test_a_doctor_sees_their_queue_and_bookings(self):
        self.as_("doc-ro")
        self.assertEqual(self.client.get(reverse("api:appointment-waiting")).status_code, 200)
        self.assertEqual(self.client.get(reverse("api:appointment-list")).status_code, 200)

    def test_a_doctor_cannot_book_edit_or_move_the_queue(self):
        self.as_("doc-ro")
        body = {"patient": str(self.patient.uuid), "scheduled_date": timezone.now().isoformat()}
        self.assertEqual(self.send("post", "api:appointment-list", body).status_code, 403)
        detail = [self.booking.uuid]
        self.assertEqual(self.send("patch", "api:appointment-detail", {"notes": "x"}, detail).status_code, 403)
        self.assertEqual(
            self.send("post", "api:appointment-set-status", {"status": "called"}, detail).status_code, 403
        )
        self.assertEqual(
            self.send("post", "api:appointment-follow-up", {"date": "2030-01-01"}, detail).status_code, 403
        )
        with tenant_context(self.tenant):
            self.assertEqual(Appointment.all_objects.get(pk=self.booking.pk).status, "waiting")

    def test_the_desk_still_moves_the_queue(self):
        self.as_("desk-ro")
        response = self.send("post", "api:appointment-set-status", {"status": "called"}, [self.booking.uuid])
        self.assertEqual(response.status_code, 200, response.content)

    # ------------------------------------------------------------ patients

    def test_a_doctor_looks_up_patients_but_cannot_register_or_edit_one(self):
        self.as_("doc-ro")
        self.assertEqual(self.client.get(reverse("api:patient-list")).status_code, 200)
        self.assertEqual(self.send("post", "api:patient-list", {"name": "New"}).status_code, 403)
        self.assertEqual(
            self.send("patch", "api:patient-detail", {"name": "Renamed"}, [self.patient.uuid]).status_code, 403
        )
        with tenant_context(self.tenant):
            self.assertEqual(Patient.all_objects.get(pk=self.patient.pk).name, "Mona")

    # ------------------------------------------------------ treatment plans

    def test_a_doctor_edits_the_course_but_not_who_or_what_it_is_for(self):
        self.as_("doc-ro")
        url = [self.plan.uuid]
        ok = self.send("patch", "api:treatmentplan-detail", {"title": "Renamed", "planned_sessions": 6}, url)
        self.assertEqual(ok.status_code, 200, ok.content)

        for field, value in (
            ("service", str(self.other_service.uuid)),
            ("start_date", (timezone.now().date() + timedelta(days=3)).isoformat()),
        ):
            response = self.send("patch", "api:treatmentplan-detail", {field: value}, url)
            self.assertEqual(response.status_code, 400, (field, response.content))
            self.assertIn(field, response.json())

    def test_sending_the_locked_fields_unchanged_is_accepted(self):
        self.as_("doc-ro")
        body = {
            "patient": str(self.patient.uuid), "doctor": str(self.employee.uuid),
            "branch": str(self.branch.uuid), "service": str(self.service.uuid),
            "start_date": self.plan.start_date.isoformat(), "title": "Same fields",
        }
        response = self.send("patch", "api:treatmentplan-detail", body, [self.plan.uuid])
        self.assertEqual(response.status_code, 200, response.content)
