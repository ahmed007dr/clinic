"""TEST-002 — cross-tenant isolation.

The audit that started this work found five places where a forgotten
`.filter(branch=…)` leaked data between branches. These tests assert the
equivalent mistake cannot leak between *tenants*, because the scoping no
longer depends on any individual view remembering to ask for it.

The user driving these requests is an Admin — org-wide within their own
tenant, so every role check passes. The only thing standing between them and
another clinic's records is the tenant scoping itself.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from appointments.models import Appointment
from billing.models import Payment
from branches.models import Branch
from employees.models import Employee
from patients.models import Patient
from services.models import Service

from .context import get_current_tenant, tenant_context
from .models import Tenant

User = get_user_model()


class CrossTenantIsolationTests(TestCase):
    def setUp(self):
        self.a = Tenant.objects.first()
        self.b = Tenant.objects.create(name='Rival Clinic', slug='rival-clinic', status=Tenant.Status.ACTIVE)

        role_a, _ = ClinicRole.all_objects.get_or_create(tenant=self.a, name='Admin')
        branch_a = Branch.all_objects.create(tenant=self.a, name='A Main', code='AM')
        self.user_a = User.objects.create_user(
            username='a-admin', email='aadmin@t.local', password='pass12345',
            tenant=self.a, role=role_a, branch=branch_a,
        )

        # Everything below belongs to tenant B and must stay unreachable.
        self.branch_b = Branch.all_objects.create(tenant=self.b, name='B Main', code='BM')
        self.patient_b = Patient.all_objects.create(tenant=self.b, name='B Patient', branch=self.branch_b)
        self.appointment_b = Appointment.all_objects.create(
            tenant=self.b, patient=self.patient_b,
            scheduled_date=timezone.now(), branch=self.branch_b,
        )
        self.payment_b = Payment.all_objects.create(
            tenant=self.b, appointment=self.appointment_b, patient=self.patient_b,
            receipt_number='B-1', amount=50, branch=self.branch_b,
        )
        self.employee_b = Employee.all_objects.create(
            tenant=self.b, name='B Doctor', branch=self.branch_b,
            national_id='B123456', salary_value=1000,
        )
        self.service_b = Service.all_objects.create(tenant=self.b, name='B Service', base_price=10)

        self.client.login(email='aadmin@t.local', password='pass12345')

    def foreign_urls(self):
        return [
            reverse('patients:patient_detail', args=[self.patient_b.uuid]),
            reverse('patients:patient_update', args=[self.patient_b.uuid]),
            reverse('patients:patient_delete', args=[self.patient_b.uuid]),
            reverse('appointments:appointment_detail', args=[self.appointment_b.uuid]),
            reverse('appointments:appointment_update', args=[self.appointment_b.uuid]),
            reverse('appointments:appointment_delete', args=[self.appointment_b.uuid]),
            reverse('billing:payment_detail', args=[self.payment_b.uuid]),
            reverse('billing:payment_update', args=[self.payment_b.uuid]),
            reverse('billing:payment_delete', args=[self.payment_b.uuid]),
            reverse('employees:employee_update', args=[self.employee_b.uuid]),
            reverse('employees:employee_delete', args=[self.employee_b.uuid]),
            reverse('branches:branch_update', args=[self.branch_b.uuid]),
            reverse('branches:branch_delete', args=[self.branch_b.uuid]),
            reverse('services:service_update', args=[self.service_b.uuid]),
            reverse('services:service_delete', args=[self.service_b.uuid]),
        ]

    def test_reading_another_tenants_records_returns_404(self):
        for url in self.foreign_urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_writing_to_another_tenants_records_returns_404(self):
        for url in self.foreign_urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url, {}).status_code, 404)

    def test_deleting_another_tenants_patient_leaves_it_intact(self):
        self.client.post(reverse('patients:patient_delete', args=[self.patient_b.uuid]), {})
        self.assertTrue(Patient.all_objects.filter(pk=self.patient_b.pk).exists())

    def test_list_views_do_not_include_another_tenants_rows(self):
        response = self.client.get(reverse('patients:patient_list'))
        self.assertNotContains(response, 'B Patient')

    def test_service_list_does_not_include_another_tenants_services(self):
        response = self.client.get(reverse('services:service_list'))
        self.assertNotContains(response, 'B Service')


class FormChoiceTests(TestCase):
    """Regression: ModelChoiceField querysets are built when the form class is
    imported, so the tenant-scoped manager resolved with no tenant in context
    and baked in .none(). Every dropdown on every form was empty — nobody could
    create an appointment, payment or employee — and it was invisible because
    the tests that touched forms only ever asserted they were *invalid*."""

    def setUp(self):
        self.a = Tenant.objects.first()
        self.b = Tenant.objects.create(name='Rival', slug='rival', status=Tenant.Status.ACTIVE)
        role, _ = ClinicRole.all_objects.get_or_create(tenant=self.a, name='Admin')
        self.branch = Branch.all_objects.create(tenant=self.a, name='Main', code='MN')
        Branch.all_objects.create(tenant=self.b, name='Theirs', code='TH')
        Patient.all_objects.create(tenant=self.a, name='Ours', branch=self.branch)
        Patient.all_objects.create(tenant=self.b, name='Theirs', branch=None)
        User.objects.create_user(
            username='admin', email='admin@t.local', password='pass12345',
            tenant=self.a, role=role, branch=self.branch,
        )
        self.client.login(email='admin@t.local', password='pass12345')

    def test_appointment_form_offers_this_tenants_records(self):
        form = self.client.get(reverse('appointments:appointment_create')).context['form']
        self.assertEqual(form.fields['patient'].queryset.count(), 1)
        self.assertEqual(form.fields['branch'].queryset.count(), 1)

    def test_form_choices_exclude_other_tenants(self):
        form = self.client.get(reverse('appointments:appointment_create')).context['form']
        self.assertNotIn('Theirs', [str(p) for p in form.fields['patient'].queryset])
        self.assertNotIn('Theirs', [str(b) for b in form.fields['branch'].queryset])

    def test_payment_form_offers_choices(self):
        form = self.client.get(reverse('billing:payment_create')).context['form']
        self.assertEqual(form.fields['patient'].queryset.count(), 1)

    def test_limit_choices_to_is_preserved(self):
        """Appointment.doctor restricts to the Doctor employee type — rebinding
        the queryset must not drop that filter."""
        form = self.client.get(reverse('appointments:appointment_create')).context['form']
        self.assertIn('employee_type', str(form.fields['doctor'].queryset.query))


class ManagerScopingTests(TestCase):
    """The manager is the layer that makes the above hold, so pin its
    behaviour directly — including that absence of context yields nothing."""

    def setUp(self):
        self.a = Tenant.objects.first()
        self.b = Tenant.objects.create(name='Rival Clinic', slug='rival-clinic', status=Tenant.Status.ACTIVE)
        Patient.all_objects.create(tenant=self.a, name='A Patient')
        Patient.all_objects.create(tenant=self.b, name='B Patient')

    def test_no_tenant_in_context_returns_nothing(self):
        """Fails closed. Returning everything here would be the dangerous default."""
        self.assertIsNone(get_current_tenant())
        self.assertEqual(Patient.objects.count(), 0)

    def test_context_scopes_reads_to_that_tenant(self):
        with tenant_context(self.a):
            self.assertEqual([p.name for p in Patient.objects.all()], ['A Patient'])
        with tenant_context(self.b):
            self.assertEqual([p.name for p in Patient.objects.all()], ['B Patient'])

    def test_all_objects_is_the_deliberate_way_across_tenants(self):
        self.assertEqual(Patient.all_objects.count(), 2)

    def test_context_does_not_leak_out_of_its_block(self):
        with tenant_context(self.a):
            pass
        self.assertIsNone(get_current_tenant())

    def test_foreign_key_traversal_still_works_without_context(self):
        """base_manager_name keeps _base_manager unfiltered; if it were
        scoped, following a FK with no tenant in context would blow up."""
        payment_branch = Branch.all_objects.create(tenant=self.a, name='FK Branch', code='FK')
        patient = Patient.all_objects.create(tenant=self.a, name='FK Patient', branch=payment_branch)
        fetched = Patient.all_objects.get(pk=patient.pk)
        self.assertEqual(fetched.branch.name, 'FK Branch')
