from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from accounts.models import ClinicRole
from tenants.models import Tenant
from tenants.testing import act_as_tenant
from .models import Branch

User = get_user_model()


class BranchAuthorizationTests(TestCase):
    """Regression tests for SEC-005: branch management must be Admin-only."""

    def setUp(self):
        self.tenant = Tenant.objects.first()  # created by tenants.0002 data migration
        act_as_tenant(self, self.tenant)
        self.branch_a = Branch.all_objects.create(tenant=self.tenant, name='Branch A', code='A')
        self.admin_role, _ = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name='Owner')
        self.reception_role, _ = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name='Reception')

        self.admin = User.objects.create_user(username='admin', email='admin@t.local', password='pass12345', tenant=self.tenant, role=self.admin_role, branch=self.branch_a)
        self.reception = User.objects.create_user(username='rec', email='rec@t.local', password='pass12345', tenant=self.tenant, role=self.reception_role, branch=self.branch_a)

    def post_branch(self, name):
        return self.client.post(
            reverse('api:branch-list'), {'name': name, 'code': name[:3].upper()}, content_type='application/json'
        )

    def test_reception_cannot_create_a_branch(self):
        self.client.login(email='rec@t.local', password='pass12345')
        self.assertEqual(self.post_branch('Nope').status_code, 403)

    def test_admin_can_create_a_branch(self):
        self.client.login(email='admin@t.local', password='pass12345')
        response = self.post_branch('Extra')
        self.assertEqual(response.status_code, 201, response.content)

    def test_reception_cannot_change_a_branch(self):
        self.client.login(email='rec@t.local', password='pass12345')
        response = self.client.patch(
            reverse('api:branch-detail', args=[self.branch_a.uuid]), {'name': 'Hacked'}, content_type='application/json'
        )
        self.assertEqual(response.status_code, 403)
        self.branch_a.refresh_from_db()
        self.assertEqual(self.branch_a.name, 'Branch A')

    def test_reception_cannot_delete_a_branch(self):
        self.client.login(email='rec@t.local', password='pass12345')
        response = self.client.delete(reverse('api:branch-detail', args=[self.branch_a.uuid]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Branch.all_objects.filter(pk=self.branch_a.pk).exists())

    def test_reception_can_still_list_branches(self):
        self.client.login(email='rec@t.local', password='pass12345')
        response = self.client.get(reverse('api:branch-list'))
        self.assertEqual(response.status_code, 200)
