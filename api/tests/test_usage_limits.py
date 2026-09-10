"""WIRE-003/004/007: the limits that were defined and never enforced.

Doctors, staff and storage — through the API and through the server-rendered
screens, because a limit enforced at one door and not the other is a limit
with a documented bypass.
"""

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from accounts.models import ClinicRole
from branches.models import Branch
from employees.models import Employee, EmployeeType
from patients.models import Patient
from subscriptions.entitlements import LimitReached
from subscriptions.models import Subscription
from subscriptions.usage import check_storage, limits_table, usage_for
from tenants.context import tenant_context
from tenants.models import Tenant

User = get_user_model()


class UsageLimitTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            self.admin_role, _ = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name="Admin")
            self.reception_role, _ = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name="Reception")
            self.branch = Branch.all_objects.create(tenant=self.tenant, name="Main", code="MN")
            self.doctor_type, _ = EmployeeType.all_objects.get_or_create(tenant=self.tenant, name="Doctor")
            self.nurse_type = EmployeeType.all_objects.create(tenant=self.tenant, name="Nurse")
            self.patient = Patient.all_objects.create(tenant=self.tenant, name="P", branch=self.branch)
            self.plan = Subscription.all_objects.filter(
                tenant=self.tenant, status=Subscription.Status.ACTIVE
            ).select_related("plan").first().plan
        for plan_field in ("max_staff", "max_doctors", "max_storage_mb"):
            setattr(self.plan, plan_field, None)
        self.plan.save()
        User.objects.create_user(
            username="adm", email="adm-use@t.local", password="pass12345",
            tenant=self.tenant, role=self.admin_role, branch=self.branch,
        )
        self.client.login(email="adm-use@t.local", password="pass12345")

    def limit(self, field, value):
        setattr(self.plan, field, value)
        self.plan.save(update_fields=[field])

    def employee(self, name, employee_type):
        with tenant_context(self.tenant):
            return Employee.all_objects.create(
                tenant=self.tenant, name=name, branch=self.branch,
                national_id=name, salary_value=1, employee_type=employee_type,
            )

    def post_employee(self, name, employee_type):
        return self.client.post(reverse("api:employee-list"), {
            "name": name, "branch": str(self.branch.uuid), "national_id": name,
            "salary_value": "100.00", "employee_type": str(employee_type.uuid),
        }, content_type="application/json")

    def count(self, name):
        with tenant_context(self.tenant):
            return Employee.all_objects.filter(name=name).count()

    # ------------------------------------------------------------------- API

    def test_a_doctor_over_the_doctor_limit_is_refused(self):
        self.employee("D1", self.doctor_type)
        self.limit("max_doctors", 1)
        response = self.post_employee("D2", self.doctor_type)
        self.assertEqual(response.status_code, 403, response.content)
        self.assertIn("الأطباء", response.json()["detail"])
        self.assertEqual(self.count("D2"), 0)

    def test_the_doctor_limit_does_not_block_other_staff(self):
        self.employee("D1", self.doctor_type)
        self.limit("max_doctors", 1)
        self.assertEqual(self.post_employee("N1", self.nurse_type).status_code, 201)

    def test_the_staff_limit_counts_everyone(self):
        self.employee("N1", self.nurse_type)
        self.limit("max_staff", 1)
        response = self.post_employee("N2", self.nurse_type)
        self.assertEqual(response.status_code, 403, response.content)
        self.assertIn("الموظفون", response.json()["detail"])

    def test_moving_someone_into_the_doctor_type_is_the_same_limit(self):
        self.employee("D1", self.doctor_type)
        nurse = self.employee("N1", self.nurse_type)
        self.limit("max_doctors", 1)
        response = self.client.patch(
            reverse("api:employee-detail", args=[nurse.uuid]),
            {"employee_type": str(self.doctor_type.uuid)}, content_type="application/json",
        )
        self.assertEqual(response.status_code, 403, response.content)
        with tenant_context(self.tenant):
            nurse.refresh_from_db()
        self.assertEqual(nurse.employee_type_id, self.nurse_type.pk)

    def test_an_upload_over_the_storage_allowance_is_refused_unwritten(self):
        self.limit("max_storage_mb", 1)
        big = SimpleUploadedFile(
            "scan.pdf", b"%PDF-1.4\n" + b"0" * (1024 * 1024 + 10), content_type="application/pdf"
        )
        response = self.client.post(reverse("api:attachment-list"), {
            "title": "Scan", "patient": str(self.patient.uuid), "category": "other", "file": big,
        })
        self.assertEqual(response.status_code, 403, response.content)
        self.assertIn("مساحة التخزين", response.json()["detail"])

    def test_an_unlimited_storage_plan_never_refuses(self):
        with tenant_context(self.tenant):
            check_storage(self.tenant, 10 ** 12)  # would raise if it were limited

    def test_storage_is_checked_against_what_is_already_used(self):
        self.limit("max_storage_mb", 1)
        with tenant_context(self.tenant):
            check_storage(self.tenant, 1024)
            with self.assertRaises(LimitReached):
                check_storage(self.tenant, 2 * 1024 * 1024)

    # ------------------------------------------------------ server-rendered

    def test_the_employee_screen_enforces_the_same_limit(self):
        self.employee("N1", self.nurse_type)
        self.limit("max_staff", 1)
        response = self.client.post(reverse("employees:employee_create"), {
            "name": "N2", "branch": self.branch.pk, "national_id": "N2",
            "salary_value": "100", "hire_date": "2026-01-01",
            "employee_type": self.nurse_type.pk,
        }, follow=True)
        messages = [str(m) for m in response.context["messages"]]
        self.assertTrue(any("الموظفون" in m for m in messages), messages)
        self.assertEqual(self.count("N2"), 0)

    # ------------------------------------------------------ the clinic's page

    def test_the_clinic_sees_its_own_usage(self):
        self.employee("D1", self.doctor_type)
        response = self.client.get(reverse("api:subscription"))
        self.assertEqual(response.status_code, 200)
        rows = {row["key"]: row for row in response.json()["limits"]}
        self.assertEqual(rows["max_doctors"]["used"], 1)

    def test_the_clinic_page_and_the_owner_portal_count_the_same(self):
        """Both call subscriptions/usage.py — this asserts the two agree."""
        self.employee("D1", self.doctor_type)
        with tenant_context(self.tenant):
            portal = {row["key"]: row["used"] for row in limits_table(self.tenant, usage=usage_for(self.tenant))}
        clinic = {row["key"]: row["used"] for row in self.client.get(reverse("api:subscription")).json()["limits"]}
        self.assertEqual(portal, clinic)

    def test_features_the_system_lacks_are_never_reported_as_enabled(self):
        """A plan may grant WhatsApp; nothing sends WhatsApp. The clinic's page
        must say "coming", not "enabled" — while a feature that does exist is
        still reported from the plan."""
        features = self.plan.features or {}
        features.update({"whatsapp": True, "packages": True})
        self.plan.features = features
        self.plan.save(update_fields=["features"])

        rows = {f["key"]: f for f in self.client.get(reverse("api:subscription")).json()["features"]}
        self.assertFalse(rows["whatsapp"]["available"])
        self.assertTrue(rows["packages"]["available"])
        self.assertTrue(rows["packages"]["enabled"])

    def test_reception_cannot_see_the_subscription(self):
        User.objects.create_user(
            username="rec", email="rec-use@t.local", password="pass12345",
            tenant=self.tenant, role=self.reception_role, branch=self.branch,
        )
        self.client.login(email="rec-use@t.local", password="pass12345")
        self.assertEqual(self.client.get(reverse("api:subscription")).status_code, 403)
