"""A doctor the Owner links to several clinics, switching between them.

Only the Owner may add clinics to a doctor; the doctor then picks which clinic
they are looking at, and every list follows that choice — within their own
patients, as always (test_doctor_scoping).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from appointments.models import Appointment
from branches.models import Branch
from employees.models import Employee, EmployeeType
from patients.models import Patient
from tenants.context import tenant_context
from tenants.models import Tenant

User = get_user_model()


class DoctorBranchTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            self.home = Branch.all_objects.create(tenant=self.tenant, name="Home", code="HM")
            self.away = Branch.all_objects.create(tenant=self.tenant, name="Away", code="AW")
            self.never = Branch.all_objects.create(tenant=self.tenant, name="Never", code="NV")
            roles = {
                name: ClinicRole.all_objects.get_or_create(tenant=self.tenant, name=name)[0]
                for name in ("Owner", "Admin", "Doctor")
            }
            doctor_type, _ = EmployeeType.all_objects.get_or_create(tenant=self.tenant, name="Doctor")
            self.doctor = Employee.all_objects.create(
                tenant=self.tenant, name="Dr Roam", branch=self.home,
                employee_type=doctor_type, national_id="R1", salary_value=0,
            )
            for branch, name in ((self.home, "At home"), (self.away, "Away one")):
                patient = Patient.all_objects.create(tenant=self.tenant, name=name, branch=branch)
                Appointment.all_objects.create(
                    tenant=self.tenant, patient=patient, doctor=self.doctor, branch=branch,
                    scheduled_date=timezone.now(),
                )
        for key, role in (("owner", "Owner"), ("admin", "Admin"), ("doc", "Doctor")):
            User.objects.create_user(
                username=key, email=f"{key}@db.local", password="pass12345",
                tenant=self.tenant, role=roles[role], branch=self.home,
                employee=self.doctor if key == "doc" else None,
            )

    def login(self, key):
        self.client.logout()
        self.assertTrue(self.client.login(email=f"{key}@db.local", password="pass12345"))

    def link_away(self, who="owner"):
        self.login(who)
        return self.client.patch(
            reverse("api:employee-detail", args=[self.doctor.uuid]),
            {"extra_branches": [str(self.away.uuid)]},
            content_type="application/json",
        )

    def patients(self):
        return {row["name"] for row in self.client.get(reverse("api:patient-list")).json()["results"]}

    def switch(self, branch):
        return self.client.post(
            reverse("api:active-branch"), {"branch": str(branch.uuid)},
            content_type="application/json",
        )

    def test_only_the_owner_links_a_doctor_to_more_clinics(self):
        self.assertEqual(self.link_away("admin").status_code, 400)
        response = self.link_away("owner")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["extra_branch_names"], ["Away"])

    def test_the_doctor_switches_and_every_list_follows(self):
        self.link_away()
        self.login("doc")
        session = self.client.get(reverse("api:session")).json()["user"]
        self.assertEqual({b["name"] for b in session["branches"]}, {"Home", "Away"})
        self.assertEqual(session["active_branch"]["name"], "Home")
        self.assertEqual(self.patients(), {"At home"})

        switched = self.switch(self.away)
        self.assertEqual(switched.status_code, 200, switched.content)
        self.assertEqual(switched.json()["user"]["active_branch"]["name"], "Away")
        self.assertEqual(self.patients(), {"Away one"})

    def test_a_clinic_not_linked_is_refused(self):
        self.link_away()
        self.login("doc")
        self.assertEqual(self.switch(self.never).status_code, 400)
        self.assertEqual(self.patients(), {"At home"})

    def test_unlinking_takes_effect_on_the_next_request(self):
        self.link_away()
        self.login("doc")
        self.switch(self.away)
        with tenant_context(self.tenant):
            self.doctor.extra_branches.clear()
        # The stale choice in the session is ignored, not honoured.
        self.assertEqual(self.patients(), {"At home"})

    def test_a_visiting_doctor_is_bookable_where_they_visit(self):
        self.link_away()
        with tenant_context(self.tenant):
            role = ClinicRole.all_objects.get(tenant=self.tenant, name="Admin")
        User.objects.create_user(
            username="awayadmin", email="awayadmin@db.local", password="pass12345",
            tenant=self.tenant, role=role, branch=self.away,
        )
        self.login("awayadmin")
        names = {row["name"] for row in self.client.get(reverse("api:doctor-list")).json()["results"]}
        self.assertIn("Dr Roam", names)
