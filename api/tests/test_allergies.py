"""Allergies through the API, and the warning that makes them matter."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import ClinicRole
from branches.models import Branch
from medical.models import Allergy, Visit
from patients.models import Patient
from tenants.context import tenant_context
from tenants.models import Tenant

User = get_user_model()


class AllergyApiTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            roles = {
                name: ClinicRole.all_objects.get_or_create(tenant=self.tenant, name=name)[0]
                for name in ("Doctor", "Reception")
            }
            self.here = Branch.all_objects.create(tenant=self.tenant, name="Here", code="H")
            self.there = Branch.all_objects.create(tenant=self.tenant, name="There", code="T")
            self.patient = Patient.all_objects.create(tenant=self.tenant, name="P", branch=self.here)
            self.far = Patient.all_objects.create(tenant=self.tenant, name="F", branch=self.there)
            Allergy.all_objects.create(tenant=self.tenant, patient=self.far, substance="Latex")
            self.visit = Visit.all_objects.create(tenant=self.tenant, patient=self.patient, branch=self.here)
        for name, role in roles.items():
            User.objects.create_user(
                username=name.lower(), email=f"{name.lower()}-al@t.local",
                password="pass12345", tenant=self.tenant, role=role, branch=self.here,
            )

    def login(self, role):
        self.client.login(email=f"{role}-al@t.local", password="pass12345")

    def post_allergy(self, substance="Penicillin", patient=None):
        return self.client.post(
            reverse("api:allergy-list"),
            {"patient": str((patient or self.patient).uuid), "substance": substance, "severity": "severe"},
            content_type="application/json",
        )

    def test_a_doctor_records_an_allergy(self):
        self.login("doctor")
        response = self.post_allergy()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["recorded_by_name"], "doctor")

    def test_reception_cannot_read_or_write_allergies(self):
        self.login("reception")
        self.assertEqual(self.client.get(reverse("api:allergy-list")).status_code, 403)
        self.assertEqual(self.post_allergy().status_code, 403)

    def test_a_duplicate_is_a_message_not_a_500(self):
        self.login("doctor")
        self.post_allergy("Penicillin")
        response = self.post_allergy("penicillin")
        self.assertEqual(response.status_code, 400)
        self.assertIn("substance", response.json())

    def test_another_branchs_allergies_are_not_listed(self):
        self.login("doctor")
        substances = {row["substance"] for row in self.client.get(reverse("api:allergy-list")).json()}
        self.assertNotIn("Latex", substances)

    def test_a_prescription_reports_an_allergy_clash(self):
        """The whole point of recording one."""
        self.login("doctor")
        self.post_allergy("Penicillin")
        response = self.client.post(
            reverse("api:prescription-list"),
            {"patient": str(self.patient.uuid), "visit": str(self.visit.uuid), "items": [
                {"medication": "Penicillin V 500mg"}, {"medication": "Paracetamol"},
            ]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(
            response.json()["allergy_warnings"],
            [{"medication": "Penicillin V 500mg", "allergen": "Penicillin"}],
        )
