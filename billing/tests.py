from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from accounts.models import ClinicRole
from branches.models import Branch
from patients.models import Patient
from appointments.models import Appointment
from tenants.models import Tenant
from tenants.testing import act_as_tenant
from .models import Payment

User = get_user_model()


class BillingTestBase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()  # created by tenants.0002 data migration
        act_as_tenant(self, self.tenant)
        self.branch_a = Branch.all_objects.create(tenant=self.tenant, name='Branch A', code='A')
        self.branch_b = Branch.all_objects.create(tenant=self.tenant, name='Branch B', code='B')
        self.admin_role, _ = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name='Owner')
        self.reception_role, _ = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name='Reception')

        self.admin = User.objects.create_user(username='admin', email='admin@t.local', password='pass12345', tenant=self.tenant, role=self.admin_role, branch=self.branch_a)
        self.reception_a = User.objects.create_user(username='recA', email='reca@t.local', password='pass12345', tenant=self.tenant, role=self.reception_role, branch=self.branch_a)
        self.reception_b = User.objects.create_user(username='recB', email='recb@t.local', password='pass12345', tenant=self.tenant, role=self.reception_role, branch=self.branch_b)

        self.patient_b = Patient.all_objects.create(tenant=self.tenant, name='Patient B', branch=self.branch_b)
        self.appointment_b = Appointment.all_objects.create(tenant=self.tenant, patient=self.patient_b, scheduled_date=timezone.now(), branch=self.branch_b)
        self.payment_b = Payment.all_objects.create(
            tenant=self.tenant, appointment=self.appointment_b, patient=self.patient_b,
            receipt_number='R-B-1', amount=100, branch=self.branch_b,
        )


class FinancialReportTests(BillingTestBase):
    """Regression tests for SEC-003/H4: the financial report requires a sign-in
    and is management's alone (through the API the React app uses)."""

    def test_anonymous_user_is_refused(self):
        response = self.client.get(reverse('api:financialreport-list'))
        self.assertIn(response.status_code, (401, 403))

    def test_reception_cannot_read_the_report(self):
        self.client.login(email='reca@t.local', password='pass12345')
        self.assertEqual(self.client.get(reverse('api:financialreport-list')).status_code, 403)

    def test_the_owner_can_read_the_report(self):
        self.client.login(email='admin@t.local', password='pass12345')
        response = self.client.get(reverse('api:financialreport-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(float(response.json()['revenue']), 100.0)


class PaymentDetailScopingTests(BillingTestBase):
    """Regression tests for SEC-004: a payment must not leak across branches."""

    def test_reception_cannot_view_other_branch_payment(self):
        self.client.login(email='reca@t.local', password='pass12345')
        response = self.client.get(reverse('api:payment-detail', args=[self.payment_b.uuid]))
        self.assertNotEqual(response.status_code, 200)

    def test_reception_sees_only_the_money_of_their_open_shift(self):
        """billing.access: reception sees today's money — the payments of their
        own open shift. This payment is in no shift of theirs, even in their
        own branch."""
        self.client.login(email='recb@t.local', password='pass12345')
        response = self.client.get(reverse('api:payment-detail', args=[self.payment_b.uuid]))
        self.assertEqual(response.status_code, 404)

    def test_admin_can_view_any_branch_payment(self):
        self.client.login(email='admin@t.local', password='pass12345')
        response = self.client.get(reverse('api:payment-detail', args=[self.payment_b.uuid]))
        self.assertEqual(response.status_code, 200)


class NegativeAmountValidationTests(BillingTestBase):
    """A negative amount would silently corrupt every revenue total in the financial report."""

    def setUp(self):
        super().setUp()
        self.client.login(email='admin@t.local', password='pass12345')

    def test_a_payment_rejects_a_negative_amount(self):
        response = self.client.post(reverse('api:payment-list'), {
            'appointment': str(self.appointment_b.uuid), 'amount': '-50',
        }, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('amount', response.json())

    def test_an_expense_rejects_a_negative_amount(self):
        response = self.client.post(reverse('api:expense-list'), {
            'branch': str(self.branch_b.uuid), 'amount': '-50', 'date': str(timezone.now().date()),
        }, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('amount', response.json())
