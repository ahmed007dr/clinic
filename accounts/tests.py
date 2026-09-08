from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from employees.models import EmployeeType
from patients.models import Patient
from tenants.context import tenant_context
from tenants.models import Tenant
from tenants.provisioning import create_tenant, provision_tenant_defaults

from .models import ClinicRole

User = get_user_model()


class EmailLoginTests(TestCase):
    """SEC-009: email is the credential, because it is the one identifier that
    stays unique platform-wide once usernames repeat between clinics."""

    def setUp(self):
        self.tenant = Tenant.objects.first()
        # tenant_context, not bare all_objects: under PostgreSQL RLS a row can
        # only be written by a connection that has declared which tenant it is
        # acting for. Production does this in middleware; tests must be explicit.
        with tenant_context(self.tenant):
            self.role, _ = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name='Admin')
        self.user = User.objects.create_user(
            username='admin', email='doctor@clinic.test', password='pass12345',
            tenant=self.tenant, role=self.role,
        )

    def test_login_succeeds_with_email(self):
        response = self.client.post(
            reverse('accounts:login'),
            {'username': 'doctor@clinic.test', 'password': 'pass12345'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('_auth_user_id', self.client.session)

    def test_login_with_the_old_username_no_longer_works(self):
        response = self.client.post(
            reverse('accounts:login'),
            {'username': 'admin', 'password': 'pass12345'},
        )
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertEqual(response.status_code, 200)  # re-renders with an error

    def test_email_must_be_unique_platform_wide(self):
        other = Tenant.objects.create(name='Other', slug='other', status=Tenant.Status.ACTIVE)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user(
                    username='someone', email='doctor@clinic.test',
                    password='pass12345', tenant=other,
                )


class UsernameScopingTests(TestCase):
    """The whole reason for moving to email: two clinics both wanting
    a 'reception' account."""

    def setUp(self):
        self.a = Tenant.objects.first()
        self.b = Tenant.objects.create(name='Other', slug='other', status=Tenant.Status.ACTIVE)

    def test_two_tenants_can_each_have_a_reception_account(self):
        User.objects.create_user(username='reception', email='r@a.test', password='pass12345', tenant=self.a)
        User.objects.create_user(username='reception', email='r@b.test', password='pass12345', tenant=self.b)
        self.assertEqual(User.objects.filter(username='reception').count(), 2)

    def test_username_still_cannot_repeat_inside_one_tenant(self):
        User.objects.create_user(username='reception', email='r1@a.test', password='pass12345', tenant=self.a)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user(username='reception', email='r2@a.test', password='pass12345', tenant=self.a)


class PlatformStaffTests(TestCase):
    """Platform staff span tenants, so they carry none — and get no implicit
    access as a result. Reaching across tenants stays an explicit act."""

    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            Patient.all_objects.create(tenant=self.tenant, name='Someone')
        self.operator = User.objects.create_user(
            username='operator', email='ops@platform.test', password='pass12345',
            tenant=None, is_platform_staff=True,
        )

    def test_platform_staff_have_no_tenant(self):
        self.assertTrue(self.operator.is_platform_staff)
        self.assertIsNone(self.operator.tenant)

    def test_platform_staff_get_no_implicit_data_access(self):
        self.client.login(email='ops@platform.test', password='pass12345')
        response = self.client.get(reverse('patients:patient_list'))
        # No role either, so the role gate turns them away well before scoping.
        self.assertNotEqual(response.status_code, 200)

    def test_ordinary_users_are_not_platform_staff_by_default(self):
        user = User.objects.create_user(
            username='normal', email='n@clinic.test', password='pass12345', tenant=self.tenant,
        )
        self.assertFalse(user.is_platform_staff)


class ProvisioningTests(TestCase):
    """SEC-010: seeding a tenant belongs to tenant setup, not to migrate.

    Reads here are wrapped too, not just writes: `all_objects` bypasses the
    application-layer manager but not RLS, so an unbound read returns nothing.
    """

    def test_create_tenant_seeds_roles_and_doctor_type(self):
        tenant = create_tenant('Fresh Clinic', slug='fresh-clinic')
        with tenant_context(tenant):
            roles = set(ClinicRole.all_objects.filter(tenant=tenant).values_list('name', flat=True))
            types = set(EmployeeType.all_objects.filter(tenant=tenant).values_list('name', flat=True))
        self.assertEqual(roles, {'Admin', 'Reception', 'Doctor'})
        self.assertIn('Doctor', types)

    def test_provisioning_is_idempotent(self):
        tenant = create_tenant('Fresh Clinic', slug='fresh-clinic')
        provision_tenant_defaults(tenant)
        provision_tenant_defaults(tenant)
        with tenant_context(tenant):
            self.assertEqual(ClinicRole.all_objects.filter(tenant=tenant).count(), 3)

    def test_a_new_tenant_does_not_inherit_another_tenants_roles(self):
        first = Tenant.objects.first()
        tenant = create_tenant('Fresh Clinic', slug='fresh-clinic')
        with tenant_context(first):
            first_roles = set(ClinicRole.all_objects.filter(tenant=first).values_list('id', flat=True))
        with tenant_context(tenant):
            new_roles = set(ClinicRole.all_objects.filter(tenant=tenant).values_list('id', flat=True))
        self.assertNotEqual(first_roles, new_roles)
