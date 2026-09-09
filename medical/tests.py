"""Clinical records — access, isolation and retention.

The access rule is the point of these tests: Reception books, registers and
bills, but must never see a diagnosis.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from accounts.models import ClinicRole
from branches.models import Branch
from patients.models import Patient
from services.models import Service
from tenants.models import Tenant
from tenants.provisioning import provision_tenant_defaults

from tenants.context import tenant_context
from tenants.testing import act_as_tenant

from .models import (
    Allergy,
    Prescription,
    PrescriptionItem,
    Procedure,
    TreatmentPlan,
    TreatmentSession,
    Visit,
)

User = get_user_model()


class ClinicalTestBase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        act_as_tenant(self, self.tenant)
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
        # The rival tenant's own rows are written under its own binding — the
        # test process cannot write for two tenants at once, any more than a
        # request can.
        with tenant_context(self.other):
            other_branch = Branch.all_objects.create(tenant=self.other, name='B', code='B')
            other_role = ClinicRole.all_objects.get(tenant=self.other, name='Doctor')
        self.other_doctor = User.objects.create_user(
            username='otherdoc', email='otherdoc@t.local', password='pass12345',
            tenant=self.other, branch=other_branch, role=other_role,
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


def prescription_post(**overrides):
    """Formsets need their management form; keep it in one place."""
    data = {
        'issued_at': '2026-09-08T12:00',
        'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0',
        'items-MIN_NUM_FORMS': '1', 'items-MAX_NUM_FORMS': '1000',
        'items-0-medication': 'Paracetamol', 'items-0-dosage': '500 مجم',
        'items-0-frequency': 'مرتين يومياً', 'items-0-duration': '5 أيام',
    }
    data.update(overrides)
    return data


class PrescriptionTests(ClinicalTestBase):
    def test_doctor_can_issue_a_prescription_with_medications(self):
        self.client.login(email='doc@t.local', password='pass12345')
        response = self.client.post(
            reverse('medical:prescription_create', args=[self.visit.uuid]),
            prescription_post(),
        )
        self.assertEqual(response.status_code, 302)
        prescription = Prescription.all_objects.get()
        self.assertEqual(prescription.patient, self.patient)
        self.assertEqual(prescription.visit, self.visit)
        self.assertTrue(prescription.serial_number)
        # Reverse accessors (prescription.items) inherit the tenant-scoped
        # manager, so outside a request they return nothing — query explicitly.
        items = PrescriptionItem.all_objects.filter(prescription=prescription)
        self.assertEqual(items.count(), 1)
        self.assertEqual(items.first().tenant, self.tenant)

    def test_reverse_accessors_are_tenant_scoped_too(self):
        """Worth pinning because it surprises: prescription.items is filtered
        by the current tenant, so code running outside a request must either
        enter tenant_context or use all_objects."""
        prescription = Prescription.all_objects.create(
            tenant=self.tenant, visit=self.visit, patient=self.patient
        )
        PrescriptionItem.all_objects.create(
            tenant=self.tenant, prescription=prescription, medication='X'
        )
        self.assertEqual(prescription.items.count(), 0)  # no tenant in context
        with tenant_context(self.tenant):
            self.assertEqual(prescription.items.count(), 1)

    def test_a_prescription_needs_at_least_one_medication(self):
        self.client.login(email='doc@t.local', password='pass12345')
        response = self.client.post(
            reverse('medical:prescription_create', args=[self.visit.uuid]),
            prescription_post(**{'items-TOTAL_FORMS': '1', 'items-0-medication': ''}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Prescription.all_objects.exists())

    def test_reception_cannot_issue_a_prescription(self):
        self.client.login(email='rec@t.local', password='pass12345')
        response = self.client.post(
            reverse('medical:prescription_create', args=[self.visit.uuid]),
            prescription_post(),
        )
        self.assertNotEqual(response.status_code, 200)
        self.assertFalse(Prescription.all_objects.exists())

    def test_reception_cannot_read_a_prescription(self):
        prescription = Prescription.all_objects.create(
            tenant=self.tenant, visit=self.visit, patient=self.patient
        )
        self.client.login(email='rec@t.local', password='pass12345')
        response = self.client.get(
            reverse('medical:prescription_detail', args=[prescription.uuid])
        )
        self.assertNotEqual(response.status_code, 200)

    def test_the_printable_sheet_lists_the_medications(self):
        self.client.login(email='doc@t.local', password='pass12345')
        self.client.post(
            reverse('medical:prescription_create', args=[self.visit.uuid]), prescription_post()
        )
        prescription = Prescription.all_objects.get()
        response = self.client.get(
            reverse('medical:prescription_print', args=[prescription.uuid])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Paracetamol')
        self.assertContains(response, prescription.serial_number)


class AllergyWarningTests(ClinicalTestBase):
    """doc §26: the system may surface a suggestion but never takes the
    medical decision. So the warning must appear *and* must not block."""

    def setUp(self):
        super().setUp()
        Allergy.all_objects.create(
            tenant=self.tenant, patient=self.patient,
            substance='Penicillin', severity=Allergy.Severity.SEVERE,
        )
        self.client.login(email='doc@t.local', password='pass12345')

    def test_prescribing_a_recorded_allergen_still_saves(self):
        response = self.client.post(
            reverse('medical:prescription_create', args=[self.visit.uuid]),
            prescription_post(**{'items-0-medication': 'Penicillin V'}),
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Prescription.all_objects.exists())

    def test_prescribing_a_recorded_allergen_warns_the_doctor(self):
        response = self.client.post(
            reverse('medical:prescription_create', args=[self.visit.uuid]),
            prescription_post(**{'items-0-medication': 'Penicillin V'}),
            follow=True,
        )
        self.assertContains(response, 'Penicillin')
        warnings = [m for m in response.context['messages'] if m.level_tag == 'warning']
        self.assertEqual(len(warnings), 1)

    def test_an_unrelated_medication_raises_no_warning(self):
        response = self.client.post(
            reverse('medical:prescription_create', args=[self.visit.uuid]),
            prescription_post(**{'items-0-medication': 'Paracetamol'}),
            follow=True,
        )
        warnings = [m for m in response.context['messages'] if m.level_tag == 'warning']
        self.assertEqual(warnings, [])

    def test_the_matching_is_case_insensitive(self):
        from .models import allergy_conflicts
        self.assertTrue(allergy_conflicts(self.patient, ['PENICILLIN injection']))

    def test_the_prescription_form_shows_allergies_before_prescribing(self):
        response = self.client.get(
            reverse('medical:prescription_create', args=[self.visit.uuid])
        )
        self.assertContains(response, 'Penicillin')


class PrescriptionIsolationTests(ClinicalIsolationTests):
    def test_another_tenants_doctor_cannot_open_a_prescription(self):
        prescription = Prescription.all_objects.create(
            tenant=self.tenant, visit=self.visit, patient=self.patient
        )
        self.client.login(email='otherdoc@t.local', password='pass12345')
        response = self.client.get(
            reverse('medical:prescription_detail', args=[prescription.uuid])
        )
        self.assertEqual(response.status_code, 404)


class PrescriptionFormsetTests(ClinicalTestBase):
    """FE-015: medication lines are added and removed dynamically. The client
    only maintains the management form; the server still decides validity."""

    def setUp(self):
        super().setUp()
        self.client.login(email='doc@t.local', password='pass12345')

    def _create(self, count):
        data = {
            'issued_at': '2026-09-08T12:00',
            'items-TOTAL_FORMS': str(count), 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '1', 'items-MAX_NUM_FORMS': '1000',
        }
        for i in range(count):
            data[f'items-{i}-medication'] = f'Drug {i}'
            data[f'items-{i}-dosage'] = f'{i + 1}00 mg'
        return self.client.post(
            reverse('medical:prescription_create', args=[self.visit.uuid]), data
        )

    def test_more_than_three_medications_can_be_submitted(self):
        """The old form had three fixed rows — a fourth drug was impossible."""
        self.assertEqual(self._create(6).status_code, 302)
        prescription = Prescription.all_objects.get()
        self.assertEqual(
            PrescriptionItem.all_objects.filter(prescription=prescription).count(), 6
        )

    def test_a_single_medication_still_works(self):
        self.assertEqual(self._create(1).status_code, 302)
        self.assertEqual(PrescriptionItem.all_objects.count(), 1)

    def test_blank_trailing_rows_are_ignored(self):
        """Extra empty rows must not become empty medication lines."""
        data = {
            'issued_at': '2026-09-08T12:00',
            'items-TOTAL_FORMS': '4', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '1', 'items-MAX_NUM_FORMS': '1000',
            'items-0-medication': 'Only one',
        }
        for i in (1, 2, 3):
            data[f'items-{i}-medication'] = ''
        self.assertEqual(self.client.post(
            reverse('medical:prescription_create', args=[self.visit.uuid]), data
        ).status_code, 302)
        self.assertEqual(PrescriptionItem.all_objects.count(), 1)

    def test_removing_every_line_is_refused_server_side(self):
        """Client-side guards are convenience; this is the actual rule."""
        data = {
            'issued_at': '2026-09-08T12:00',
            'items-TOTAL_FORMS': '0', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '1', 'items-MAX_NUM_FORMS': '1000',
        }
        response = self.client.post(
            reverse('medical:prescription_create', args=[self.visit.uuid]), data
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Prescription.all_objects.exists())

    def test_a_saved_line_can_be_deleted_on_update(self):
        self._create(3)
        prescription = Prescription.all_objects.get()
        items = list(PrescriptionItem.all_objects.filter(prescription=prescription).order_by('id'))

        data = {
            'issued_at': '2026-09-08T12:00',
            'items-TOTAL_FORMS': '3', 'items-INITIAL_FORMS': '3',
            'items-MIN_NUM_FORMS': '1', 'items-MAX_NUM_FORMS': '1000',
        }
        for i, item in enumerate(items):
            data[f'items-{i}-id'] = str(item.pk)
            data[f'items-{i}-medication'] = item.medication
        data['items-1-DELETE'] = 'on'          # remove the middle line

        response = self.client.post(
            reverse('medical:prescription_update', args=[prescription.uuid]), data
        )
        self.assertEqual(response.status_code, 302)
        remaining = PrescriptionItem.all_objects.filter(prescription=prescription)
        self.assertEqual(remaining.count(), 2)
        self.assertNotIn(items[1].pk, [r.pk for r in remaining])

    def test_a_line_can_be_appended_on_update(self):
        self._create(1)
        prescription = Prescription.all_objects.get()
        existing = PrescriptionItem.all_objects.get(prescription=prescription)
        data = {
            'issued_at': '2026-09-08T12:00',
            'items-TOTAL_FORMS': '2', 'items-INITIAL_FORMS': '1',
            'items-MIN_NUM_FORMS': '1', 'items-MAX_NUM_FORMS': '1000',
            'items-0-id': str(existing.pk), 'items-0-medication': existing.medication,
            'items-1-medication': 'Added later',
        }
        self.assertEqual(self.client.post(
            reverse('medical:prescription_update', args=[prescription.uuid]), data
        ).status_code, 302)
        added = PrescriptionItem.all_objects.get(medication='Added later')
        self.assertEqual(added.tenant, self.tenant)

    def test_the_form_ships_a_row_template_and_an_add_control(self):
        """The add button is inert without an empty_form to clone."""
        response = self.client.get(
            reverse('medical:prescription_create', args=[self.visit.uuid])
        )
        self.assertContains(response, 'id="add-medication"')
        self.assertContains(response, 'id="empty-medication-row"')
        self.assertContains(response, '__prefix__')


class PrescriptionUrlAccessTests(ClinicalTestBase):
    """Closing a coverage gap found while analysing FE-015: update and print
    had no Reception test at all — believed safe, never demonstrated."""

    def setUp(self):
        super().setUp()
        self.prescription = Prescription.all_objects.create(
            tenant=self.tenant, visit=self.visit, patient=self.patient
        )

    def test_reception_is_blocked_on_every_prescription_url(self):
        self.client.login(email='rec@t.local', password='pass12345')
        urls = [
            reverse('medical:prescription_create', args=[self.visit.uuid]),
            reverse('medical:prescription_detail', args=[self.prescription.uuid]),
            reverse('medical:prescription_update', args=[self.prescription.uuid]),
            reverse('medical:prescription_print', args=[self.prescription.uuid]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertNotEqual(self.client.get(url).status_code, 200)
                self.assertNotEqual(self.client.post(url, {}).status_code, 200)

    def test_doctor_reaches_every_prescription_url(self):
        self.client.login(email='doc@t.local', password='pass12345')
        for name in ('prescription_detail', 'prescription_update', 'prescription_print'):
            with self.subTest(view=name):
                url = reverse(f'medical:{name}', args=[self.prescription.uuid])
                self.assertEqual(self.client.get(url).status_code, 200)


class TreatmentPlanTests(ClinicalTestBase):
    """P3 — a course of treatment delivered over several visits (doc §28).

    Structured, unlike the free-text `Visit.treatment_plan` note it sits beside:
    a named course with its own identity, which sessions will be booked against.
    """

    def setUp(self):
        super().setUp()
        self.client.login(email='doc@t.local', password='pass12345')

    def _post(self, **overrides):
        data = {
            'title': 'علاج بالليزر',
            'planned_sessions': '6',
            'status': TreatmentPlan.Status.ACTIVE,
            'start_date': '2026-09-08',
        }
        data.update(overrides)
        return self.client.post(
            reverse('medical:treatment_plan_create', args=[self.patient.uuid]), data
        )

    def test_doctor_can_create_a_plan_and_it_gets_a_serial(self):
        self.assertEqual(self._post().status_code, 302)
        plan = TreatmentPlan.all_objects.get()
        self.assertEqual(plan.patient, self.patient)
        self.assertEqual(plan.tenant, self.tenant)
        self.assertEqual(plan.created_by, self.doctor_user)
        self.assertEqual(plan.planned_sessions, 6)
        self.assertTrue(plan.serial_number)

    def test_the_branch_defaults_to_the_patients(self):
        """Left unset the plan would be invisible to branch-scoped staff."""
        self._post()
        self.assertEqual(TreatmentPlan.all_objects.get().branch, self.branch)

    def test_a_plan_needs_a_title(self):
        self.assertEqual(self._post(title='').status_code, 200)
        self.assertFalse(TreatmentPlan.all_objects.exists())

    def test_zero_sessions_is_refused(self):
        """A course of nothing is not a course — and `planned_sessions` feeds
        the session scheduling that follows."""
        self.assertEqual(self._post(planned_sessions='0').status_code, 200)
        self.assertFalse(TreatmentPlan.all_objects.exists())

    def test_serials_are_per_tenant_and_restart_at_001(self):
        self._post()
        self.assertTrue(TreatmentPlan.all_objects.get().serial_number.endswith('-001'))

    def test_doctor_can_read_and_update_a_plan(self):
        self._post()
        plan = TreatmentPlan.all_objects.get()

        response = self.client.get(
            reverse('medical:treatment_plan_detail', args=[plan.uuid])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'علاج بالليزر')

        response = self.client.post(
            reverse('medical:treatment_plan_update', args=[plan.uuid]),
            {
                'title': 'علاج بالليزر - معدل',
                'planned_sessions': '8',
                'status': TreatmentPlan.Status.COMPLETED,
                'start_date': '2026-09-08',
            },
        )
        self.assertEqual(response.status_code, 302)
        plan.refresh_from_db()
        self.assertEqual(plan.planned_sessions, 8)
        self.assertEqual(plan.status, TreatmentPlan.Status.COMPLETED)

    def test_the_plan_form_offers_this_tenants_records(self):
        """Regression guard: ModelChoiceField querysets built at import time
        resolve with no tenant in context and bake in .none(), which left every
        dropdown in the app empty once and was invisible in the tests."""
        form = self.client.get(
            reverse('medical:treatment_plan_create', args=[self.patient.uuid])
        ).context['form']
        self.assertGreater(form.fields['branch'].queryset.count(), 0)

    def test_the_plan_appears_on_the_patient_page(self):
        self._post()
        response = self.client.get(
            reverse('patients:patient_detail', args=[self.patient.uuid])
        )
        self.assertContains(response, 'علاج بالليزر')


class TreatmentPlanAccessTests(ClinicalTestBase):
    """A treatment plan states a diagnosis-driven course of care, so it sits
    behind the same wall as the rest of the clinical record."""

    def setUp(self):
        super().setUp()
        self.plan = TreatmentPlan.all_objects.create(
            tenant=self.tenant, patient=self.patient, branch=self.branch,
            title='CONFIDENTIAL COURSE', planned_sessions=3,
        )

    def test_reception_is_blocked_on_every_plan_url(self):
        self.client.login(email='rec@t.local', password='pass12345')
        urls = [
            reverse('medical:treatment_plan_create', args=[self.patient.uuid]),
            reverse('medical:treatment_plan_detail', args=[self.plan.uuid]),
            reverse('medical:treatment_plan_update', args=[self.plan.uuid]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertNotEqual(self.client.get(url).status_code, 200)
                self.assertNotEqual(self.client.post(url, {}).status_code, 200)

    def test_a_plan_never_reaches_receptions_patient_page(self):
        self.client.login(email='rec@t.local', password='pass12345')
        response = self.client.get(
            reverse('patients:patient_detail', args=[self.patient.uuid])
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'CONFIDENTIAL COURSE')

    def test_a_user_with_no_role_gets_nothing(self):
        User.objects.create_user(
            username='norole2', email='norole2@t.local', password='pass12345',
            tenant=self.tenant, branch=self.branch,
        )
        self.client.login(email='norole2@t.local', password='pass12345')
        self.assertNotEqual(
            self.client.get(
                reverse('medical:treatment_plan_detail', args=[self.plan.uuid])
            ).status_code,
            200,
        )


class TreatmentPlanIsolationTests(ClinicalIsolationTests):
    def test_another_tenants_doctor_cannot_open_a_plan(self):
        plan = TreatmentPlan.all_objects.create(
            tenant=self.tenant, patient=self.patient, branch=self.branch,
            title='Ours', planned_sessions=2,
        )
        self.client.login(email='otherdoc@t.local', password='pass12345')
        response = self.client.get(
            reverse('medical:treatment_plan_detail', args=[plan.uuid])
        )
        self.assertEqual(response.status_code, 404)

    def test_another_tenants_doctor_cannot_create_against_the_patient(self):
        self.client.login(email='otherdoc@t.local', password='pass12345')
        response = self.client.get(
            reverse('medical:treatment_plan_create', args=[self.patient.uuid])
        )
        self.assertEqual(response.status_code, 404)


class TreatmentSessionTests(ClinicalTestBase):
    """P3 — the sessions a plan is delivered in (doc §28), including the
    quantity-priced services of §29 where 25 pulses cost 25 times the unit."""

    def setUp(self):
        super().setUp()
        self.service = Service.all_objects.create(
            tenant=self.tenant, name='ليزر', base_price=Decimal('100.00')
        )
        self.plan = TreatmentPlan.all_objects.create(
            tenant=self.tenant, patient=self.patient, branch=self.branch,
            service=self.service, title='علاج بالليزر', planned_sessions=3,
        )
        self.client.login(email='doc@t.local', password='pass12345')

    def _post(self, **overrides):
        data = {
            'scheduled_date': '2026-09-08T10:00',
            'status': TreatmentSession.Status.SCHEDULED,
            'quantity': '1',
            'unit_price': '100.00',
            'discount': '0',
        }
        data.update(overrides)
        return self.client.post(
            reverse('medical:session_create', args=[self.plan.uuid]), data
        )

    def test_doctor_can_record_a_session(self):
        self.assertEqual(self._post().status_code, 302)
        session = TreatmentSession.all_objects.get()
        self.assertEqual(session.plan, self.plan)
        self.assertEqual(session.patient, self.patient)
        self.assertEqual(session.tenant, self.tenant)
        self.assertEqual(session.created_by, self.doctor_user)

    def test_sessions_are_numbered_within_the_plan(self):
        for _ in range(3):
            self._post()
        sequences = list(
            TreatmentSession.all_objects.filter(plan=self.plan)
            .order_by('sequence').values_list('sequence', flat=True)
        )
        self.assertEqual(sequences, [1, 2, 3])

    def test_numbering_restarts_for_a_different_plan(self):
        """Sequence is a position in a course — session 1 of 6 — not a global
        identifier, so a second plan starts at 1 again."""
        self._post()
        other = TreatmentPlan.all_objects.create(
            tenant=self.tenant, patient=self.patient, branch=self.branch,
            title='خطة أخرى', planned_sessions=2,
        )
        self.client.post(
            reverse('medical:session_create', args=[other.uuid]),
            {
                'scheduled_date': '2026-09-08T11:00',
                'status': TreatmentSession.Status.SCHEDULED,
                'quantity': '1', 'unit_price': '50', 'discount': '0',
            },
        )
        self.assertEqual(TreatmentSession.all_objects.get(plan=other).sequence, 1)

    def test_quantity_priced_services_multiply(self):
        """doc §29: 25 pulses at 100 each is 2500, not 100."""
        self._post(quantity='25', unit_price='100.00')
        session = TreatmentSession.all_objects.get()
        self.assertEqual(session.gross_amount, Decimal('2500.00'))
        self.assertEqual(session.total_amount, Decimal('2500.00'))

    def test_a_discount_reduces_the_total(self):
        self._post(quantity='10', unit_price='100.00', discount='250.00')
        self.assertEqual(
            TreatmentSession.all_objects.get().total_amount, Decimal('750.00')
        )

    def test_a_discount_larger_than_the_line_is_refused(self):
        """Otherwise the session contributes negative revenue, and every total
        downstream of it is wrong."""
        response = self._post(quantity='1', unit_price='100.00', discount='500.00')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(TreatmentSession.all_objects.exists())

    def test_the_database_refuses_an_over_discount_too(self):
        """The form check is a courtesy; this is the actual rule. A background
        job or a future API bypassing the form must not be able to write it."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TreatmentSession.all_objects.create(
                    tenant=self.tenant, plan=self.plan, patient=self.patient,
                    sequence=99, quantity=1,
                    unit_price=Decimal('100.00'), discount=Decimal('500.00'),
                )

    def test_negative_money_is_refused(self):
        self.assertEqual(self._post(unit_price='-10').status_code, 200)
        self.assertFalse(TreatmentSession.all_objects.exists())

    def test_zero_quantity_is_refused(self):
        self.assertEqual(self._post(quantity='0').status_code, 200)
        self.assertFalse(TreatmentSession.all_objects.exists())

    def test_the_price_is_seeded_from_the_plans_service(self):
        """§29 wants the price to come from a pricing engine. There is none
        yet, so it comes from the service — the seam is the same either way."""
        form = self.client.get(
            reverse('medical:session_create', args=[self.plan.uuid])
        ).context['form']
        self.assertEqual(form.initial['unit_price'], Decimal('100.00'))
        self.assertEqual(form.initial['service'], self.service)

    def test_the_plan_counts_completed_sessions_rather_than_storing_them(self):
        self._post(status=TreatmentSession.Status.COMPLETED)
        self._post(status=TreatmentSession.Status.COMPLETED)
        self._post(status=TreatmentSession.Status.CANCELLED)
        with tenant_context(self.tenant):
            plan = TreatmentPlan.all_objects.get(pk=self.plan.pk)
            self.assertEqual(plan.completed_sessions, 2)
            self.assertEqual(plan.remaining_sessions, 1)

    def test_sessions_appear_on_the_plan_page(self):
        self._post(unit_price='125.00')
        response = self.client.get(
            reverse('medical:treatment_plan_detail', args=[self.plan.uuid])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '125.00')

    def test_doctor_can_read_and_update_a_session(self):
        self._post()
        session = TreatmentSession.all_objects.get()
        self.assertEqual(
            self.client.get(
                reverse('medical:session_detail', args=[session.uuid])
            ).status_code,
            200,
        )
        response = self.client.post(
            reverse('medical:session_update', args=[session.uuid]),
            {
                'scheduled_date': '2026-09-08T10:00',
                'status': TreatmentSession.Status.COMPLETED,
                'quantity': '2', 'unit_price': '100.00', 'discount': '0',
                'result': 'تحسن ملحوظ',
            },
        )
        self.assertEqual(response.status_code, 302)
        session.refresh_from_db()
        self.assertEqual(session.status, TreatmentSession.Status.COMPLETED)
        self.assertEqual(session.result, 'تحسن ملحوظ')


class TreatmentSessionAccessTests(ClinicalTestBase):
    """A session records what was done to a patient and what it cost — the
    same wall as the rest of the clinical record."""

    def setUp(self):
        super().setUp()
        self.plan = TreatmentPlan.all_objects.create(
            tenant=self.tenant, patient=self.patient, branch=self.branch,
            title='CONFIDENTIAL COURSE', planned_sessions=2,
        )
        self.session = TreatmentSession.all_objects.create(
            tenant=self.tenant, plan=self.plan, patient=self.patient,
            branch=self.branch, sequence=1, result='CONFIDENTIAL RESULT',
        )

    def test_reception_is_blocked_on_every_session_url(self):
        self.client.login(email='rec@t.local', password='pass12345')
        urls = [
            reverse('medical:session_create', args=[self.plan.uuid]),
            reverse('medical:session_detail', args=[self.session.uuid]),
            reverse('medical:session_update', args=[self.session.uuid]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertNotEqual(self.client.get(url).status_code, 200)
                self.assertNotEqual(self.client.post(url, {}).status_code, 200)

    def test_a_user_with_no_role_gets_nothing(self):
        User.objects.create_user(
            username='norole3', email='norole3@t.local', password='pass12345',
            tenant=self.tenant, branch=self.branch,
        )
        self.client.login(email='norole3@t.local', password='pass12345')
        self.assertNotEqual(
            self.client.get(
                reverse('medical:session_detail', args=[self.session.uuid])
            ).status_code,
            200,
        )


class TreatmentSessionIsolationTests(ClinicalIsolationTests):
    def test_another_tenants_doctor_cannot_open_a_session(self):
        plan = TreatmentPlan.all_objects.create(
            tenant=self.tenant, patient=self.patient, branch=self.branch,
            title='Ours', planned_sessions=1,
        )
        session = TreatmentSession.all_objects.create(
            tenant=self.tenant, plan=plan, patient=self.patient,
            branch=self.branch, sequence=1,
        )
        self.client.login(email='otherdoc@t.local', password='pass12345')
        self.assertEqual(
            self.client.get(
                reverse('medical:session_detail', args=[session.uuid])
            ).status_code,
            404,
        )


class ProcedureTests(ClinicalTestBase):
    """P3 — a discrete clinical act performed at a visit (doc §19, §23).

    Distinct from a Service (a catalogue entry) and from a TreatmentSession
    (one numbered step of a course). §46 counts it separately from both.
    """

    def setUp(self):
        super().setUp()
        self.service = Service.all_objects.create(
            tenant=self.tenant, name='استئصال', base_price=Decimal('500.00')
        )
        self.client.login(email='doc@t.local', password='pass12345')

    def _post(self, **overrides):
        data = {
            'name': 'استئصال شامة',
            'performed_at': '2026-09-08T10:00',
            'status': Procedure.Status.COMPLETED,
            'body_site': 'الساعد الأيمن',
            'quantity': '1',
            'unit_price': '500.00',
            'discount': '0',
        }
        data.update(overrides)
        return self.client.post(
            reverse('medical:procedure_create', args=[self.visit.uuid]), data
        )

    def test_doctor_can_record_a_procedure(self):
        self.assertEqual(self._post().status_code, 302)
        procedure = Procedure.all_objects.get()
        self.assertEqual(procedure.visit, self.visit)
        self.assertEqual(procedure.patient, self.patient)
        self.assertEqual(procedure.tenant, self.tenant)
        self.assertEqual(procedure.created_by, self.doctor_user)
        self.assertEqual(procedure.body_site, 'الساعد الأيمن')

    def test_it_gets_a_serial_starting_at_001(self):
        self._post()
        self.assertTrue(Procedure.all_objects.get().serial_number.endswith('-001'))

    def test_serials_are_a_separate_sequence_from_visits(self):
        """Procedures have their own SerialCounter scope, so numbering does not
        interleave with visits or prescriptions."""
        self._post()
        procedure = Procedure.all_objects.get()
        self.assertNotEqual(procedure.serial_number, self.visit.serial_number)

    def test_a_procedure_needs_a_name(self):
        """An unnamed act is not a record of anything. The name is required even
        though the catalogue Service is optional, because plenty of procedures
        are not in the price list."""
        self.assertEqual(self._post(name='').status_code, 200)
        self.assertFalse(Procedure.all_objects.exists())

    def test_the_service_is_optional(self):
        """An unlisted procedure must still be recordable."""
        self.assertEqual(self._post().status_code, 302)
        self.assertIsNone(Procedure.all_objects.get().service)

    def test_the_doctor_and_branch_default_to_the_visits(self):
        self._post()
        procedure = Procedure.all_objects.get()
        self.assertEqual(procedure.branch, self.visit.branch)

    def test_money_is_computed_from_quantity_and_discount(self):
        self._post(quantity='3', unit_price='500.00', discount='250.00')
        procedure = Procedure.all_objects.get()
        self.assertEqual(procedure.gross_amount, Decimal('1500.00'))
        self.assertEqual(procedure.total_amount, Decimal('1250.00'))

    def test_a_discount_larger_than_the_line_is_refused(self):
        response = self._post(quantity='1', unit_price='500.00', discount='900.00')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Procedure.all_objects.exists())

    def test_the_database_refuses_an_over_discount_too(self):
        """The form check is a courtesy; this is the rule. Same guarantee as
        TreatmentSession — a background job or future API cannot write negative
        revenue."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Procedure.all_objects.create(
                    tenant=self.tenant, visit=self.visit, patient=self.patient,
                    name='X', quantity=1,
                    unit_price=Decimal('100.00'), discount=Decimal('500.00'),
                )

    def test_negative_money_and_zero_quantity_are_refused(self):
        self.assertEqual(self._post(unit_price='-1').status_code, 200)
        self.assertEqual(self._post(quantity='0').status_code, 200)
        self.assertFalse(Procedure.all_objects.exists())

    def test_complications_are_recordable_and_flagged(self):
        """An adverse event needs somewhere to live. Without a field for it, it
        gets written into a free-text note where nobody finds it again."""
        self._post(complications='نزيف بسيط توقف بالضغط')
        procedure = Procedure.all_objects.get()
        self.assertTrue(procedure.had_complications)
        response = self.client.get(
            reverse('medical:procedure_detail', args=[procedure.uuid])
        )
        self.assertContains(response, 'نزيف بسيط')
        self.assertContains(response, 'مضاعفات مسجلة')

    def test_no_complications_means_no_warning(self):
        self._post()
        procedure = Procedure.all_objects.get()
        self.assertFalse(procedure.had_complications)
        response = self.client.get(
            reverse('medical:procedure_detail', args=[procedure.uuid])
        )
        self.assertNotContains(response, 'مضاعفات مسجلة')

    def test_an_aborted_procedure_is_distinguishable_from_a_cancelled_one(self):
        """Aborted means it was started on the patient and stopped — a clinical
        event. Cancelled means it never happened. Collapsing the two would lose
        the difference."""
        self.assertEqual(self._post(status=Procedure.Status.ABORTED).status_code, 302)
        self.assertEqual(
            Procedure.all_objects.get().status, Procedure.Status.ABORTED
        )
        self.assertNotEqual(Procedure.Status.ABORTED, Procedure.Status.CANCELLED)

    def test_doctor_can_read_and_update_a_procedure(self):
        self._post()
        procedure = Procedure.all_objects.get()
        self.assertEqual(
            self.client.get(
                reverse('medical:procedure_detail', args=[procedure.uuid])
            ).status_code,
            200,
        )
        response = self.client.post(
            reverse('medical:procedure_update', args=[procedure.uuid]),
            {
                'name': 'استئصال شامة - معدل',
                'performed_at': '2026-09-08T10:00',
                'status': Procedure.Status.COMPLETED,
                'quantity': '1', 'unit_price': '500.00', 'discount': '0',
                'outcome': 'التئام كامل',
            },
        )
        self.assertEqual(response.status_code, 302)
        procedure.refresh_from_db()
        self.assertEqual(procedure.outcome, 'التئام كامل')

    def test_there_is_no_delete_route(self):
        """doc §66: medical data must not change without trace. Prescriptions
        already work this way; procedures follow."""
        from django.urls import NoReverseMatch

        self._post()
        procedure = Procedure.all_objects.get()
        with self.assertRaises(NoReverseMatch):
            reverse('medical:procedure_delete', args=[procedure.uuid])

    def test_the_procedure_appears_on_the_visit_page(self):
        self._post()
        response = self.client.get(
            reverse('medical:visit_detail', args=[self.visit.uuid])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'استئصال شامة')
        self.assertContains(response, 'الساعد الأيمن')

    def test_the_form_offers_this_tenants_records(self):
        form = self.client.get(
            reverse('medical:procedure_create', args=[self.visit.uuid])
        ).context['form']
        self.assertGreater(form.fields['branch'].queryset.count(), 0)
        self.assertGreater(form.fields['service'].queryset.count(), 0)


class ProcedureAccessTests(ClinicalTestBase):
    """A procedure records what was physically done to a patient — the same
    wall as the rest of the clinical record."""

    def setUp(self):
        super().setUp()
        self.procedure = Procedure.all_objects.create(
            tenant=self.tenant, visit=self.visit, patient=self.patient,
            branch=self.branch, name='CONFIDENTIAL PROCEDURE',
            findings='CONFIDENTIAL FINDING',
        )

    def test_reception_is_blocked_on_every_procedure_url(self):
        self.client.login(email='rec@t.local', password='pass12345')
        urls = [
            reverse('medical:procedure_create', args=[self.visit.uuid]),
            reverse('medical:procedure_detail', args=[self.procedure.uuid]),
            reverse('medical:procedure_update', args=[self.procedure.uuid]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertNotEqual(self.client.get(url).status_code, 200)
                self.assertNotEqual(self.client.post(url, {}).status_code, 200)

    def test_a_user_with_no_role_gets_nothing(self):
        User.objects.create_user(
            username='norole4', email='norole4@t.local', password='pass12345',
            tenant=self.tenant, branch=self.branch,
        )
        self.client.login(email='norole4@t.local', password='pass12345')
        self.assertNotEqual(
            self.client.get(
                reverse('medical:procedure_detail', args=[self.procedure.uuid])
            ).status_code,
            200,
        )


class ProcedureIsolationTests(ClinicalIsolationTests):
    def test_another_tenants_doctor_cannot_open_a_procedure(self):
        procedure = Procedure.all_objects.create(
            tenant=self.tenant, visit=self.visit, patient=self.patient,
            branch=self.branch, name='Ours',
        )
        self.client.login(email='otherdoc@t.local', password='pass12345')
        self.assertEqual(
            self.client.get(
                reverse('medical:procedure_detail', args=[procedure.uuid])
            ).status_code,
            404,
        )

    def test_another_tenants_doctor_cannot_record_against_the_visit(self):
        self.client.login(email='otherdoc@t.local', password='pass12345')
        self.assertEqual(
            self.client.get(
                reverse('medical:procedure_create', args=[self.visit.uuid])
            ).status_code,
            404,
        )
