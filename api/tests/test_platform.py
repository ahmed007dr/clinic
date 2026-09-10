"""The owner portal's API.

The rules are platform_admin's, unchanged: platform staff only (the flag, and
no clinic of their own — not `is_superuser`), one tenant at a time, clinical
data read-only, and every look and every change written to the clinic's own
audit trail.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import ClinicRole
from audit.models import AuditLog
from branches.models import Branch
from patients.models import Patient
from subscriptions.models import Plan, Subscription
from tenants.context import tenant_context
from tenants.models import Tenant

User = get_user_model()


class PlatformApiTests(TestCase):
    def setUp(self):
        self.clinic = Tenant.objects.first()
        with tenant_context(self.clinic):
            role, _ = ClinicRole.all_objects.get_or_create(tenant=self.clinic, name="Admin")
            branch = Branch.all_objects.create(tenant=self.clinic, name="Main", code="MN")
            Patient.all_objects.create(tenant=self.clinic, name="P", branch=branch)
        User.objects.create_user(
            username="clinic-admin", email="ca@t.local", password="pass12345",
            tenant=self.clinic, role=role, branch=branch,
        )
        User.objects.create_user(
            username="op", email="op@platform.local", password="pass12345",
            tenant=None, is_platform_staff=True,
        )

    def as_operator(self):
        self.client.login(email="op@platform.local", password="pass12345")

    def audit(self, tenant, needle):
        with tenant_context(tenant):
            return AuditLog._default_manager.filter(
                tenant=tenant, description__contains=needle
            ).count()

    # ------------------------------------------------------------------ gate

    def test_a_clinic_admin_is_refused_every_platform_endpoint(self):
        self.client.login(email="ca@t.local", password="pass12345")
        for url in (
            reverse("api:platform-tenants"),
            reverse("api:platform-plans"),
            reverse("api:platform-tenant", args=[self.clinic.uuid]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
        response = self.client.post(
            reverse("api:platform-tenant-status", args=[self.clinic.uuid]),
            {"status": "suspended"}, content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.clinic.refresh_from_db()
        self.assertNotEqual(self.clinic.status, "suspended")

    def test_a_superuser_without_the_flag_is_not_platform_staff(self):
        User.objects.create_superuser(username="su", email="su@t.local", password="pass12345")
        self.client.login(email="su@t.local", password="pass12345")
        self.assertEqual(self.client.get(reverse("api:platform-tenants")).status_code, 403)

    # ----------------------------------------------------------------- reads

    def test_the_operator_lists_clinics_with_their_counts(self):
        self.as_operator()
        body = self.client.get(reverse("api:platform-tenants")).json()
        row = next(r for r in body["results"] if r["uuid"] == str(self.clinic.uuid))
        self.assertEqual(row["patients"], 1)

    def test_opening_a_clinic_is_recorded_in_that_clinics_audit_trail(self):
        self.as_operator()
        before = self.audit(self.clinic, "[platform] inspect")
        response = self.client.get(reverse("api:platform-tenant", args=[self.clinic.uuid]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.audit(self.clinic, "[platform] inspect"), before + 1)

    # ---------------------------------------------------------------- writes

    def test_suspending_a_clinic_stops_its_signed_in_staff_immediately(self):
        clinic_client = self.client_class()
        clinic_client.login(email="ca@t.local", password="pass12345")
        self.assertEqual(clinic_client.get(reverse("api:patient-list")).status_code, 200)

        self.as_operator()
        response = self.client.post(
            reverse("api:platform-tenant-status", args=[self.clinic.uuid]),
            {"status": "suspended"}, content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.audit(self.clinic, "tenant status"), 1)

        refused = clinic_client.get(reverse("api:patient-list"))
        self.assertEqual(refused.status_code, 403)
        self.assertIn("اشتراك", refused.json()["detail"])

    def test_changing_the_plan_is_applied_and_audited(self):
        target = Plan.objects.filter(is_active=True).exclude(
            pk=Subscription.all_objects.filter(tenant=self.clinic).first().plan_id
        ).first()
        self.as_operator()
        response = self.client.post(
            reverse("api:platform-tenant-plan", args=[self.clinic.uuid]),
            {"plan": target.code}, content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["plan"]["code"], target.code)
        self.assertEqual(self.audit(self.clinic, "plan change"), 1)

    # ------------------------------------------------------------ onboarding

    def test_onboarding_creates_a_working_clinic(self):
        self.as_operator()
        response = self.client.post(reverse("api:platform-tenants"), {
            "name": "عيادة جديدة", "slug": "new-clinic", "admin_email": "boss@new.local",
        }, content_type="application/json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response["Cache-Control"], "no-store")
        body = response.json()
        tenant = Tenant.objects.get(slug="new-clinic")
        with tenant_context(tenant):
            self.assertEqual(Branch.objects.count(), 1)
            self.assertTrue(Subscription.objects.exists())
        self.assertEqual(self.audit(tenant, "onboard"), 1)

        # The password shown once actually works, and lands in the new clinic.
        newcomer = self.client_class()
        login = newcomer.post(reverse("api:login"), {
            "email": "boss@new.local", "password": body["admin_password"],
        }, content_type="application/json")
        self.assertEqual(login.status_code, 200, login.content)
        self.assertEqual(login.json()["user"]["role"], "Admin")
        self.assertEqual(login.json()["user"]["clinic"], "عيادة جديدة")

    def test_an_arabic_name_needs_an_explicit_slug(self):
        self.as_operator()
        response = self.client.post(reverse("api:platform-tenants"), {
            "name": "عيادة", "admin_email": "x@new.local",
        }, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("slug", response.json())

    def test_a_taken_email_or_slug_creates_nothing(self):
        self.as_operator()
        response = self.client.post(reverse("api:platform-tenants"), {
            "name": "Dup", "slug": self.clinic.slug, "admin_email": "ca@t.local",
        }, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()), {"slug", "admin_email"})
        self.assertEqual(Tenant.objects.filter(name="Dup").count(), 0)
