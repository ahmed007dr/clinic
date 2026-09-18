from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from accounts.models import ClinicRole
from branches.models import Branch
from tenants.models import Tenant
from tenants.testing import act_as_tenant
from .models import AuditLog

User = get_user_model()


class AuditLogAccessTests(TestCase):
    """Regression tests for SEC-007: the audit log must be Admin-only."""

    def setUp(self):
        self.tenant = Tenant.objects.first()  # created by tenants.0002 data migration
        act_as_tenant(self, self.tenant)
        self.branch = Branch.all_objects.create(tenant=self.tenant, name='Branch A', code='A')
        self.admin_role, _ = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name='Owner')
        self.reception_role, _ = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name='Reception')

        self.admin = User.objects.create_user(username='admin', email='admin@t.local', password='pass12345', tenant=self.tenant, role=self.admin_role, branch=self.branch)
        self.reception = User.objects.create_user(username='rec', email='rec@t.local', password='pass12345', tenant=self.tenant, role=self.reception_role, branch=self.branch)

    def test_reception_cannot_view_audit_log(self):
        self.client.login(email='rec@t.local', password='pass12345')
        response = self.client.get(reverse('audit:audit_list'))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_view_audit_log(self):
        self.client.login(email='admin@t.local', password='pass12345')
        response = self.client.get(reverse('audit:audit_list'))
        self.assertEqual(response.status_code, 200)


class LoginLogoutAuditTests(TestCase):
    """Regression tests for SEC-008: login/logout must actually be audited."""

    def setUp(self):
        self.tenant = Tenant.objects.first()  # created by tenants.0002 data migration
        act_as_tenant(self, self.tenant)
        self.branch = Branch.all_objects.create(tenant=self.tenant, name='Branch A', code='A')
        self.admin_role, _ = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name='Admin')
        self.user = User.objects.create_user(username='admin', email='admin@t.local', password='pass12345', tenant=self.tenant, role=self.admin_role, branch=self.branch)

    def test_login_creates_audit_log_entry(self):
        response = self.client.post(
            reverse('api:login'), {'email': 'admin@t.local', 'password': 'pass12345'}, content_type='application/json'
        )
        self.assertEqual(response.status_code, 200, response.content)
        entry = AuditLog.objects.get(user=self.user, action='login')
        self.assertEqual(entry.tenant_id, self.tenant.pk)

    def test_a_failed_login_is_not_recorded_as_a_login(self):
        self.client.post(
            reverse('api:login'), {'email': 'admin@t.local', 'password': 'wrong-password'}, content_type='application/json'
        )
        self.assertFalse(AuditLog.objects.filter(action='login').exists())

    def test_logout_creates_audit_log_entry(self):
        self.client.login(email='admin@t.local', password='pass12345')
        self.client.post(reverse('api:logout'))
        self.assertTrue(AuditLog.objects.filter(user=self.user, action='logout').exists())

    def test_logging_out_when_not_signed_in_records_nothing(self):
        self.client.post(reverse('api:logout'))
        self.assertFalse(AuditLog.objects.filter(action='logout').exists())
