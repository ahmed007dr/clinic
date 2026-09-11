"""First-visit intake from the front desk.

Covers what the wizard sends — personal, visit, history, referral, consent —
and the rules around it: required fields, structured history, the referral
distinctions, doctor/specialty consistency, duplicates, clinic scoping, and
that Reception can enter a medical history without being shown it back.
"""

import copy

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import ClinicRole
from branches.models import Branch
from employees.models import Employee, EmployeeType, Specialization
from medical.models import Allergy, PatientCondition, PatientIntake, PatientMedicalProfile
from patients.models import Patient
from subscriptions.models import Subscription
from tenants.context import tenant_context
from tenants.testing import link_doctor
from tenants.models import Tenant

User = get_user_model()
PASSWORD = "pass12345"

BASE = {
    "personal": {"name": "Sara Ahmed", "gender": "female", "phone1": "01011112222",
                 "birth_date": "1990-05-01"},
    "visit": {"case_type": "consultation", "reason_for_visit": "Rash on both arms",
              "symptoms": "itching at night", "symptom_onset": "weeks"},
    "consent": {"data_processing": True, "contact_by_whatsapp": True},
}


def body(**sections):
    data = copy.deepcopy(BASE)
    for key, value in sections.items():
        if isinstance(value, dict) and isinstance(data.get(key), dict):
            data[key].update(value)
        else:
            data[key] = value
    return data


class IntakeTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            self.roles = {n: ClinicRole.all_objects.get_or_create(tenant=self.tenant, name=n)[0]
                          for n in ("Owner", "Admin", "Reception", "Doctor")}
            self.a = Branch.all_objects.create(tenant=self.tenant, name="Clinic A", code="IA")
            self.b = Branch.all_objects.create(tenant=self.tenant, name="Clinic B", code="IB")
            doctor_type, _ = EmployeeType.all_objects.get_or_create(tenant=self.tenant, name="Doctor")
            nurse_type = EmployeeType.all_objects.create(tenant=self.tenant, name="Nurse")
            self.derm = Specialization.all_objects.create(tenant=self.tenant, name="Dermatology")
            self.peds = Specialization.all_objects.create(tenant=self.tenant, name="Pediatrics")
            self.dr_a = Employee.all_objects.create(tenant=self.tenant, name="Dr A", branch=self.a,
                                                    national_id="1", salary_value=1, employee_type=doctor_type)
            self.dr_a.specializations.add(self.derm)
            self.dr_b = Employee.all_objects.create(tenant=self.tenant, name="Dr B", branch=self.b,
                                                    national_id="2", salary_value=1, employee_type=doctor_type)
            self.nurse = Employee.all_objects.create(tenant=self.tenant, name="Nurse", branch=self.a,
                                                     national_id="3", salary_value=1, employee_type=nurse_type)
        self.reception = self.user("reception", "Reception", self.a)
        self.doctor = self.user("doctor", "Doctor", self.a)
        self.owner = self.user("owner", "Owner", self.a)
        self.login(self.reception)

    def user(self, name, role, branch):
        return User.objects.create_user(username=name, email=f"{name}@intake.local", password=PASSWORD,
                                        tenant=self.tenant, role=self.roles[role], branch=branch)

    def login(self, user):
        self.client.logout()
        self.client.login(email=user.email, password=PASSWORD)

    def register(self, data):
        return self.client.post(reverse("api:intake-register"), data, content_type="application/json")

    def patient(self, uuid):
        with tenant_context(self.tenant):
            return Patient.all_objects.get(uuid=uuid)

    # ------------------------------------------------------------ success

    def test_a_minimal_registration_creates_the_patient_and_the_intake(self):
        response = self.register(body())
        self.assertEqual(response.status_code, 201, response.content)
        patient = self.patient(response.json()["patient"]["uuid"])
        self.assertEqual(patient.branch_id, self.a.pk)  # Reception registers into their clinic
        self.assertIsNotNone(patient.consent_data_processing_at)
        self.assertTrue(patient.contact_by_whatsapp)
        self.assertFalse(patient.needs_review)
        with tenant_context(self.tenant):
            intake = PatientIntake.all_objects.get(patient=patient)
            self.assertEqual(intake.reason_for_visit, "Rash on both arms")
            self.assertEqual(intake.symptom_onset, "weeks")
            # The optional history step was skipped: no profile invented.
            self.assertFalse(PatientMedicalProfile.all_objects.filter(patient=patient).exists())

    def test_the_response_does_not_echo_medical_data_to_reception(self):
        response = self.register(body(history={"current_medications": "metformin"}))
        self.assertNotIn("metformin", response.content.decode())

    def test_history_is_stored_structured(self):
        response = self.register(body(history={
            "smoking_status": "current", "current_medications": "metformin 500",
            "conditions": [
                {"condition": "diabetes", "current_treatment": "metformin"},
                {"condition": "other", "other_name": "Gout"},
            ],
            "allergies": [{"substance": "Penicillin", "severity": "severe"}],
        }))
        self.assertEqual(response.status_code, 201, response.content)
        patient = self.patient(response.json()["patient"]["uuid"])
        with tenant_context(self.tenant):
            profile = PatientMedicalProfile.all_objects.get(patient=patient)
            self.assertEqual(profile.smoking_status, "current")
            self.assertTrue(profile.conditions_reviewed)
            codes = set(PatientCondition.all_objects.filter(patient=patient).values_list("condition", flat=True))
            self.assertEqual(codes, {"diabetes", "other"})
            self.assertTrue(Allergy.all_objects.filter(patient=patient, substance="Penicillin").exists())

    def test_referral_and_recommended_doctor_are_kept_apart(self):
        response = self.register(body(
            referral={"referral_source": "doctor_referral", "referring_doctor_name": "Dr Outside",
                      "recommended_doctor": str(self.dr_a.uuid)},
            visit={"requested_doctor": str(self.dr_a.uuid), "specialization": str(self.derm.uuid)},
        ))
        self.assertEqual(response.status_code, 201, response.content)
        patient = self.patient(response.json()["patient"]["uuid"])
        self.assertEqual(patient.referral_source, "doctor_referral")
        self.assertEqual(patient.referring_doctor_name, "Dr Outside")
        self.assertEqual(patient.recommended_doctor_id, self.dr_a.pk)
        with tenant_context(self.tenant):
            intake = PatientIntake.all_objects.get(patient=patient)
        self.assertEqual(intake.requested_doctor_id, self.dr_a.pk)
        self.assertEqual(intake.specialization_id, self.derm.pk)

    def test_an_existing_patient_can_be_named_as_the_referrer(self):
        with tenant_context(self.tenant):
            friend = Patient.all_objects.create(tenant=self.tenant, name="Old Friend", branch=self.a)
        response = self.register(body(referral={"referral_source": "existing_patient",
                                                "referred_by_patient": str(friend.uuid)}))
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self.patient(response.json()["patient"]["uuid"]).referred_by_patient_id, friend.pk)

    def test_a_specialty_without_a_doctor_is_fine(self):
        response = self.register(body(visit={"specialization": str(self.peds.uuid)}))
        self.assertEqual(response.status_code, 201, response.content)
        with tenant_context(self.tenant):
            intake = PatientIntake.all_objects.get(patient__uuid=response.json()["patient"]["uuid"])
        self.assertEqual(intake.specialization_id, self.peds.pk)
        self.assertIsNone(intake.requested_doctor_id)

    # ------------------------------------------------------------ validation

    def test_required_fields_come_back_addressed_to_their_step(self):
        data = body()
        del data["personal"]["name"]
        data["personal"]["phone1"] = ""
        data["visit"]["reason_for_visit"] = ""
        response = self.register(data)
        self.assertEqual(response.status_code, 400)
        errors = response.json()
        self.assertIn("name", errors["personal"])
        self.assertIn("phone1", errors["personal"])
        self.assertIn("reason_for_visit", errors["visit"])

    def test_consent_to_store_medical_data_is_required(self):
        response = self.register(body(consent={"data_processing": False}))
        self.assertEqual(response.status_code, 400)
        self.assertIn("data_processing", response.json()["consent"])

    def test_other_condition_needs_a_name_and_conditions_cannot_repeat(self):
        response = self.register(body(history={"conditions": [{"condition": "other"}]}))
        self.assertEqual(response.status_code, 400)
        response = self.register(body(history={"conditions": [{"condition": "diabetes"}, {"condition": "diabetes"}]}))
        self.assertEqual(response.status_code, 400)

    def test_a_doctor_referral_needs_the_referring_doctors_name(self):
        response = self.register(body(referral={"referral_source": "doctor_referral"}))
        self.assertEqual(response.status_code, 400)
        self.assertIn("referring_doctor_name", response.json()["referral"])

    def test_the_doctor_must_match_the_specialty_work_here_and_be_a_doctor(self):
        wrong_specialty = self.register(body(visit={"requested_doctor": str(self.dr_a.uuid),
                                                    "specialization": str(self.peds.uuid)}))
        self.assertEqual(wrong_specialty.status_code, 400)
        other_clinic = self.register(body(visit={"requested_doctor": str(self.dr_b.uuid)}))
        self.assertEqual(other_clinic.status_code, 400)
        not_a_doctor = self.register(body(visit={"requested_doctor": str(self.nurse.uuid)}))
        self.assertEqual(not_a_doctor.status_code, 400)

    def test_a_birth_date_in_the_future_is_refused(self):
        response = self.register(body(personal={"birth_date": "2999-01-01"}))
        self.assertEqual(response.status_code, 400)

    # ------------------------------------------------------------ duplicates

    def test_a_duplicate_phone_is_flagged_and_can_be_overridden(self):
        with tenant_context(self.tenant):
            existing = Patient.all_objects.create(tenant=self.tenant, name="Sara A.", branch=self.a,
                                                  phone1="010 1111 2222")
        response = self.register(body())
        self.assertEqual(response.status_code, 409)
        self.assertEqual([d["uuid"] for d in response.json()["duplicates"]], [str(existing.uuid)])
        confirmed = self.register(body(confirm_new=True))
        self.assertEqual(confirmed.status_code, 201)

    def test_a_duplicate_in_another_clinic_is_counted_not_shown(self):
        with tenant_context(self.tenant):
            Patient.all_objects.create(tenant=self.tenant, name="Elsewhere", branch=self.b, phone1="01011112222")
        response = self.register(body())
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["duplicates"], [])
        self.assertEqual(response.json()["other_clinics"], 1)
        self.assertNotIn("Elsewhere", response.content.decode())

    # ------------------------------------------------------------ permissions

    def test_reception_enters_history_but_only_clinicians_read_it(self):
        response = self.register(body(history={"conditions": [{"condition": "hypertension"}]}))
        uuid = response.json()["patient"]["uuid"]
        self.assertEqual(self.client.get(reverse("api:patient-history", args=[uuid])).status_code, 403)
        with tenant_context(self.tenant):
            link_doctor(self.doctor, Patient.all_objects.get(uuid=uuid))
        self.login(self.doctor)
        history = self.client.get(reverse("api:patient-history", args=[uuid]))
        self.assertEqual(history.status_code, 200)
        self.assertEqual([c["condition"] for c in history.json()["conditions"]], ["hypertension"])

    def test_reception_registers_only_into_their_own_clinic(self):
        response = self.register(body(personal={"branch": str(self.b.uuid)}))
        self.assertEqual(response.status_code, 400)
        self.login(self.owner)
        response = self.register(body(personal={"branch": str(self.b.uuid)}))
        self.assertEqual(response.status_code, 201, response.content)

    def test_a_doctor_does_not_register_patients(self):
        self.login(self.doctor)
        self.assertEqual(self.register(body()).status_code, 403)

    def test_a_doctor_from_another_group_is_not_found(self):
        other = Tenant.objects.create(name="Other group", slug="other-intake", status="active")
        with tenant_context(other):
            branch = Branch.all_objects.create(tenant=other, name="X", code="X")
            foreign = Employee.all_objects.create(tenant=other, name="Foreign Dr", branch=branch,
                                                  national_id="9", salary_value=1)
        response = self.register(body(visit={"requested_doctor": str(foreign.uuid)}))
        self.assertEqual(response.status_code, 400)
        self.assertIn("requested_doctor", response.json()["visit"])

    def test_the_plan_limit_still_applies(self):
        with tenant_context(self.tenant):
            plan = Subscription.all_objects.filter(tenant=self.tenant, status="active").first().plan
            plan.max_patients = Patient.all_objects.filter(tenant=self.tenant, needs_review=False).count()
            plan.save(update_fields=["max_patients"])
        self.assertEqual(self.register(body()).status_code, 403)
