"""A clinical record's visit must be its own patient's visit.

Nothing in the schema ties the two together, so without the check a
prescription for one patient could be filed under another patient's visit and
appear in the wrong person's history.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import ClinicRole
from branches.models import Branch
from medical.models import Prescription, Visit
from patients.models import Patient
from tenants.context import tenant_context
from tenants.models import Tenant

User = get_user_model()


class VisitConsistencyTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            role, _ = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name="Doctor")
            branch = Branch.all_objects.create(tenant=self.tenant, name="Main", code="MN")
            self.alice = Patient.all_objects.create(tenant=self.tenant, name="Alice", branch=branch)
            self.bob = Patient.all_objects.create(tenant=self.tenant, name="Bob", branch=branch)
            self.bobs_visit = Visit.all_objects.create(tenant=self.tenant, patient=self.bob, branch=branch)
            self.alices_visit = Visit.all_objects.create(tenant=self.tenant, patient=self.alice, branch=branch)
        User.objects.create_user(
            username="doc", email="doc-vc@t.local", password="pass12345",
            tenant=self.tenant, role=role, branch=branch,
        )
        self.client.login(email="doc-vc@t.local", password="pass12345")

    def prescribe(self, visit):
        return self.client.post(reverse("api:prescription-list"), {
            "patient": str(self.alice.uuid), "visit": str(visit.uuid),
            "items": [{"medication": "Paracetamol"}],
        }, content_type="application/json")

    def test_another_patients_visit_is_refused(self):
        response = self.prescribe(self.bobs_visit)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("visit", response.json())
        self.assertEqual(Prescription.all_objects.filter(patient=self.alice).count(), 0)

    def test_the_patients_own_visit_is_accepted(self):
        self.assertEqual(self.prescribe(self.alices_visit).status_code, 201)

    def test_a_prescription_without_a_visit_is_a_400_not_a_500(self):
        """The database requires the visit; the API used to call it optional
        and crash on the INSERT."""
        response = self.client.post(reverse("api:prescription-list"), {
            "patient": str(self.alice.uuid), "items": [{"medication": "Paracetamol"}],
        }, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("visit", response.json())
