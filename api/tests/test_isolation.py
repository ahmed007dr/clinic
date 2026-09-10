"""The API's own isolation boundary.

`tenants/test_isolation.py` proves the server-rendered screens cannot leak
between clinics. None of that carries over automatically: the API is a second
front door onto the same tables, reached by a different code path, with its own
serializers, its own querysets and its own idea of who may do what. Every
boundary has to be demonstrated again here or it is merely assumed.

The user driving these requests is an **Admin** — clinic-wide within their own
tenant, so every role check passes. The only thing between them and another
clinic's records is the tenant scoping itself.
"""

import uuid as uuid_module

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from appointments.models import Appointment
from billing.models import Payment
from branches.models import Branch
from employees.models import Employee, EmployeeType
from medical.models import Visit
from patients.models import Patient
from services.models import Service
from tenants.context import tenant_context
from tenants.models import Tenant

User = get_user_model()


class ApiCrossTenantTests(TestCase):
    def setUp(self):
        self.a = Tenant.objects.first()
        self.b = Tenant.objects.create(
            name="Rival Clinic", slug="rival-api", status=Tenant.Status.ACTIVE
        )

        with tenant_context(self.a):
            role_a, _ = ClinicRole.all_objects.get_or_create(
                tenant=self.a, name="Admin"
            )
            self.branch_a = Branch.all_objects.create(
                tenant=self.a, name="A Main", code="AM"
            )
            self.patient_a = Patient.all_objects.create(
                tenant=self.a, name="A Patient", branch=self.branch_a
            )
        self.user_a = User.objects.create_user(
            username="a-admin", email="a-api@t.local", password="pass12345",
            tenant=self.a, role=role_a, branch=self.branch_a,
        )

        with tenant_context(self.b):
            self.branch_b = Branch.all_objects.create(
                tenant=self.b, name="B Main", code="BM"
            )
            self.patient_b = Patient.all_objects.create(
                tenant=self.b, name="B Patient", branch=self.branch_b
            )
            self.appointment_b = Appointment.all_objects.create(
                tenant=self.b, patient=self.patient_b,
                scheduled_date=timezone.now(), branch=self.branch_b,
            )
            self.payment_b = Payment.all_objects.create(
                tenant=self.b, appointment=self.appointment_b,
                patient=self.patient_b, receipt_number="B-1", amount=50,
                branch=self.branch_b,
            )
            self.service_b = Service.all_objects.create(
                tenant=self.b, name="B Service", base_price=10
            )
            self.visit_b = Visit.all_objects.create(
                tenant=self.b, patient=self.patient_b, branch=self.branch_b,
                diagnosis="B diagnosis",
            )

        self.client.login(email="a-api@t.local", password="pass12345")

    # ------------------------------------------------------------------ reads

    def test_lists_never_contain_another_clinics_rows(self):
        cases = [
            ("api:patient-list", self.patient_b.uuid),
            ("api:appointment-list", self.appointment_b.uuid),
            ("api:payment-list", self.payment_b.uuid),
            ("api:service-list", self.service_b.uuid),
            ("api:branch-list", self.branch_b.uuid),
            ("api:visit-list", self.visit_b.uuid),
        ]
        for name, foreign_uuid in cases:
            with self.subTest(endpoint=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                body = response.json()
                returned = {row["uuid"] for row in body["results"]}
                self.assertNotIn(str(foreign_uuid), returned)

    def test_fetching_another_clinics_record_is_a_404(self):
        cases = [
            ("api:patient-detail", self.patient_b.uuid),
            ("api:appointment-detail", self.appointment_b.uuid),
            ("api:payment-detail", self.payment_b.uuid),
            ("api:service-detail", self.service_b.uuid),
            ("api:branch-detail", self.branch_b.uuid),
            ("api:visit-detail", self.visit_b.uuid),
        ]
        for name, foreign_uuid in cases:
            with self.subTest(endpoint=name):
                response = self.client.get(reverse(name, args=[foreign_uuid]))
                self.assertEqual(
                    response.status_code, 404,
                    f"{name} returned {response.status_code} for a foreign record",
                )

    def test_a_foreign_uuid_is_indistinguishable_from_a_missing_one(self):
        """Both are 404 with the same body.

        If a real-but-foreign UUID answered differently from a random one, the
        API would confirm the existence of another clinic's records to anyone
        willing to guess.
        """
        foreign = self.client.get(
            reverse("api:patient-detail", args=[self.patient_b.uuid])
        )
        missing = self.client.get(
            reverse("api:patient-detail", args=[uuid_module.uuid4()])
        )
        self.assertEqual(foreign.status_code, missing.status_code)
        self.assertEqual(foreign.json(), missing.json())

    def test_the_patient_timeline_of_a_foreign_patient_is_a_404(self):
        response = self.client.get(
            reverse("api:patient-timeline", args=[self.patient_b.uuid])
        )
        self.assertEqual(response.status_code, 404)

    # ----------------------------------------------------------------- writes

    def test_cannot_attach_a_new_record_to_another_clinics_patient(self):
        """The sharpest edge in the whole API.

        Reads are protected by the queryset; a *write* that names a foreign
        UUID in its payload is protected only by the related field resolving
        its choices inside the tenant. This is the test that fails if
        `TenantScopedRelatedField` is ever replaced with a plain
        `SlugRelatedField(queryset=...)`.
        """
        response = self.client.post(
            reverse("api:appointment-list"),
            {
                "patient": str(self.patient_b.uuid),
                "scheduled_date": timezone.now().isoformat(),
                "price": "100.00",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("patient", response.json())
        with tenant_context(self.b):
            self.assertEqual(
                Appointment.all_objects.filter(patient=self.patient_b).count(), 1
            )

    def test_cannot_edit_another_clinics_record(self):
        response = self.client.patch(
            reverse("api:patient-detail", args=[self.patient_b.uuid]),
            {"name": "hijacked"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)
        with tenant_context(self.b):
            self.patient_b.refresh_from_db()
        self.assertEqual(self.patient_b.name, "B Patient")

    def test_cannot_delete_another_clinics_record(self):
        response = self.client.delete(
            reverse("api:patient-detail", args=[self.patient_b.uuid])
        )
        self.assertEqual(response.status_code, 404)
        with tenant_context(self.b):
            self.assertTrue(
                Patient.all_objects.filter(pk=self.patient_b.pk).exists()
            )

    def test_a_tenant_in_the_payload_is_ignored(self):
        """`tenant` is not a serializer field, so supplying it changes nothing.

        A client that guesses the field name must not be able to file a record
        under another clinic — and the record must still be created under
        their own, rather than rejected, because the field simply is not part
        of the API.
        """
        response = self.client.post(
            reverse("api:patient-list"),
            {"name": "Planted", "tenant": self.b.pk, "gender": "male"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        created = Patient.all_objects.get(uuid=response.json()["uuid"])
        self.assertEqual(created.tenant_id, self.a.pk)


class RelatedFieldFreezeTests(TestCase):
    """Regression for the trap documented in `api/relations.py`.

    `TenantManager` fails closed, so a queryset evaluated at import time is
    frozen empty and every write is rejected forever. The symptom is not a
    crash — it is a clinic reporting that nothing can be saved, with a
    validation error that says the patient does not exist while the patient is
    plainly on screen.

    Creating one record through a related field is enough to catch it, and this
    is why the field builds its queryset per request.
    """

    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            role, _ = ClinicRole.all_objects.get_or_create(
                tenant=self.tenant, name="Admin"
            )
            self.branch = Branch.all_objects.create(
                tenant=self.tenant, name="Main", code="MN"
            )
            self.patient = Patient.all_objects.create(
                tenant=self.tenant, name="Real Patient", branch=self.branch
            )
        self.user = User.objects.create_user(
            username="admin", email="freeze@t.local", password="pass12345",
            tenant=self.tenant, role=role, branch=self.branch,
        )
        self.client.login(email="freeze@t.local", password="pass12345")

    def test_a_related_field_resolves_a_real_record(self):
        response = self.client.post(
            reverse("api:appointment-list"),
            {
                "patient": str(self.patient.uuid),
                "branch": str(self.branch.uuid),
                "scheduled_date": timezone.now().isoformat(),
                "price": "150.00",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["patient_name"], "Real Patient")

    def test_the_doctor_picker_refuses_staff_who_are_not_doctors(self):
        """`limit_choices_to` constrains form dropdowns and nothing else — a
        direct API write sails past it, which is what this rejects."""
        with tenant_context(self.tenant):
            cleaner_type = EmployeeType.all_objects.create(
                tenant=self.tenant, name="Cleaner"
            )
            cleaner = Employee.all_objects.create(
                tenant=self.tenant, name="Not A Doctor", branch=self.branch,
                national_id="X1", salary_value=1, employee_type=cleaner_type,
            )
        response = self.client.post(
            reverse("api:appointment-list"),
            {
                "patient": str(self.patient.uuid),
                "doctor": str(cleaner.uuid),
                "scheduled_date": timezone.now().isoformat(),
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("doctor", response.json())
