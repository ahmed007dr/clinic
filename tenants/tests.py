from datetime import date

from django.db.models import ProtectedError
from django.test import TestCase
from django.utils import timezone

from accounts.models import ClinicRole
from branches.models import Branch
from patients.models import Patient
from services.models import Service

from .models import SerialCounter, Tenant


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
        names = set(ClinicRole.all_objects.filter(tenant=tenant).values_list('name', flat=True))
        self.assertEqual(names, {'Admin', 'Reception', 'Doctor'})


class TenantOwnershipTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()

    def test_tenant_is_required_on_owned_models(self):
        with self.assertRaises(Exception):
            Branch.all_objects.create(name='No Tenant', code='NT')

    def test_deleting_a_tenant_with_data_is_blocked(self):
        """PROTECT, not CASCADE — offboarding must never silently drop records."""
        Patient.all_objects.create(tenant=self.tenant, name='Someone')
        with self.assertRaises(ProtectedError):
            self.tenant.delete()


class PerTenantUniquenessTests(TestCase):
    """TENANT-003: global unique constraints let one tenant probe another's
    data by watching which values were rejected as duplicates."""

    def setUp(self):
        self.a = Tenant.objects.first()
        self.b = Tenant.objects.create(name='Second Clinic', slug='second-clinic', status=Tenant.Status.ACTIVE)

    def test_two_tenants_can_reuse_a_branch_name_and_code(self):
        Branch.all_objects.create(tenant=self.a, name='Main', code='MAIN')
        Branch.all_objects.create(tenant=self.b, name='Main', code='MAIN')
        self.assertEqual(Branch.all_objects.filter(name='Main').count(), 2)

    def test_two_tenants_can_reuse_a_service_name(self):
        Service.all_objects.create(tenant=self.a, name='Consultation', base_price=100)
        Service.all_objects.create(tenant=self.b, name='Consultation', base_price=250)
        self.assertEqual(Service.all_objects.filter(name='Consultation').count(), 2)

    def test_two_tenants_can_hold_the_same_role_names(self):
        ClinicRole.all_objects.get_or_create(tenant=self.a, name='Admin')
        ClinicRole.all_objects.get_or_create(tenant=self.b, name='Admin')
        self.assertEqual(ClinicRole.all_objects.filter(name='Admin').count(), 2)

    def test_duplicate_within_one_tenant_is_still_rejected(self):
        Branch.all_objects.create(tenant=self.a, name='Clinic X', code='CX')
        with self.assertRaises(Exception):
            Branch.all_objects.create(tenant=self.a, name='Clinic X', code='CX2')


class SerialNumberTests(TestCase):
    """TENANT-004: serials were counted across the whole table, so one
    tenant's ticket numbers disclosed another's daily volume."""

    def setUp(self):
        self.a = Tenant.objects.first()
        self.b = Tenant.objects.create(name='Second Clinic', slug='second-clinic', status=Tenant.Status.ACTIVE)

    def test_each_tenant_starts_its_own_day_at_001(self):
        first_a = Patient.all_objects.create(tenant=self.a, name='A1')
        Patient.all_objects.create(tenant=self.a, name='A2')
        first_b = Patient.all_objects.create(tenant=self.b, name='B1')

        today = timezone.now().date().strftime('%Y%m%d')
        self.assertEqual(first_a.serial_number, f'{today}-001')
        # Tenant B is unaffected by the two patients Tenant A just registered.
        self.assertEqual(first_b.serial_number, f'{today}-001')

    def test_serials_increment_within_a_tenant(self):
        serials = [Patient.all_objects.create(tenant=self.a, name=f'P{i}').serial_number for i in range(3)]
        today = timezone.now().date().strftime('%Y%m%d')
        self.assertEqual(serials, [f'{today}-001', f'{today}-002', f'{today}-003'])

    def test_counter_resumes_from_a_seeded_value(self):
        """Mirrors what the 0004 migration does for pre-existing rows."""
        day = date(2026, 1, 15)
        SerialCounter.objects.create(tenant=self.a, scope='patient', date=day, last_value=7)
        self.assertEqual(SerialCounter.next_serial(self.a.id, 'patient', day), '20260115-008')

    def test_counters_are_independent_per_tenant_and_scope(self):
        day = date(2026, 1, 15)
        SerialCounter.next_serial(self.a.id, 'patient', day)
        self.assertEqual(SerialCounter.next_serial(self.b.id, 'patient', day), '20260115-001')
        self.assertEqual(SerialCounter.next_serial(self.a.id, 'employee', day), '20260115-001')
