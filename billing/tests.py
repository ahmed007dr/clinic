from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from accounts.models import ClinicRole
from branches.models import Branch
from patients.models import Patient
from appointments.models import Appointment
from .models import Payment

User = get_user_model()


class BillingTestBase(TestCase):
    def setUp(self):
        self.branch_a = Branch.objects.create(name='Branch A', code='A')
        self.branch_b = Branch.objects.create(name='Branch B', code='B')
        self.admin_role = ClinicRole.objects.create(name='Admin')
        self.reception_role = ClinicRole.objects.create(name='Reception')

        self.admin = User.objects.create_user(username='admin', password='pass12345', role=self.admin_role, branch=self.branch_a)
        self.reception_a = User.objects.create_user(username='recA', password='pass12345', role=self.reception_role, branch=self.branch_a)
        self.reception_b = User.objects.create_user(username='recB', password='pass12345', role=self.reception_role, branch=self.branch_b)

        self.patient_b = Patient.objects.create(name='Patient B', branch=self.branch_b)
        self.appointment_b = Appointment.objects.create(patient=self.patient_b, scheduled_date=timezone.now(), branch=self.branch_b)
        self.payment_b = Payment.objects.create(
            appointment=self.appointment_b, patient=self.patient_b,
            receipt_number='R-B-1', amount=100, branch=self.branch_b,
        )


class FinancialReportTests(BillingTestBase):
    """Regression tests for SEC-003/H4: financial_report must require login and not crash on search."""

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse('billing:financial_report'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_doctor_revenue_search_does_not_crash(self):
        self.client.login(username='admin', password='pass12345')
        response = self.client.get(reverse('billing:financial_report'), {'doctor_revenue_search': 'x'})
        self.assertEqual(response.status_code, 200)

    def test_non_employee_search_does_not_crash(self):
        self.client.login(username='admin', password='pass12345')
        response = self.client.get(reverse('billing:financial_report'), {'non_employee_search': 'x'})
        self.assertEqual(response.status_code, 200)


class PaymentDetailScopingTests(BillingTestBase):
    """Regression tests for SEC-004: payment_detail must not leak cross-branch payments."""

    def test_reception_cannot_view_other_branch_payment(self):
        self.client.login(username='recA', password='pass12345')
        response = self.client.get(reverse('billing:payment_detail', args=[self.payment_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_reception_can_view_own_branch_payment(self):
        self.client.login(username='recB', password='pass12345')
        response = self.client.get(reverse('billing:payment_detail', args=[self.payment_b.pk]))
        self.assertEqual(response.status_code, 200)

    def test_admin_can_view_any_branch_payment(self):
        self.client.login(username='admin', password='pass12345')
        response = self.client.get(reverse('billing:payment_detail', args=[self.payment_b.pk]))
        self.assertEqual(response.status_code, 200)
