"""A doctor sees their own patients and their own work — nobody else's.

Two doctors in one branch, each with a patient of their own. Before the
account-to-doctor link, both could read everything in the branch; these check
every kind of door that used to allow it (lists, direct detail URLs, patient
sub-records, relation fields, the dashboard) and that a doctor's records are
always signed with their own name.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from appointments.models import Appointment
from branches.models import Branch
from employees.models import Employee, EmployeeType
from medical.models import Allergy, Visit
from patients.models import Patient
from tenants.context import tenant_context
from tenants.models import Tenant

User = get_user_model()


class DoctorScopingTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            self.branch = Branch.all_objects.create(tenant=self.tenant, name="Scope", code="SC")
            self.other_branch = Branch.all_objects.create(tenant=self.tenant, name="Far", code="FR")
            doctor_type, _ = EmployeeType.all_objects.get_or_create(tenant=self.tenant, name="Doctor")
            self.roles = {
                name: ClinicRole.all_objects.get_or_create(tenant=self.tenant, name=name)[0]
                for name in ("Admin", "Doctor", "Reception")
            }

            def employee(name, national_id, branch=None):
                return Employee.all_objects.create(
                    tenant=self.tenant, name=name, employee_type=doctor_type,
                    branch=branch or self.branch, national_id=national_id, salary_value=0,
                )

            self.dr_a = employee("Dr A", "1001")
            self.dr_b = employee("Dr B", "1002")
            self.dr_far = employee("Dr Far", "1003", self.other_branch)

            self.patient_a = Patient.all_objects.create(tenant=self.tenant, name="PA", branch=self.branch)
            self.patient_b = Patient.all_objects.create(tenant=self.tenant, name="PB", branch=self.branch)
            for patient, doctor in ((self.patient_a, self.dr_a), (self.patient_b, self.dr_b)):
                Appointment.all_objects.create(
                    tenant=self.tenant, patient=patient, doctor=doctor, branch=self.branch,
                    scheduled_date=timezone.now(), price=100,
                )
            self.visit_a = Visit.all_objects.create(
                tenant=self.tenant, patient=self.patient_a, doctor=self.dr_a, branch=self.branch,
            )
            self.visit_b = Visit.all_objects.create(
                tenant=self.tenant, patient=self.patient_b, doctor=self.dr_b, branch=self.branch,
            )
            Allergy.all_objects.create(tenant=self.tenant, patient=self.patient_b, substance="Penicillin")

        self.make_user("doc-a", "Doctor", employee=self.dr_a)
        self.make_user("doc-b", "Doctor", employee=self.dr_b)
        self.make_user("doc-none", "Doctor")
        self.make_user("admin", "Admin")
        self.make_user("desk", "Reception")

    def make_user(self, name, role, employee=None):
        return User.objects.create_user(
            username=name, email=f"{name}@sc.local", password="pass12345",
            tenant=self.tenant, role=self.roles[role], branch=self.branch, employee=employee,
        )

    def login(self, name):
        self.client.logout()
        self.assertTrue(self.client.login(email=f"{name}@sc.local", password="pass12345"))

    def names(self, url_name, key="patient_name"):
        response = self.client.get(reverse(url_name))
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        rows = body["results"] if isinstance(body, dict) else body
        return {row[key] for row in rows}

    # ---------------------------------------------------------------- lists

    def test_a_doctor_lists_only_their_own(self):
        self.login("doc-a")
        self.assertEqual(self.names("api:visit-list"), {"PA"})
        self.assertEqual(self.names("api:appointment-list"), {"PA"})
        self.assertEqual(self.names("api:patient-list", key="name"), {"PA"})

    def test_management_still_sees_the_whole_branch(self):
        self.login("admin")
        self.assertEqual(self.names("api:visit-list"), {"PA", "PB"})
        self.assertEqual(self.names("api:patient-list", key="name"), {"PA", "PB"})

    def test_an_unlinked_doctor_sees_nothing(self):
        self.login("doc-none")
        self.assertEqual(self.names("api:visit-list"), set())
        self.assertEqual(self.names("api:patient-list", key="name"), set())

    # ------------------------------------------------------- direct access

    def test_a_colleagues_records_are_not_found(self):
        self.login("doc-a")
        for url in (
            reverse("api:visit-detail", args=[self.visit_b.uuid]),
            reverse("api:patient-detail", args=[self.patient_b.uuid]),
            reverse("api:patient-timeline", args=[self.patient_b.uuid]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_patient_sub_records_follow_the_patient(self):
        self.login("doc-a")
        response = self.client.get(reverse("api:allergy-list"), {"patient": str(self.patient_b.uuid)})
        body = response.json()
        rows = body["results"] if isinstance(body, dict) else body
        self.assertEqual(rows, [])

    # ------------------------------------------------------------- writing

    def plan(self, patient, **extra):
        return self.client.post(
            reverse("api:treatmentplan-list"),
            {"patient": str(patient.uuid), "title": "Laser", **extra},
            content_type="application/json",
        )

    def test_a_record_is_signed_with_the_doctors_own_name(self):
        self.login("doc-a")
        response = self.plan(self.patient_a, doctor=str(self.dr_b.uuid))
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["doctor"], str(self.dr_a.uuid))

    def test_a_doctor_cannot_write_for_a_colleagues_patient(self):
        self.login("doc-a")
        self.assertEqual(self.plan(self.patient_b).status_code, 400)

    def test_an_unlinked_doctor_cannot_write(self):
        self.login("doc-none")
        response = self.plan(self.patient_a)
        # No patient is theirs, so the patient itself is refused.
        self.assertEqual(response.status_code, 400)

    # ----------------------------------------------------------- dashboard

    def test_dashboard_counts_only_their_own(self):
        self.login("doc-a")
        data = self.client.get(reverse("api:dashboard")).json()
        self.assertEqual(data["patients"]["total"], 1)
        self.assertEqual(data["appointments"]["today"], 1)

    # ------------------------------------------------------------- session

    def test_session_says_which_doctor_you_are(self):
        self.login("doc-a")
        user = self.client.get(reverse("api:session")).json()["user"]
        self.assertEqual(user["doctor"], {"uuid": str(self.dr_a.uuid), "name": "Dr A"})
        self.assertTrue(user["permissions"]["is_doctor"])

    # --------------------------------------------------------- linking

    def link(self, **payload):
        self.login("admin")
        body = {
            "username": "new-doc", "email": "new-doc@sc.local",
            "role": str(self.roles["Doctor"].uuid), "branch": str(self.branch.uuid),
            "password": "pass12345", **payload,
        }
        return self.client.post(reverse("api:staff-list"), body, content_type="application/json")

    def test_admin_links_a_new_doctor_account(self):
        with tenant_context(self.tenant):
            free = Employee.all_objects.create(
                tenant=self.tenant, name="Dr New", employee_type=self.dr_a.employee_type,
                branch=self.branch, national_id="1009", salary_value=0,
            )
        response = self.link(employee=str(free.uuid))
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["employee_name"], "Dr New")

    def test_a_doctor_record_cannot_have_two_accounts(self):
        response = self.link(employee=str(self.dr_a.uuid))
        self.assertEqual(response.status_code, 400)
        self.assertIn("employee", response.json())

    def test_the_record_must_be_in_the_accounts_branch(self):
        response = self.link(employee=str(self.dr_far.uuid))
        self.assertEqual(response.status_code, 400)

    def test_only_doctor_accounts_are_linked(self):
        response = self.link(employee=str(self.dr_a.uuid), role=str(self.roles["Reception"].uuid))
        self.assertEqual(response.status_code, 400)
