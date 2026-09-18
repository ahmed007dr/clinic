from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from accounts.models import ClinicRole
from branches.models import Branch
from tenants.models import Tenant
from tenants.testing import act_as_tenant

User = get_user_model()


class ServiceAuthorizationTests(TestCase):
    """Regression tests for BE-002: service management must use the same
    role-based authorization as every other app, not is_superuser."""

    def setUp(self):
        self.tenant = Tenant.objects.first()  # created by tenants.0002 data migration
        act_as_tenant(self, self.tenant)
        self.branch = Branch.all_objects.create(tenant=self.tenant, name='Branch A', code='A')
        self.admin_role, _ = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name='Admin')
        self.reception_role, _ = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name='Reception')

        # role='Admin' but NOT a Django is_superuser — this is the case that
        # was broken before BE-002 (previously blocked by the is_superuser check).
        self.branch_admin = User.objects.create_user(username='admin', email='admin@t.local', password='pass12345', tenant=self.tenant, role=self.admin_role, branch=self.branch)
        self.reception = User.objects.create_user(username='rec', email='rec@t.local', password='pass12345', tenant=self.tenant, role=self.reception_role, branch=self.branch)

    def create(self, name='Consultation', price='100'):
        return self.client.post(
            reverse('api:service-list'), {'name': name, 'base_price': price}, content_type='application/json'
        )

    def test_role_admin_without_superuser_can_create_service(self):
        self.client.login(email='admin@t.local', password='pass12345')
        self.assertEqual(self.create().status_code, 201)

    def test_reception_cannot_create_service(self):
        self.client.login(email='rec@t.local', password='pass12345')
        self.assertEqual(self.create().status_code, 403)

    def test_reception_can_still_read_the_service_list(self):
        self.client.login(email='rec@t.local', password='pass12345')
        self.assertEqual(self.client.get(reverse('api:service-list')).status_code, 200)


class ServicePriceValidationTests(TestCase):
    """A negative base_price would silently corrupt pricing/reporting downstream."""

    def setUp(self):
        self.tenant = Tenant.objects.first()
        act_as_tenant(self, self.tenant)
        role, _ = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name='Admin')
        branch = Branch.all_objects.create(tenant=self.tenant, name='Branch A', code='A')
        User.objects.create_user(username='admin', email='admin@t.local', password='pass12345',
                                 tenant=self.tenant, role=role, branch=branch)
        self.client.login(email='admin@t.local', password='pass12345')

    def test_a_negative_base_price_is_rejected(self):
        response = self.client.post(
            reverse('api:service-list'), {'name': 'Consultation', 'base_price': '-10'}, content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('base_price', response.json())
