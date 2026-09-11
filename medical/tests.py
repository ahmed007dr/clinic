"""Clinical records — access, isolation and retention.

The access rule is the point of these tests: Reception books, registers and
bills, but must never see a diagnosis.
"""

import hashlib
import os
import shutil
import tempfile
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import ClinicRole
from branches.models import Branch
from employees.models import Employee, EmployeeType
from patients.models import Patient
from services.models import Service
from tenants.models import Tenant
from tenants.provisioning import provision_tenant_defaults

from tenants.context import tenant_context
from tenants.testing import act_as_tenant

from .attachments import (
    attachment_storage,
    attachment_upload_path,
    checksum,
    validate_attachment,
)
from .models import (
    Allergy,
    LabResult,
    MedicalAttachment,
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

        # A doctor sees only their own patients (accounts.roles), so the
        # doctor account is linked to a doctor record and the visit that makes
        # this patient theirs is under that record.
        self.doctor = Employee.all_objects.create(
            tenant=self.tenant, name='Dr Test', branch=self.branch,
            employee_type=EmployeeType.all_objects.get(tenant=self.tenant, name='Doctor'),
            national_id='DOC-1', salary_value=0,
        )
        self.doctor_user.employee = self.doctor
        self.doctor_user.save(update_fields=['employee'])

        self.patient = Patient.all_objects.create(
            tenant=self.tenant, name='Test Patient', branch=self.branch,
        )
        self.visit = Visit.all_objects.create(
            tenant=self.tenant, patient=self.patient, branch=self.branch, doctor=self.doctor,
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
    def test_an_admin_can_record_a_visit_and_it_gets_a_serial(self):
        self.client.login(email='admin@t.local', password='pass12345')
        response = self.client.post(
            reverse('medical:visit_create', args=[self.patient.uuid]),
            {'visit_date': '2026-09-08T10:00', 'diagnosis': 'Eczema', 'branch': self.branch.pk},
        )
        self.assertEqual(response.status_code, 302)
        visit = Visit.all_objects.get(diagnosis='Eczema')
        self.assertEqual(visit.tenant, self.tenant)
        self.assertEqual(visit.created_by, self.admin_user)
        self.assertTrue(visit.serial_number)

    def test_a_doctor_does_not_open_visits_the_desk_does(self):
        """Visits open when reception sends the patient in (medical/checkin.py)."""
        self.client.login(email='doc@t.local', password='pass12345')
        self.client.post(
            reverse('medical:visit_create', args=[self.patient.uuid]),
            {'visit_date': '2026-09-08T10:00', 'diagnosis': 'Doc-opened', 'branch': self.branch.pk},
        )
        self.assertFalse(Visit.all_objects.filter(diagnosis='Doc-opened').exists())

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
        prescription = Prescription.all_objects.create(doctor=self.doctor, 
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
        prescription = Prescription.all_objects.create(doctor=self.doctor, 
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
        prescription = Prescription.all_objects.create(doctor=self.doctor, 
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
        self.prescription = Prescription.all_objects.create(doctor=self.doctor, 
            tenant=self.tenant, visit=self.visit, patient=self.patient
        )

    def test_reception_is_blocked_on_every_prescription_url(self):
        self.client.login(email='rec@t.local', password='pass12345')
        urls = [
            reverse('medical:prescription_create', args=[self.visit.uuid]),
            reverse('medical:prescription_detail', args=[self.prescription.uuid]),
            reverse('medical:prescription_update', args=[self.prescription.uuid]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertNotEqual(self.client.get(url).status_code, 200)
                self.assertNotEqual(self.client.post(url, {}).status_code, 200)

    def test_reception_prints_for_the_doctor_to_sign(self):
        """The one prescription page the desk reaches (2026-09-11): the sheet
        itself, in their own clinic, read-only."""
        self.client.login(email='rec@t.local', password='pass12345')
        url = reverse('medical:prescription_print', args=[self.prescription.uuid])
        self.assertEqual(self.client.get(url).status_code, 200)

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
        self.plan = TreatmentPlan.all_objects.create(doctor=self.doctor, 
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
        plan = TreatmentPlan.all_objects.create(doctor=self.doctor, 
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
        self.plan = TreatmentPlan.all_objects.create(doctor=self.doctor, 
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
        other = TreatmentPlan.all_objects.create(doctor=self.doctor, 
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
        # Price and discount are management's to set (billing.pricing).
        self.client.login(email='admin@t.local', password='pass12345')
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
        # Price and discount are management's to set (billing.pricing).
        self.client.login(email='admin@t.local', password='pass12345')
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
        self.plan = TreatmentPlan.all_objects.create(doctor=self.doctor, 
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
        plan = TreatmentPlan.all_objects.create(doctor=self.doctor, 
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
        # Price and discount are management's to set (billing.pricing).
        self.client.login(email='admin@t.local', password='pass12345')
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


class LabResultTests(ClinicalTestBase):
    """P3 — lab results on the patient record (doc §23).

    The spec says only "Lab results", so most of what is asserted here is the
    design: values are text, abnormality is entered rather than inferred, and
    acknowledgement is a first-class act.
    """

    def setUp(self):
        super().setUp()
        self.client.login(email='doc@t.local', password='pass12345')

    def _post(self, **overrides):
        data = {
            'test_name': 'صورة دم كاملة',
            'specimen': 'دم وريدي',
            'status': LabResult.Status.ORDERED,
            'flag': LabResult.Flag.NORMAL,
            'ordered_at': '2026-09-08T09:00',
        }
        data.update(overrides)
        return self.client.post(
            reverse('medical:lab_result_create', args=[self.patient.uuid]), data
        )

    def test_doctor_can_order_a_test(self):
        self.assertEqual(self._post().status_code, 302)
        result = LabResult.all_objects.get()
        self.assertEqual(result.patient, self.patient)
        self.assertEqual(result.tenant, self.tenant)
        self.assertEqual(result.created_by, self.doctor_user)
        self.assertEqual(result.status, LabResult.Status.ORDERED)
        self.assertTrue(result.serial_number)

    def test_a_test_name_is_required(self):
        self.assertEqual(self._post(test_name='').status_code, 200)
        self.assertFalse(LabResult.all_objects.exists())

    def test_a_result_can_be_qualitative_not_just_numeric(self):
        """Values are stored as text on purpose: 'إيجابي' and '<0.01' are as
        real as '7.2', and a numeric field would reject them."""
        for value in ('إيجابي', '<0.01', '7.2', 'لم يُكتشف'):
            with self.subTest(value=value):
                LabResult.all_objects.filter(patient=self.patient).delete()
                response = self._post(
                    value=value, status=LabResult.Status.RESULTED,
                    ordered_at='2026-09-08T09:00',
                )
                self.assertEqual(response.status_code, 302)
                self.assertEqual(LabResult.all_objects.get().value, value)

    def test_a_resulted_test_must_carry_a_value(self):
        """Otherwise the row reads as 'صدرت النتيجة' with nothing in it, which
        looks like a normal result rather than a missing one."""
        response = self._post(status=LabResult.Status.RESULTED, value='')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(LabResult.all_objects.exists())

    def test_resulted_at_is_stamped_when_the_result_arrives(self):
        """A result marked as arrived with no arrival date makes 'how long has
        this been waiting' unanswerable."""
        self._post(status=LabResult.Status.RESULTED, value='13.4')
        self.assertIsNotNone(LabResult.all_objects.get().resulted_at)

    # ---- the point of the model: abnormal results get seen -------------------

    def _resulted(self, flag=LabResult.Flag.ABNORMAL):
        return LabResult.all_objects.create(
            tenant=self.tenant, patient=self.patient, branch=self.branch,
            test_name='سكر صائم', value='162', unit='mg/dL',
            reference_range='70 - 99', flag=flag,
            status=LabResult.Status.RESULTED,
        )

    def test_an_unacknowledged_abnormal_result_needs_attention(self):
        self.assertTrue(self._resulted().needs_attention)

    def test_a_normal_result_does_not_need_attention(self):
        self.assertFalse(self._resulted(LabResult.Flag.NORMAL).needs_attention)

    def test_an_abnormal_result_that_has_not_arrived_does_not_need_attention(self):
        """There is nothing to read yet, so chasing it would be noise."""
        pending = LabResult.all_objects.create(
            tenant=self.tenant, patient=self.patient, branch=self.branch,
            test_name='سكر صائم', flag=LabResult.Flag.ABNORMAL,
            status=LabResult.Status.ORDERED,
        )
        self.assertFalse(pending.needs_attention)

    def test_acknowledging_clears_the_need_for_attention(self):
        result = self._resulted()
        response = self.client.post(
            reverse('medical:lab_result_acknowledge', args=[result.uuid])
        )
        self.assertEqual(response.status_code, 302)
        result.refresh_from_db()
        self.assertTrue(result.is_acknowledged)
        self.assertEqual(result.acknowledged_by, self.doctor_user)
        self.assertIsNotNone(result.acknowledged_at)
        self.assertFalse(result.needs_attention)

    def test_acknowledging_twice_keeps_the_first_signature(self):
        """Who saw it first is the fact worth keeping; a second click must not
        rewrite it."""
        result = self._resulted()
        result.acknowledge(self.doctor_user)
        first_at = result.acknowledged_at

        self.assertFalse(result.acknowledge(self.admin_user))
        result.refresh_from_db()
        self.assertEqual(result.acknowledged_by, self.doctor_user)
        self.assertEqual(result.acknowledged_at, first_at)

    def test_acknowledgement_cannot_happen_on_a_get(self):
        """A clinical sign-off must not be triggerable by a crawler, a prefetch
        or a link someone was sent."""
        result = self._resulted()
        response = self.client.get(
            reverse('medical:lab_result_acknowledge', args=[result.uuid])
        )
        self.assertEqual(response.status_code, 405)
        result.refresh_from_db()
        self.assertFalse(result.is_acknowledged)

    def test_the_edit_form_cannot_acknowledge_as_a_side_effect(self):
        """Acknowledgement is its own act, so the general edit form must not
        expose those fields at all."""
        form = self.client.get(
            reverse('medical:lab_result_create', args=[self.patient.uuid])
        ).context['form']
        self.assertNotIn('acknowledged_by', form.fields)
        self.assertNotIn('acknowledged_at', form.fields)

    def test_a_critical_result_is_distinguishable_from_a_merely_abnormal_one(self):
        """Critical means act now; a clinician scanning a list needs that
        without reading values."""
        critical = self._resulted(LabResult.Flag.CRITICAL)
        self.assertTrue(critical.is_out_of_range)
        self.assertTrue(critical.needs_attention)
        self.assertNotEqual(LabResult.Flag.CRITICAL, LabResult.Flag.ABNORMAL)

    # ---- surfacing -----------------------------------------------------------

    def test_the_patient_page_flags_a_result_nobody_has_read(self):
        self._resulted()
        response = self.client.get(
            reverse('patients:patient_detail', args=[self.patient.uuid])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'سكر صائم')
        self.assertContains(response, 'لم يُطّلع عليها')

    def test_the_patient_page_stops_flagging_once_acknowledged(self):
        result = self._resulted()
        result.acknowledge(self.doctor_user)
        response = self.client.get(
            reverse('patients:patient_detail', args=[self.patient.uuid])
        )
        self.assertContains(response, 'سكر صائم')
        self.assertNotContains(response, 'لم يُطّلع عليها')

    def test_doctor_can_read_and_update_a_result(self):
        result = self._resulted()
        self.assertEqual(
            self.client.get(
                reverse('medical:lab_result_detail', args=[result.uuid])
            ).status_code,
            200,
        )
        response = self.client.post(
            reverse('medical:lab_result_update', args=[result.uuid]),
            {
                'test_name': 'سكر صائم', 'status': LabResult.Status.RESULTED,
                'flag': LabResult.Flag.CRITICAL, 'value': '310',
                'ordered_at': '2026-09-08T09:00',
            },
        )
        self.assertEqual(response.status_code, 302)
        result.refresh_from_db()
        self.assertEqual(result.flag, LabResult.Flag.CRITICAL)

    def test_there_is_no_delete_route(self):
        from django.urls import NoReverseMatch

        result = self._resulted()
        with self.assertRaises(NoReverseMatch):
            reverse('medical:lab_result_delete', args=[result.uuid])


class LabResultAccessTests(ClinicalTestBase):
    def setUp(self):
        super().setUp()
        self.result = LabResult.all_objects.create(
            tenant=self.tenant, patient=self.patient, branch=self.branch,
            test_name='CONFIDENTIAL TEST', value='CONFIDENTIAL VALUE',
            status=LabResult.Status.RESULTED, flag=LabResult.Flag.ABNORMAL,
        )

    def test_reception_is_blocked_on_every_lab_url(self):
        self.client.login(email='rec@t.local', password='pass12345')
        urls = [
            reverse('medical:lab_result_create', args=[self.patient.uuid]),
            reverse('medical:lab_result_detail', args=[self.result.uuid]),
            reverse('medical:lab_result_update', args=[self.result.uuid]),
            reverse('medical:lab_result_acknowledge', args=[self.result.uuid]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertNotEqual(self.client.get(url).status_code, 200)
                self.assertNotEqual(self.client.post(url, {}).status_code, 200)

    def test_reception_cannot_acknowledge_a_result(self):
        """Sign-off is a clinical act, so it must not merely be hidden."""
        self.client.login(email='rec@t.local', password='pass12345')
        self.client.post(
            reverse('medical:lab_result_acknowledge', args=[self.result.uuid])
        )
        self.result.refresh_from_db()
        self.assertFalse(self.result.is_acknowledged)

    def test_results_never_reach_receptions_patient_page(self):
        self.client.login(email='rec@t.local', password='pass12345')
        response = self.client.get(
            reverse('patients:patient_detail', args=[self.patient.uuid])
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'CONFIDENTIAL TEST')
        self.assertNotContains(response, 'CONFIDENTIAL VALUE')


class LabResultIsolationTests(ClinicalIsolationTests):
    def test_another_tenants_doctor_cannot_open_a_result(self):
        result = LabResult.all_objects.create(
            tenant=self.tenant, patient=self.patient, branch=self.branch,
            test_name='Ours', status=LabResult.Status.RESULTED, value='1',
        )
        self.client.login(email='otherdoc@t.local', password='pass12345')
        self.assertEqual(
            self.client.get(
                reverse('medical:lab_result_detail', args=[result.uuid])
            ).status_code,
            404,
        )

    def test_another_tenants_doctor_cannot_acknowledge_a_result(self):
        result = LabResult.all_objects.create(
            tenant=self.tenant, patient=self.patient, branch=self.branch,
            test_name='Ours', status=LabResult.Status.RESULTED, value='1',
            flag=LabResult.Flag.ABNORMAL,
        )
        self.client.login(email='otherdoc@t.local', password='pass12345')
        self.assertEqual(
            self.client.post(
                reverse('medical:lab_result_acknowledge', args=[result.uuid])
            ).status_code,
            404,
        )
        result.refresh_from_db()
        self.assertFalse(result.is_acknowledged)


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def upload(name="report.pdf", content=PDF_BYTES, content_type="application/pdf"):
    return SimpleUploadedFile(name, content, content_type=content_type)


class AttachmentStorageTests(SimpleTestCase):
    """The storage decisions, asserted directly — these are what make the file
    bytes safe, and none of them is visible from the model."""

    def test_attachments_are_stored_outside_media_root(self):
        """A file under MEDIA_ROOT is a candidate for the web server to serve,
        and a file served that way has bypassed every check in the view layer.
        With DEBUG on, Django serves MEDIA_ROOT itself with no authentication.
        """
        attachments = Path(settings.MEDICAL_ATTACHMENTS_ROOT).resolve()
        media = Path(settings.MEDIA_ROOT).resolve()
        self.assertNotEqual(attachments, media)
        self.assertFalse(
            str(attachments).startswith(str(media) + os.sep),
            f"attachments are inside MEDIA_ROOT: {attachments}",
        )

    def test_the_storage_exposes_no_public_url(self):
        """`attachment.file.url` must fail rather than return a path. A template
        that reaches for it should break loudly, not render a link that leaks."""
        with self.assertRaises(ValueError):
            attachment_storage().url("tenant-1/whatever.pdf")

    def test_the_override_is_load_bearing_not_decorative(self):
        """Passing base_url=None does not achieve the above, which is easy to
        assume and wrong: None means "use the default", and the default is
        MEDIA_URL. A storage built that way hands out
        /media/tenant-1/<uuid>.pdf quite happily. This asserts the difference so
        nobody simplifies the override away."""
        from django.core.files.storage import FileSystemStorage

        naive = FileSystemStorage(
            location=str(settings.MEDICAL_ATTACHMENTS_ROOT), base_url=None
        )
        self.assertTrue(naive.url("tenant-1/whatever.pdf").startswith(settings.MEDIA_URL))

    def test_the_stored_name_is_random_and_tenant_partitioned(self):
        """The uploaded name is attacker-controlled: it can carry separators, be
        absurdly long, collide, or name the patient in a directory listing."""
        instance = SimpleNamespace(tenant_id=7)
        path = attachment_upload_path(instance, "scan.pdf")
        self.assertTrue(path.startswith("tenant-7/"))
        self.assertTrue(path.endswith(".pdf"))
        self.assertNotIn("scan", path)
        self.assertNotEqual(path, attachment_upload_path(instance, "scan.pdf"))

    def test_a_traversing_filename_cannot_escape_the_directory(self):
        instance = SimpleNamespace(tenant_id=7)
        for hostile in ("../../etc/passwd.pdf", "..\\..\\windows\\evil.pdf",
                        "/etc/shadow.pdf"):
            with self.subTest(name=hostile):
                path = attachment_upload_path(instance, hostile)
                self.assertTrue(path.startswith("tenant-7/"))
                self.assertNotIn("..", path)
                self.assertEqual(path.count("/"), 1)


class AttachmentValidationTests(SimpleTestCase):
    """§61: extension, size and MIME validation."""

    def test_an_allowed_type_with_matching_content_passes(self):
        extension, content_type = validate_attachment(upload())
        self.assertEqual(extension, ".pdf")
        self.assertEqual(content_type, "application/pdf")

    def test_a_disallowed_extension_is_refused(self):
        for name in ("evil.exe", "script.js", "shell.sh", "archive.zip", "noext"):
            with self.subTest(name=name):
                with self.assertRaises(ValidationError):
                    validate_attachment(upload(name, PDF_BYTES))

    def test_content_must_match_the_extension(self):
        """The whole point of sniffing: `report.pdf` can be anything at all, and
        the browser's declared Content-Type is supplied by the client."""
        with self.assertRaises(ValidationError):
            validate_attachment(
                upload("report.pdf", b"MZ\x90\x00 this is a windows executable",
                       content_type="application/pdf")
            )

    def test_a_renamed_executable_claiming_to_be_a_png_is_refused(self):
        with self.assertRaises(ValidationError):
            validate_attachment(
                upload("photo.png", b"MZ\x90\x00", content_type="image/png")
            )

    def test_an_oversized_file_is_refused(self):
        with override_settings(MEDICAL_ATTACHMENT_MAX_BYTES=100):
            with self.assertRaises(ValidationError):
                validate_attachment(upload("big.pdf", PDF_BYTES + b"x" * 200))

    def test_an_empty_file_is_refused(self):
        with self.assertRaises(ValidationError):
            validate_attachment(upload("empty.pdf", b""))

    def test_validation_leaves_the_file_readable(self):
        """It reads the head to sniff and the whole file to hash, so it must
        rewind — otherwise the upload is saved truncated or empty."""
        uploaded = upload()
        validate_attachment(uploaded)
        checksum(uploaded)
        uploaded.seek(0)
        self.assertEqual(uploaded.read(), PDF_BYTES)

    def test_the_checksum_is_the_sha256_of_the_content(self):
        self.assertEqual(checksum(upload()), hashlib.sha256(PDF_BYTES).hexdigest())


@override_settings(MEDICAL_ATTACHMENTS_ROOT=Path(tempfile.mkdtemp()) / "attachments")
class AttachmentUploadTests(ClinicalTestBase):
    def setUp(self):
        super().setUp()
        self.client.login(email='doc@t.local', password='pass12345')

    def tearDown(self):
        shutil.rmtree(settings.MEDICAL_ATTACHMENTS_ROOT, ignore_errors=True)
        super().tearDown()

    def post(self, **overrides):
        data = {'title': 'تقرير أشعة', 'category': MedicalAttachment.Category.IMAGING}
        data.update(overrides)
        data.setdefault('file', upload())
        return self.client.post(
            reverse('medical:attachment_upload', args=[self.patient.uuid]), data
        )

    def test_a_doctor_can_upload_a_document(self):
        self.assertEqual(self.post().status_code, 302)
        attachment = MedicalAttachment.all_objects.get()
        self.assertEqual(attachment.patient, self.patient)
        self.assertEqual(attachment.tenant, self.tenant)
        self.assertEqual(attachment.uploaded_by, self.doctor_user)
        self.assertTrue(attachment.serial_number)

    def test_the_derived_columns_are_filled_from_the_upload(self):
        self.post()
        attachment = MedicalAttachment.all_objects.get()
        self.assertEqual(attachment.original_filename, 'report.pdf')
        self.assertEqual(attachment.content_type, 'application/pdf')
        self.assertEqual(attachment.size_bytes, len(PDF_BYTES))
        self.assertEqual(attachment.checksum, hashlib.sha256(PDF_BYTES).hexdigest())

    def test_the_declared_content_type_is_not_trusted(self):
        """The browser sends whatever it likes; the stored type comes from the
        file's own bytes."""
        self.post(file=upload("photo.png", PNG_BYTES, content_type="application/pdf"))
        self.assertEqual(MedicalAttachment.all_objects.get().content_type, "image/png")

    def test_the_file_lands_outside_media_root_with_a_random_name(self):
        self.post()
        attachment = MedicalAttachment.all_objects.get()
        stored = Path(attachment.file.path).resolve()
        self.assertTrue(stored.exists())
        self.assertFalse(str(stored).startswith(str(Path(settings.MEDIA_ROOT).resolve())))
        self.assertNotIn('report', stored.name)
        self.assertIn(f'tenant-{self.tenant.id}', attachment.file.name)

    def test_a_hostile_upload_is_refused_and_nothing_is_written(self):
        response = self.post(file=upload("evil.exe", b"MZ\x90\x00"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(MedicalAttachment.all_objects.exists())

    def test_a_content_mismatch_is_refused(self):
        response = self.post(file=upload("report.pdf", b"MZ\x90\x00 not a pdf"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(MedicalAttachment.all_objects.exists())

    def test_an_oversized_upload_is_refused(self):
        with override_settings(MEDICAL_ATTACHMENT_MAX_BYTES=10):
            response = self.post(file=upload("report.pdf", PDF_BYTES))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(MedicalAttachment.all_objects.exists())

    def test_a_title_is_required(self):
        self.assertEqual(self.post(title='').status_code, 200)
        self.assertFalse(MedicalAttachment.all_objects.exists())


@override_settings(MEDICAL_ATTACHMENTS_ROOT=Path(tempfile.mkdtemp()) / "download")
class AttachmentDownloadTests(ClinicalTestBase):
    """The download view is the only route to the bytes, so every access rule
    has to hold there."""

    def setUp(self):
        super().setUp()
        self.client.login(email='doc@t.local', password='pass12345')
        self.client.post(
            reverse('medical:attachment_upload', args=[self.patient.uuid]),
            {'title': 'تقرير', 'category': MedicalAttachment.Category.LAB_REPORT,
             'file': upload()},
        )
        self.attachment = MedicalAttachment.all_objects.get()
        self.url = reverse('medical:attachment_download', args=[self.attachment.uuid])

    def tearDown(self):
        shutil.rmtree(settings.MEDICAL_ATTACHMENTS_ROOT, ignore_errors=True)
        super().tearDown()

    def test_a_doctor_gets_the_file_back_intact(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), PDF_BYTES)

    def test_it_is_served_as_an_attachment_with_the_detected_type(self):
        """Serving a user-supplied type inline is how an upload becomes stored
        XSS; nosniff stops a browser second-guessing the type we set."""
        response = self.client.get(self.url)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response["Content-Disposition"].startswith("attachment;"))
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_an_anonymous_visitor_gets_nothing(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertNotEqual(response.status_code, 200)

    def test_reception_cannot_download_a_medical_document(self):
        self.client.login(email='rec@t.local', password='pass12345')
        self.assertNotEqual(self.client.get(self.url).status_code, 200)

    def test_a_user_with_no_role_cannot_download(self):
        User.objects.create_user(
            username='norole5', email='norole5@t.local', password='pass12345',
            tenant=self.tenant, branch=self.branch,
        )
        self.client.login(email='norole5@t.local', password='pass12345')
        self.assertNotEqual(self.client.get(self.url).status_code, 200)

    def test_documents_are_absent_from_receptions_patient_page(self):
        self.client.login(email='rec@t.local', password='pass12345')
        response = self.client.get(
            reverse('patients:patient_detail', args=[self.patient.uuid])
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'تقرير')


@override_settings(MEDICAL_ATTACHMENTS_ROOT=Path(tempfile.mkdtemp()) / "isolation")
class AttachmentIsolationTests(ClinicalIsolationTests):
    def tearDown(self):
        shutil.rmtree(settings.MEDICAL_ATTACHMENTS_ROOT, ignore_errors=True)
        super().tearDown()

    def test_another_tenants_doctor_cannot_download_the_file(self):
        """The tenant boundary has to hold for the bytes, not just the row."""
        with tenant_context(self.tenant):
            attachment = MedicalAttachment.all_objects.create(
                tenant=self.tenant, patient=self.patient, branch=self.branch,
                title='Ours', content_type='application/pdf',
                file=ContentFile(PDF_BYTES, name='x.pdf'),
            )
        self.client.login(email='otherdoc@t.local', password='pass12345')
        response = self.client.get(
            reverse('medical:attachment_download', args=[attachment.uuid])
        )
        self.assertEqual(response.status_code, 404)

    def test_another_tenants_doctor_cannot_upload_against_the_patient(self):
        self.client.login(email='otherdoc@t.local', password='pass12345')
        response = self.client.get(
            reverse('medical:attachment_upload', args=[self.patient.uuid])
        )
        self.assertEqual(response.status_code, 404)
