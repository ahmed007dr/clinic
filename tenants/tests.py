from django.db.models import ProtectedError
from django.test import TestCase

from accounts.models import ClinicRole
from branches.models import Branch
from patients.models import Patient

from .models import Tenant


class DefaultTenantMigrationTests(TestCase):
    """tenants.0002 must leave exactly one usable tenant for existing data."""

    def test_default_tenant_exists(self):
        self.assertEqual(Tenant.objects.count(), 1)

    def test_default_tenant_is_active_with_a_slug(self):
        tenant = Tenant.objects.get()
        self.assertEqual(tenant.status, Tenant.Status.ACTIVE)
        self.assertTrue(tenant.slug)
        self.assertTrue(tenant.is_usable)

    def test_default_roles_are_seeded_for_the_tenant(self):
        tenant = Tenant.objects.get()
        names = set(ClinicRole.objects.filter(tenant=tenant).values_list('name', flat=True))
        self.assertEqual(names, {'Admin', 'Reception'})


class TenantOwnershipTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()

    def test_tenant_is_required_on_owned_models(self):
        with self.assertRaises(Exception):
            Branch.objects.create(name='No Tenant', code='NT')

    def test_deleting_a_tenant_with_data_is_blocked(self):
        """PROTECT, not CASCADE — offboarding must never silently drop records."""
        Patient.objects.create(tenant=self.tenant, name='Someone')
        with self.assertRaises(ProtectedError):
            self.tenant.delete()
