"""Visits open at check-in; who/when/where is fixed; prescriptions follow.

The group owner's rules (2026-09-11): reception registers the visit by sending
the patient in; the doctor finds them "in the room" and writes; patient,
doctor, clinic and date never change afterwards; the follow-up date is the one
thing reception sets; a prescription is dated and signed automatically, can be
copied onto the current patient, and reception prints it for signing.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from appointments.models import Appointment
from branches.models import Branch
from employees.models import Employee, EmployeeType
from medical.models import Prescription, PrescriptionItem, Visit
from patients.models import Patient
from tenants.context import tenant_context
from tenants.models import Tenant

User = get_user_model()


class CheckInTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            self.branch = Branch.all_objects.create(tenant=self.tenant, name="Room", code="RM")
            roles = {
                n: ClinicRole.all_objects.get_or_create(tenant=self.tenant, name=n)[0]
                for n in ("Admin", "Doctor", "Reception")
            }
            doctor_type, _ = EmployeeType.all_objects.get_or_create(tenant=self.tenant, name="Doctor")
            self.dr_a = Employee.all_objects.create(
                tenant=self.tenant, name="Dr A", branch=self.branch,
                employee_type=doctor_type, national_id="CI-1", salary_value=0,
            )
            self.dr_b = Employee.all_objects.create(
                tenant=self.tenant, name="Dr B", branch=self.branch,
                employee_type=doctor_type, national_id="CI-2", salary_value=0,
            )
            self.patient = Patient.all_objects.create(tenant=self.tenant, name="Sara", branch=self.branch)
            self.other = Patient.all_objects.create(tenant=self.tenant, name="Omar", branch=self.branch)
            self.booking = self.book(self.patient, self.dr_a)
        for key, role, employee in (
            ("desk", "Reception", None), ("doc-a", "Doctor", self.dr_a),
            ("doc-b", "Doctor", self.dr_b), ("admin", "Admin", None),
        ):
            User.objects.create_user(
                username=key, email=f"{key}@ci.local", password="pass12345",
                tenant=self.tenant, role=roles[role], branch=self.branch, employee=employee,
            )

    def book(self, patient, doctor):
        return Appointment.all_objects.create(
            tenant=self.tenant, patient=patient, doctor=doctor, branch=self.branch,
            scheduled_date=timezone.now(), status="waiting",
        )

    def login(self, key):
        self.client.logout()
        self.assertTrue(self.client.login(email=f"{key}@ci.local", password="pass12345"))

    def post(self, name, data=None, args=None):
        return self.client.post(reverse(name, args=args), data or {}, content_type="application/json")

    def send_in(self, booking=None):
        return self.post("api:appointment-set-status", {"status": "entered"}, args=[(booking or self.booking).uuid])

    def visit(self, booking=None):
        with tenant_context(self.tenant):
            return Visit.all_objects.filter(appointment=booking or self.booking).first()

    # ------------------------------------------------------------ check-in

    def test_sending_the_patient_in_opens_the_visit_once(self):
        self.login("desk")
        self.assertEqual(self.send_in().status_code, 200)
        visit = self.visit()
        self.assertEqual((visit.patient_id, visit.doctor_id, visit.branch_id),
                         (self.patient.pk, self.dr_a.pk, self.branch.pk))
        self.send_in()
        with tenant_context(self.tenant):
            self.assertEqual(Visit.all_objects.filter(appointment=self.booking).count(), 1)

    def test_no_check_in_without_a_doctor(self):
        with tenant_context(self.tenant):
            booking = self.book(self.other, None)
        self.login("desk")
        self.assertEqual(self.send_in(booking).status_code, 400)
        self.assertIsNone(self.visit(booking))

    def test_the_doctor_finds_the_patient_in_the_room(self):
        self.login("desk")
        self.send_in()
        self.login("doc-a")
        rows = self.client.get(reverse("api:visit-in-room")).json()
        self.assertEqual([r["patient_name"] for r in rows], ["Sara"])
        self.assertEqual(rows[0]["visit"], str(self.visit().uuid))
        self.login("doc-b")
        self.assertEqual(self.client.get(reverse("api:visit-in-room")).json(), [])

    def test_a_doctor_does_not_open_visits(self):
        self.login("doc-a")
        response = self.post("api:visit-list", {"patient": str(self.patient.uuid)})
        self.assertEqual(response.status_code, 403)

    # ------------------------------------------------------- fixed fields

    def test_who_when_and_where_cannot_be_edited(self):
        self.login("desk")
        self.send_in()
        visit = self.visit()
        opened = visit.visit_date
        self.login("doc-a")
        response = self.client.patch(
            reverse("api:visit-detail", args=[visit.uuid]),
            {"patient": str(self.other.uuid), "doctor": str(self.dr_b.uuid),
             "visit_date": "2020-01-01T10:00", "diagnosis": "Eczema"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        with tenant_context(self.tenant):
            visit.refresh_from_db()
        self.assertEqual(visit.diagnosis, "Eczema")
        self.assertEqual((visit.patient_id, visit.doctor_id), (self.patient.pk, self.dr_a.pk))
        self.assertEqual(visit.visit_date, opened)

    # ------------------------------------------------------------ follow-up

    def test_reception_sets_the_follow_up_without_the_record(self):
        self.login("desk")
        self.assertEqual(
            self.post("api:appointment-follow-up", {"date": "2026-10-01"}, args=[self.booking.uuid]).status_code,
            400,  # not sent in yet: no visit
        )
        self.send_in()
        response = self.post("api:appointment-follow-up", {"date": "2026-10-01"}, args=[self.booking.uuid])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["follow_up_date"], "2026-10-01")
        # …and still cannot read the visit itself.
        self.assertEqual(self.client.get(reverse("api:visit-detail", args=[self.visit().uuid])).status_code, 403)

    # --------------------------------------------------------- prescriptions

    def prescribe(self, visit, **extra):
        return self.post("api:prescription-list", {
            "visit": str(visit.uuid),
            "items": [{"medication": "Cetirizine", "dosage": "10mg"}],
            **extra,
        })

    def test_a_prescription_takes_its_patient_and_date_itself(self):
        self.login("desk")
        self.send_in()
        self.login("doc-a")
        response = self.prescribe(self.visit(), issued_at="2020-01-01T10:00", doctor=str(self.dr_b.uuid))
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["patient"], str(self.patient.uuid))
        self.assertEqual(body["doctor"], str(self.dr_a.uuid))
        self.assertTrue(body["issued_at"].startswith(timezone.now().date().isoformat()))

    def test_copying_an_old_prescription_onto_the_current_patient(self):
        with tenant_context(self.tenant):
            old_visit = Visit.all_objects.create(
                tenant=self.tenant, patient=self.other, doctor=self.dr_a, branch=self.branch,
            )
            old = Prescription.all_objects.create(
                tenant=self.tenant, visit=old_visit, patient=self.other, doctor=self.dr_a, notes="after meals",
            )
            PrescriptionItem.all_objects.create(tenant=self.tenant, prescription=old, medication="Amoxicillin")
        self.login("desk")
        self.send_in()
        self.login("doc-a")
        response = self.post("api:prescription-copy", {"visit": str(self.visit().uuid)}, args=[old.uuid])
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["patient_name"], "Sara")
        self.assertEqual([i["medication"] for i in body["items"]], ["Amoxicillin"])
        self.assertEqual(body["notes"], "after meals")
        self.assertNotEqual(body["uuid"], str(old.uuid))

    def test_reception_lists_and_prints_the_bookings_prescriptions(self):
        self.login("desk")
        self.send_in()
        self.login("doc-a")
        self.prescribe(self.visit())
        self.login("desk")
        rows = self.client.get(reverse("api:appointment-prescriptions", args=[self.booking.uuid])).json()
        self.assertEqual(len(rows), 1)
        self.assertNotIn("items", rows[0])
        self.assertEqual(self.client.get(rows[0]["print_url"]).status_code, 200)
