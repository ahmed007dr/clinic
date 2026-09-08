from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from accounts.models import ClinicRole
from tenants.models import Tenant
from .models import Branch

User = get_user_model()


class BranchAuthorizationTests(TestCase):
    """Regression tests for SEC-005: branch management must be Admin-only."""

    def setUp(self):
        self.tenant = Tenant.objects.first()  # created by tenants.0002 data migration
        self.branch_a = Branch.objects.create(tenant=self.tenant, name='Branch A', code='A')
        self.admin_role, _ = ClinicRole.objects.get_or_create(tenant=self.tenant, name='Admin')
        self.reception_role, _ = ClinicRole.objects.get_or_create(tenant=self.tenant, name='Reception')

        self.admin = User.objects.create_user(username='admin', password='pass12345', tenant=self.tenant, role=self.admin_role, branch=self.branch_a)
        self.reception = User.objects.create_user(username='rec', password='pass12345', tenant=self.tenant, role=self.reception_role, branch=self.branch_a)

    def test_reception_cannot_reach_branch_create(self):
        self.client.login(username='rec', password='pass12345')
        response = self.client.get(reverse('branches:branch_create'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_admin_can_reach_branch_create(self):
        self.client.login(username='admin', password='pass12345')
        response = self.client.get(reverse('branches:branch_create'))
        self.assertEqual(response.status_code, 200)

    def test_reception_cannot_reach_branch_update(self):
        self.client.login(username='rec', password='pass12345')
        response = self.client.get(reverse('branches:branch_update', args=[self.branch_a.pk]))
        self.assertEqual(response.status_code, 302)

    def test_reception_cannot_reach_branch_delete(self):
        self.client.login(username='rec', password='pass12345')
        response = self.client.get(reverse('branches:branch_delete', args=[self.branch_a.pk]))
        self.assertEqual(response.status_code, 302)

    def test_reception_can_still_list_branches(self):
        self.client.login(username='rec', password='pass12345')
        response = self.client.get(reverse('branches:branch_list'))
        self.assertEqual(response.status_code, 200)
