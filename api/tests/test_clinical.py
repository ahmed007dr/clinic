"""Clinical list behaviour that a screen depends on."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import ClinicRole
from branches.models import Branch
from medical.models import LabResult
from patients.models import Patient
from tenants.context import tenant_context
from tenants.models import Tenant

User = get_user_model()


class UnacknowledgedLabTests(TestCase):
    """The dashboard's count and the list it links to must agree.

    Found by looking at the running app: the dashboard tile said 1 and the list
    behind it showed 5, because the list also counted normal results nobody had
    clicked. A number that disagrees with its own detail view is not trusted
    twice.
    """

    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            role, _ = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name="Doctor")
            branch = Branch.all_objects.create(tenant=self.tenant, name="Main", code="MN")
            patient = Patient.all_objects.create(tenant=self.tenant, name="P", branch=branch)
            for name, flag in (("A", "normal"), ("B", "abnormal"), ("C", "critical")):
                LabResult.all_objects.create(
                    tenant=self.tenant, patient=patient, branch=branch,
                    test_name=name, flag=flag,
                )
        User.objects.create_user(
            username="doc", email="doc-lab@t.local", password="pass12345",
            tenant=self.tenant, role=role, branch=branch,
        )
        self.client.login(email="doc-lab@t.local", password="pass12345")

    def test_the_filter_lists_exactly_what_the_dashboard_counts(self):
        listed = self.client.get(reverse("api:labresult-list"), {"unacknowledged": "1"}).json()
        counted = self.client.get(reverse("api:dashboard")).json()["clinical"]["unacknowledged_labs"]
        self.assertEqual({row["test_name"] for row in listed["results"]}, {"B", "C"})
        self.assertEqual(listed["count"], counted)
