from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from accounts.models import ClinicRole
from branches.models import Branch
from tenants.models import Tenant
from .models import Patient

User = get_user_model()


class PatientBranchScopingTests(TestCase):
    """Regression tests for SEC-004: patient_detail must not leak cross-branch patients."""

    def setUp(self):
        self.tenant = Tenant.objects.first()  # created by tenants.0002 data migration
        self.branch_a = Branch.all_objects.create(tenant=self.tenant, name='Branch A', code='A')
        self.branch_b = Branch.all_objects.create(tenant=self.tenant, name='Branch B', code='B')
        self.admin_role, _ = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name='Admin')
        self.reception_role, _ = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name='Reception')

        self.admin = User.objects.create_user(username='admin', email='admin@t.local', password='pass12345', tenant=self.tenant, role=self.admin_role, branch=self.branch_a)
        self.reception_a = User.objects.create_user(username='recA', email='reca@t.local', password='pass12345', tenant=self.tenant, role=self.reception_role, branch=self.branch_a)
        self.reception_b = User.objects.create_user(username='recB', email='recb@t.local', password='pass12345', tenant=self.tenant, role=self.reception_role, branch=self.branch_b)

        self.patient_b = Patient.all_objects.create(tenant=self.tenant, name='Patient B', branch=self.branch_b)

    def test_reception_cannot_view_other_branch_patient(self):
        self.client.login(email='reca@t.local', password='pass12345')
        response = self.client.get(reverse('patients:patient_detail', args=[self.patient_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_reception_can_view_own_branch_patient(self):
        self.client.login(email='recb@t.local', password='pass12345')
        response = self.client.get(reverse('patients:patient_detail', args=[self.patient_b.pk]))
        self.assertEqual(response.status_code, 200)

    def test_admin_can_view_any_branch_patient(self):
        self.client.login(email='admin@t.local', password='pass12345')
        response = self.client.get(reverse('patients:patient_detail', args=[self.patient_b.pk]))
        self.assertEqual(response.status_code, 200)
