"""Clinical records — access, isolation and retention.

The access rule is the point of these tests: Reception books, registers and
bills, but must never see a diagnosis.
"""

from django.contrib.auth import get_user_model
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from accounts.models import ClinicRole
from branches.models import Branch
from patients.models import Patient
from tenants.models import Tenant
from tenants.provisioning import provision_tenant_defaults

from .models import Allergy, Visit

User = get_user_model()


class ClinicalTestBase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        provision_tenant_defaults(self.tenant)
        self.branch = Branch.all_objects.create(tenant=self.tenant, name='Main', code='MN')

        def role(name):
            return ClinicRole.all_objects.get(tenant=self.tenant, name=name)

        def user(username, email, role_name):
            return User.objects.create_user(
                username=username, email=email, password='pass12345',
                tenant=self.tenant, role=role(role_name), branch=self.branch,
            )

        self.doctor_user = user('doc', 'doc@t.local', 'Doctor')
        self.admin_user = user('admin', 'admin@t.local', 'Admin')
        self.reception_user = user('rec', 'rec@t.local', 'Reception')

        self.patient = Patient.all_objects.create(
            tenant=self.tenant, name='Test Patient', branch=self.branch,
        )
        self.visit = Visit.all_objects.create(
            tenant=self.tenant, patient=self.patient, branch=self.branch,
            chief_complaint='صداع', diagnosis='CONFIDENTIAL DIAGNOSIS',
        )


class ClinicalAccessTests(ClinicalTestBase):
    def test_doctor_can_read_a_visit(self):
        self.client.login(email='doc@t.local', password='pass12345')
        response = self.client.get(reverse('medical:visit_detail', args=[self.visit.uuid]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'CONFIDENTIAL DIAGNOSIS')

    def test_admin_can_read_a_visit(self):
        self.client.login(email='admin@t.local', password='pass12345')
        response = self.client.get(reverse('medical:visit_detail', args=[self.visit.uuid]))
        self.assertEqual(response.status_code, 200)

    def test_reception_cannot_read_a_visit(self):
        self.client.login(email='rec@t.local', password='pass12345')
        response = self.client.get(reverse('medical:visit_detail', args=[self.visit.uuid]))
        self.assertNotEqual(response.status_code, 200)

    def test_reception_cannot_record_a_visit(self):
        self.client.login(email='rec@t.local', password='pass12345')
        response = self.client.post(
            reverse('medical:visit_create', args=[self.patient.uuid]),
            {'diagnosis': 'sneaked in', 'visit_date': '2026-09-08T10:00'},
        )
        self.assertNotEqual(response.status_code, 200)
        self.assertFalse(Visit.all_objects.filter(diagnosis='sneaked in').exists())

    def test_diagnosis_never_reaches_receptions_patient_page(self):
        """The clinical section is skipped for Reception, not merely hidden."""
        self.client.login(email='rec@t.local', password='pass12345')
        response = self.client.get(reverse('patients:patient_detail', args=[self.patient.uuid]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'CONFIDENTIAL DIAGNOSIS')
        self.assertFalse(response.context['show_clinical'])

    def test_doctor_sees_the_clinical_section_on_the_patient_page(self):
        self.client.login(email='doc@t.local', password='pass12345')
        response = self.client.get(reverse('patients:patient_detail', args=[self.patient.uuid]))
        self.assertTrue(response.context['show_clinical'])
        self.assertContains(response, self.visit.serial_number)

    def test_a_user_with_no_role_gets_nothing(self):
        User.objects.create_user(
            username='norole', email='norole@t.local', password='pass12345',
            tenant=self.tenant, branch=self.branch,
        )
        self.client.login(email='norole@t.local', password='pass12345')
        response = self.client.get(reverse('medical:visit_detail', args=[self.visit.uuid]))
        self.assertNotEqual(response.status_code, 200)


class ClinicalRecordingTests(ClinicalTestBase):
    def test_doctor_can_record_a_visit_and_it_gets_a_serial(self):
        self.client.login(email='doc@t.local', password='pass12345')
        response = self.client.post(
            reverse('medical:visit_create', args=[self.patient.uuid]),
            {'visit_date': '2026-09-08T10:00', 'diagnosis': 'Eczema', 'branch': self.branch.pk},
        )
        self.assertEqual(response.status_code, 302)
        visit = Visit.all_objects.get(diagnosis='Eczema')
        self.assertEqual(visit.tenant, self.tenant)
        self.assertEqual(visit.created_by, self.doctor_user)
        self.assertTrue(visit.serial_number)

    def test_allergies_are_recorded_once_per_substance(self):
        Allergy.all_objects.create(tenant=self.tenant, patient=self.patient, substance='Penicillin')
        self.client.login(email='doc@t.local', password='pass12345')
        self.client.post(
            reverse('medical:allergy_create', args=[self.patient.uuid]),
            {'substance': 'Penicillin', 'severity': 'severe'},
        )
        self.assertEqual(Allergy.all_objects.filter(patient=self.patient).count(), 1)

    def test_a_recorded_allergy_warns_on_the_visit_page(self):
        Allergy.all_objects.create(
            tenant=self.tenant, patient=self.patient,
            substance='Penicillin', severity=Allergy.Severity.SEVERE,
        )
        self.client.login(email='doc@t.local', password='pass12345')
        response = self.client.get(reverse('medical:visit_detail', args=[self.visit.uuid]))
        self.assertContains(response, 'Penicillin')


class ClinicalIsolationTests(ClinicalTestBase):
    """Medical records are the most sensitive rows in the database — the
    tenant boundary has to hold for them as it does everywhere else."""

    def setUp(self):
        super().setUp()
        self.other = Tenant.objects.create(
            name='Rival', slug='rival', status=Tenant.Status.ACTIVE
        )
        provision_tenant_defaults(self.other)
        other_branch = Branch.all_objects.create(tenant=self.other, name='B', code='B')
        self.other_doctor = User.objects.create_user(
            username='otherdoc', email='otherdoc@t.local', password='pass12345',
            tenant=self.other, branch=other_branch,
            role=ClinicRole.all_objects.get(tenant=self.other, name='Doctor'),
        )

    def test_another_tenants_doctor_cannot_open_the_visit(self):
        self.client.login(email='otherdoc@t.local', password='pass12345')
        response = self.client.get(reverse('medical:visit_detail', args=[self.visit.uuid]))
        self.assertEqual(response.status_code, 404)

    def test_another_tenants_doctor_cannot_record_against_the_patient(self):
        self.client.login(email='otherdoc@t.local', password='pass12345')
        response = self.client.get(reverse('medical:visit_create', args=[self.patient.uuid]))
        self.assertEqual(response.status_code, 404)


class MedicalRetentionTests(ClinicalTestBase):
    def test_a_patient_with_records_cannot_be_deleted_at_the_model_level(self):
        with self.assertRaises(ProtectedError):
            self.patient.delete()

    def test_deleting_such_a_patient_explains_itself_instead_of_erroring(self):
        self.client.login(email='admin@t.local', password='pass12345')
        response = self.client.post(
            reverse('patients:patient_delete', args=[self.patient.uuid]), follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Patient.all_objects.filter(pk=self.patient.pk).exists())
        self.assertContains(response, 'سجلات طبية')
