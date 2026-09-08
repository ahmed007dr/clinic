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
from .forms import PaymentForm, ExpenseForm

User = get_user_model()


class BillingTestBase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()  # created by tenants.0002 data migration
        act_as_tenant(self, self.tenant)
        self.branch_a = Branch.all_objects.create(tenant=self.tenant, name='Branch A', code='A')
        self.branch_b = Branch.all_objects.create(tenant=self.tenant, name='Branch B', code='B')
        self.admin_role, _ = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name='Admin')
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
    """Regression tests for SEC-003/H4: financial_report must require login and not crash on search."""

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse('billing:financial_report'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_doctor_revenue_search_does_not_crash(self):
        self.client.login(email='admin@t.local', password='pass12345')
        response = self.client.get(reverse('billing:financial_report'), {'doctor_revenue_search': 'x'})
        self.assertEqual(response.status_code, 200)

    def test_non_employee_search_does_not_crash(self):
        self.client.login(email='admin@t.local', password='pass12345')
        response = self.client.get(reverse('billing:financial_report'), {'non_employee_search': 'x'})
        self.assertEqual(response.status_code, 200)


class PaymentDetailScopingTests(BillingTestBase):
    """Regression tests for SEC-004: payment_detail must not leak cross-branch payments."""

    def test_reception_cannot_view_other_branch_payment(self):
        self.client.login(email='reca@t.local', password='pass12345')
        response = self.client.get(reverse('billing:payment_detail', args=[self.payment_b.uuid]))
        self.assertEqual(response.status_code, 404)

    def test_reception_can_view_own_branch_payment(self):
        self.client.login(email='recb@t.local', password='pass12345')
        response = self.client.get(reverse('billing:payment_detail', args=[self.payment_b.uuid]))
        self.assertEqual(response.status_code, 200)

    def test_admin_can_view_any_branch_payment(self):
        self.client.login(email='admin@t.local', password='pass12345')
        response = self.client.get(reverse('billing:payment_detail', args=[self.payment_b.uuid]))
        self.assertEqual(response.status_code, 200)


class NegativeAmountValidationTests(BillingTestBase):
    """A negative amount would silently corrupt every revenue total in financial_report."""

    def test_payment_form_rejects_negative_amount(self):
        form = PaymentForm(data={
            'appointment': self.appointment_b.pk,
            'patient': self.patient_b.pk,
            'receipt_number': 'R-NEG-1',
            'amount': '-50',
            'branch': self.branch_b.pk,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('amount', form.errors)

    def test_expense_form_rejects_negative_amount(self):
        form = ExpenseForm(data={
            'branch': self.branch_b.pk,
            'amount': '-50',
            'date': timezone.now().date(),
        })
        self.assertFalse(form.is_valid())
        self.assertIn('amount', form.errors)
