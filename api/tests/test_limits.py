"""Plan limits, enforced through the API as they are through the screens.

The server-rendered `patient_create` and `branch_create` refuse a create that
would exceed the clinic's plan. The first version of the API did not — it was a
second door around the paywall, found by reading docs/11 rather than by any
test. These pin that the two doors agree.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import ClinicRole
from branches.models import Branch
from patients.models import Patient
from subscriptions.models import Subscription
from tenants.context import tenant_context
from tenants.models import Tenant

User = get_user_model()


class PlanLimitTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            role, _ = ClinicRole.all_objects.get_or_create(
                tenant=self.tenant, name="Admin"
            )
            self.branch = Branch.all_objects.create(
                tenant=self.tenant, name="Main", code="MN"
            )
            self.subscription = Subscription.all_objects.filter(
                tenant=self.tenant, status=Subscription.Status.ACTIVE
            ).select_related("plan").first()
        User.objects.create_user(
            username="lim", email="lim@t.local", password="pass12345",
            tenant=self.tenant, role=role, branch=self.branch,
        )
        self.client.login(email="lim@t.local", password="pass12345")

    def set_limit(self, field, value):
        plan = self.subscription.plan
        setattr(plan, field, value)
        plan.save(update_fields=[field])

    def test_a_patient_over_the_plan_limit_is_refused(self):
        with tenant_context(self.tenant):
            existing = Patient.all_objects.filter(tenant=self.tenant).count()
        self.set_limit("max_patients", existing)

        response = self.client.post(
            reverse("api:patient-list"), {"name": "One too many"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403, response.content)
        self.assertIn("باقتك", response.json()["detail"])
        with tenant_context(self.tenant):
            self.assertFalse(Patient.all_objects.filter(name="One too many").exists())

    def test_under_the_limit_it_saves(self):
        with tenant_context(self.tenant):
            existing = Patient.all_objects.filter(tenant=self.tenant).count()
        self.set_limit("max_patients", existing + 1)
        response = self.client.post(
            reverse("api:patient-list"), {"name": "Fits"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)

    def test_an_unlimited_plan_never_refuses(self):
        self.set_limit("max_patients", None)
        response = self.client.post(
            reverse("api:patient-list"), {"name": "Unlimited"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)

    def test_a_branch_over_the_plan_limit_is_refused(self):
        with tenant_context(self.tenant):
            existing = Branch.all_objects.filter(tenant=self.tenant).count()
        self.set_limit("max_branches", existing)
        response = self.client.post(
            reverse("api:branch-list"), {"name": "Extra", "code": "EX"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403, response.content)
