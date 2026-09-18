"""The clinical record's rules, through the API the React app uses.

These carry the guarantees that used to be tested against the old server-rendered
clinical screens (`medical/tests.py`): who may read and write which record, that
another clinic's records are unreachable, the serial numbers, the money maths of
sessions and procedures, the lab-result flow, and the private storage of
attachments. The screens are gone; the rules are not.
"""

import io
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from branches.models import Branch
from employees.models import Employee, EmployeeType
from medical.models import (
    LabResult,
    Prescription,
    Procedure,
    TreatmentPlan,
    TreatmentSession,
    Visit,
)
from patients.models import Patient
from services.models import Service
from tenants.context import tenant_context
from tenants.models import Tenant
from tenants.provisioning import provision_tenant_defaults
from tenants.testing import act_as_tenant

User = get_user_model()

PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"


def as_json(client, method, url, body=None):
    return getattr(client, method)(url, body or {}, content_type="application/json")


class ClinicalBase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        act_as_tenant(self, self.tenant)
        provision_tenant_defaults(self.tenant)
        self.branch = Branch.all_objects.create(tenant=self.tenant, name="Main", code="MN")

        def role(name):
            return ClinicRole.all_objects.get(tenant=self.tenant, name=name)

        def make(username, role_name):
            return User.objects.create_user(
                username=username, email=f"{username}@cl.local", password="pass12345",
                tenant=self.tenant, role=role(role_name), branch=self.branch,
            )

        self.doctor_user = make("doc", "Doctor")
        self.admin_user = make("admin", "Admin")
        self.reception_user = make("rec", "Reception")
        self.doctor = Employee.all_objects.create(
            tenant=self.tenant, name="Dr Test", branch=self.branch,
            employee_type=EmployeeType.all_objects.get(tenant=self.tenant, name="Doctor"),
            national_id="DOC-1", salary_value=0,
        )
        self.doctor_user.employee = self.doctor
        self.doctor_user.save(update_fields=["employee"])
        self.patient = Patient.all_objects.create(tenant=self.tenant, name="Test Patient", branch=self.branch)
        self.visit = Visit.all_objects.create(
            tenant=self.tenant, patient=self.patient, branch=self.branch, doctor=self.doctor,
            chief_complaint="صداع", diagnosis="CONFIDENTIAL DIAGNOSIS",
        )
        self.service = Service.all_objects.create(tenant=self.tenant, name="Laser", base_price=200)

    def login(self, username):
        self.client.logout()
        self.assertTrue(self.client.login(email=f"{username}@cl.local", password="pass12345"))

    def post(self, name, body=None, **kw):
        return as_json(self.client, "post", reverse(name, **kw), body)


# --------------------------------------------------------------------- access


class ClinicalAccessTests(ClinicalBase):
    def collections(self):
        return ["api:visit-list", "api:prescription-list", "api:treatmentplan-list",
                "api:treatmentsession-list", "api:procedure-list", "api:labresult-list",
                "api:attachment-list"]

    def test_doctor_and_admin_read_the_clinical_record(self):
        for who in ("doc", "admin"):
            self.login(who)
            for name in self.collections():
                with self.subTest(who=who, endpoint=name):
                    self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_reception_is_blocked_from_every_clinical_endpoint(self):
        self.login("rec")
        for name in self.collections():
            with self.subTest(endpoint=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)
        self.assertEqual(self.client.get(reverse("api:visit-detail", args=[self.visit.uuid])).status_code, 403)

    def test_reception_cannot_record_a_visit(self):
        self.login("rec")
        response = self.post("api:visit-list", {"patient": str(self.patient.uuid)})
        self.assertEqual(response.status_code, 403)

    def test_a_user_with_no_role_gets_nothing(self):
        User.objects.create_user(username="norole", email="norole@cl.local", password="pass12345",
                                 tenant=self.tenant, branch=self.branch)
        self.login("norole")
        for name in self.collections():
            with self.subTest(endpoint=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)

    def test_the_diagnosis_never_reaches_receptions_view_of_the_patient(self):
        self.login("rec")
        timeline = self.client.get(reverse("api:patient-timeline", args=[self.patient.uuid]))
        self.assertEqual(timeline.status_code, 200)
        self.assertNotIn("CONFIDENTIAL DIAGNOSIS", timeline.content.decode())
        detail = self.client.get(reverse("api:patient-detail", args=[self.patient.uuid]))
        self.assertNotIn("CONFIDENTIAL DIAGNOSIS", detail.content.decode())

    def test_a_patient_with_records_cannot_be_deleted(self):
        self.login("admin")
        response = self.client.delete(reverse("api:patient-detail", args=[self.patient.uuid]))
        self.assertEqual(response.status_code, 409)
        self.assertIn("السجلات الطبية", response.json()["detail"])
        with tenant_context(self.tenant):
            self.assertTrue(Patient.all_objects.filter(pk=self.patient.pk).exists())
            self.assertTrue(Visit.all_objects.filter(pk=self.visit.pk).exists())


class ClinicalIsolationTests(ClinicalBase):
    """Another clinic's doctor reaches none of this clinic's records."""

    def setUp(self):
        super().setUp()
        with tenant_context(self.tenant):
            self.plan = TreatmentPlan.all_objects.create(
                tenant=self.tenant, patient=self.patient, doctor=self.doctor, branch=self.branch,
                title="Plan", planned_sessions=4,
            )
            self.session = TreatmentSession.all_objects.create(
                tenant=self.tenant, plan=self.plan, patient=self.patient, branch=self.branch,
                sequence=1, quantity=1, unit_price=100,
            )
            self.procedure = Procedure.all_objects.create(
                tenant=self.tenant, visit=self.visit, patient=self.patient, doctor=self.doctor,
                branch=self.branch, name="Excision", quantity=1, unit_price=100,
            )
            self.lab = LabResult.all_objects.create(
                tenant=self.tenant, patient=self.patient, branch=self.branch, test_name="CBC",
            )
            self.prescription = Prescription.all_objects.create(
                tenant=self.tenant, visit=self.visit, patient=self.patient, doctor=self.doctor,
            )

        self.rival = Tenant.objects.create(name="Rival", slug="rival-clin", status=Tenant.Status.ACTIVE)
        provision_tenant_defaults(self.rival)
        with tenant_context(self.rival):
            rival_branch = Branch.all_objects.create(tenant=self.rival, name="R", code="R")
            rival_doctor = Employee.all_objects.create(
                tenant=self.rival, name="Dr Rival", branch=rival_branch,
                employee_type=EmployeeType.all_objects.get(tenant=self.rival, name="Doctor"),
                national_id="DOC-R", salary_value=0,
            )
        self.rival_user = User.objects.create_user(
            username="rival", email="rival@cl.local", password="pass12345", tenant=self.rival,
            role=ClinicRole.all_objects.get(tenant=self.rival, name="Admin"), branch=rival_branch,
            employee=rival_doctor,
        )

    def test_another_clinics_user_cannot_open_any_record(self):
        self.login("rival")
        for name, obj in (("api:visit-detail", self.visit), ("api:prescription-detail", self.prescription),
                          ("api:treatmentplan-detail", self.plan), ("api:treatmentsession-detail", self.session),
                          ("api:procedure-detail", self.procedure), ("api:labresult-detail", self.lab)):
            with self.subTest(endpoint=name):
                self.assertEqual(self.client.get(reverse(name, args=[obj.uuid])).status_code, 404)

    def test_another_clinics_user_cannot_acknowledge_a_result(self):
        self.login("rival")
        response = self.post("api:labresult-acknowledge", args=[self.lab.uuid])
        self.assertEqual(response.status_code, 404)
        self.lab.refresh_from_db()
        self.assertIsNone(self.lab.acknowledged_at)

    def test_another_clinics_user_cannot_record_against_this_clinics_patient(self):
        self.login("rival")
        for name, body in (
            ("api:visit-list", {"patient": str(self.patient.uuid)}),
            ("api:treatmentplan-list", {"patient": str(self.patient.uuid), "title": "x", "planned_sessions": 2}),
            ("api:labresult-list", {"patient": str(self.patient.uuid), "test_name": "CBC"}),
        ):
            with self.subTest(endpoint=name):
                response = self.post(name, body)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn("patient", response.json())


# -------------------------------------------------------------- prescriptions


class PrescriptionTests(ClinicalBase):
    def issue(self, items, **extra):
        return self.post("api:prescription-list", {"visit": str(self.visit.uuid), "items": items, **extra})

    def med(self, name="Paracetamol"):
        return {"medication": name, "dosage": "500mg", "frequency": "x3", "duration": "5 days"}

    def test_a_doctor_issues_a_prescription_with_medications_and_it_gets_a_serial(self):
        self.login("doc")
        response = self.issue([self.med("A"), self.med("B")])
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(len(body["items"]), 2)
        self.assertTrue(body["serial_number"])
        self.assertEqual(body["patient"], str(self.patient.uuid))
        # Signed with the issuing doctor's own name.
        self.assertEqual(body["doctor_name"], "Dr Test")

    def test_more_than_three_medications_are_accepted(self):
        self.login("doc")
        response = self.issue([self.med(f"M{i}") for i in range(6)])
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(len(response.json()["items"]), 6)

    def test_a_prescription_needs_at_least_one_medication(self):
        self.login("doc")
        self.assertEqual(self.issue([]).status_code, 400)
        with tenant_context(self.tenant):
            self.assertEqual(Prescription.all_objects.count(), 0)

    def test_reception_cannot_issue_or_read_a_prescription(self):
        self.login("rec")
        self.assertEqual(self.issue([self.med()]).status_code, 403)
        self.assertEqual(self.client.get(reverse("api:prescription-list")).status_code, 403)

    def test_the_printable_sheet_lists_the_medications(self):
        self.login("doc")
        uuid = self.issue([self.med("UniqueMedName")]).json()["uuid"]
        page = self.client.get(reverse("medical:prescription_print", args=[uuid]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "UniqueMedName")

    def test_reception_prints_for_the_doctor_to_sign_but_reads_nothing_else(self):
        self.login("doc")
        uuid = self.issue([self.med()]).json()["uuid"]
        self.login("rec")
        self.assertEqual(self.client.get(reverse("medical:prescription_print", args=[uuid])).status_code, 200)
        self.assertEqual(self.client.get(reverse("api:prescription-detail", args=[uuid])).status_code, 403)

    def test_another_clinics_user_cannot_print_it(self):
        self.login("doc")
        uuid = self.issue([self.med()]).json()["uuid"]
        rival = Tenant.objects.create(name="Rv", slug="rv-print", status=Tenant.Status.ACTIVE)
        provision_tenant_defaults(rival)
        with tenant_context(rival):
            branch = Branch.all_objects.create(tenant=rival, name="R", code="R")
        User.objects.create_user(username="rvp", email="rvp@cl.local", password="pass12345", tenant=rival,
                                 role=ClinicRole.all_objects.get(tenant=rival, name="Admin"), branch=branch)
        self.login("rvp")
        self.assertEqual(self.client.get(reverse("medical:prescription_print", args=[uuid])).status_code, 404)

    def test_a_medication_matching_a_recorded_allergy_warns_but_still_saves(self):
        from medical.models import Allergy

        with tenant_context(self.tenant):
            Allergy.all_objects.create(tenant=self.tenant, patient=self.patient, substance="Penicillin",
                                       reaction="rash", severity="moderate")
        self.login("doc")
        response = self.issue([self.med("penicillin V")])
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(response.json()["allergy_warnings"])
        clean = self.issue([self.med("Aspirin")])
        self.assertFalse(clean.json()["allergy_warnings"])


# ------------------------------------------------------------ treatment plans


class TreatmentPlanTests(ClinicalBase):
    def plan(self, **extra):
        return self.post("api:treatmentplan-list", {
            "patient": str(self.patient.uuid), "title": "Laser course", "planned_sessions": 6,
            "service": str(self.service.uuid), **extra,
        })

    def test_a_doctor_creates_a_plan_and_it_gets_a_serial(self):
        self.login("doc")
        response = self.plan()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(response.json()["serial_number"].endswith("001"))

    def test_serials_are_per_clinic_and_restart(self):
        self.login("doc")
        self.plan()
        second = self.plan(title="Second").json()["serial_number"]
        self.assertTrue(second.endswith("002"))
        rival = Tenant.objects.create(name="Rv2", slug="rv-plan", status=Tenant.Status.ACTIVE)
        provision_tenant_defaults(rival)
        with tenant_context(rival):
            branch = Branch.all_objects.create(tenant=rival, name="R", code="R")
            patient = Patient.all_objects.create(tenant=rival, name="RP", branch=branch)
            plan = TreatmentPlan.all_objects.create(
                tenant=rival, patient=patient, branch=branch, title="x", planned_sessions=1
            )
        self.assertTrue(plan.serial_number.endswith("001"))

    def test_the_branch_defaults_to_the_patients(self):
        self.login("doc")
        body = self.plan().json()
        with tenant_context(self.tenant):
            self.assertEqual(TreatmentPlan.all_objects.get(uuid=body["uuid"]).branch_id, self.branch.pk)

    def test_a_plan_needs_a_title_and_at_least_one_session(self):
        self.login("doc")
        self.assertEqual(self.plan(title="").status_code, 400)
        self.assertEqual(self.plan(planned_sessions=0).status_code, 400)

    def test_reception_cannot_touch_plans(self):
        self.login("rec")
        self.assertEqual(self.plan().status_code, 403)

    def test_the_plan_counts_completed_sessions_rather_than_storing_them(self):
        self.login("doc")
        plan_uuid = self.plan().json()["uuid"]
        for status in ("completed", "completed", "scheduled"):
            self.post("api:treatmentsession-list", {
                "plan": plan_uuid, "patient": str(self.patient.uuid), "status": status,
                "quantity": 1, "unit_price": "100.00",
            })
        plan = self.client.get(reverse("api:treatmentplan-detail", args=[plan_uuid])).json()
        self.assertEqual(plan["completed_sessions"], 2)
        # Cancelling one changes the count; nothing was stored to go stale.
        sessions = self.client.get(reverse("api:treatmentsession-list"), {"plan": plan_uuid}).json()["results"]
        done = next(s for s in sessions if s["status"] == "completed")
        as_json(self.client, "patch", reverse("api:treatmentsession-detail", args=[done["uuid"]]),
                {"status": "cancelled"})
        plan = self.client.get(reverse("api:treatmentplan-detail", args=[plan_uuid])).json()
        self.assertEqual(plan["completed_sessions"], 1)


class TreatmentSessionTests(ClinicalBase):
    def setUp(self):
        super().setUp()
        with tenant_context(self.tenant):
            self.plan = TreatmentPlan.all_objects.create(
                tenant=self.tenant, patient=self.patient, doctor=self.doctor, branch=self.branch,
                service=self.service, title="Course", planned_sessions=6,
            )
        self.login("admin")

    def session(self, **extra):
        return self.post("api:treatmentsession-list", {
            "plan": str(self.plan.uuid), "patient": str(self.patient.uuid),
            "quantity": 1, "unit_price": "100.00", **extra,
        })

    def test_a_session_can_be_recorded_and_is_numbered_within_its_plan(self):
        first, second = self.session(), self.session()
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual([first.json()["sequence"], second.json()["sequence"]], [1, 2])

    def test_numbering_restarts_for_a_different_plan(self):
        self.session()
        with tenant_context(self.tenant):
            other = TreatmentPlan.all_objects.create(
                tenant=self.tenant, patient=self.patient, branch=self.branch, title="Other", planned_sessions=2
            )
        body = self.post("api:treatmentsession-list", {
            "plan": str(other.uuid), "patient": str(self.patient.uuid), "quantity": 1, "unit_price": "10",
        }).json()
        self.assertEqual(body["sequence"], 1)

    def test_the_session_takes_the_plans_service(self):
        body = self.session().json()
        self.assertEqual(body["service"], str(self.service.uuid))

    def test_quantity_priced_sessions_multiply_and_a_discount_reduces_the_total(self):
        body = self.session(quantity=25, unit_price="10.00", discount="50.00").json()
        with tenant_context(self.tenant):
            row = TreatmentSession.all_objects.get(uuid=body["uuid"])
        self.assertEqual(row.gross_amount, Decimal("250.00"))
        self.assertEqual(row.total_amount, Decimal("200.00"))

    def test_a_discount_larger_than_the_line_is_refused(self):
        response = self.session(quantity=2, unit_price="10.00", discount="25.00")
        self.assertEqual(response.status_code, 400, response.content)
        with tenant_context(self.tenant):
            self.assertEqual(TreatmentSession.all_objects.count(), 0)

    def test_negative_money_and_zero_quantity_are_refused(self):
        self.assertEqual(self.session(unit_price="-5.00").status_code, 400)
        self.assertEqual(self.session(discount="-1.00").status_code, 400)
        self.assertEqual(self.session(quantity=0).status_code, 400)

    def test_a_session_must_belong_to_its_plans_patient(self):
        other = Patient.all_objects.create(tenant=self.tenant, name="Other", branch=self.branch)
        response = self.post("api:treatmentsession-list", {
            "plan": str(self.plan.uuid), "patient": str(other.uuid), "quantity": 1, "unit_price": "10",
        })
        self.assertEqual(response.status_code, 400)

    def test_reception_cannot_record_or_read_sessions(self):
        self.login("rec")
        self.assertEqual(self.session().status_code, 403)
        self.assertEqual(self.client.get(reverse("api:treatmentsession-list")).status_code, 403)


# ----------------------------------------------------------------- procedures


class ProcedureTests(ClinicalBase):
    def setUp(self):
        super().setUp()
        self.login("admin")

    def procedure(self, **extra):
        return self.post("api:procedure-list", {
            "visit": str(self.visit.uuid), "patient": str(self.patient.uuid), "name": "Excision",
            "quantity": 1, "unit_price": "100.00", **extra,
        })

    def test_procedure_serials_are_a_separate_sequence_from_visits(self):
        first = self.procedure().json()
        second = self.procedure(name="Other").json()
        self.assertTrue(first["serial_number"].endswith("001"))
        self.assertTrue(second["serial_number"].endswith("002"))
        # A further visit is numbered from the visits' own count (this clinic's
        # first visit already took 001), not from the procedures'.
        with tenant_context(self.tenant):
            visit = Visit.all_objects.create(tenant=self.tenant, patient=self.patient, branch=self.branch)
        self.assertTrue(visit.serial_number.endswith("002"))

    def test_a_procedure_needs_a_name_but_not_a_service(self):
        self.assertEqual(self.procedure(name="").status_code, 400)
        self.assertEqual(self.procedure().status_code, 201)

    def test_the_doctor_and_branch_default_to_the_visits(self):
        body = self.procedure().json()
        self.assertEqual(body["doctor"], str(self.doctor.uuid))
        with tenant_context(self.tenant):
            self.assertEqual(Procedure.all_objects.get(uuid=body["uuid"]).branch_id, self.branch.pk)

    def test_money_is_computed_from_quantity_and_discount(self):
        body = self.procedure(quantity=3, unit_price="40.00", discount="20.00").json()
        with tenant_context(self.tenant):
            row = Procedure.all_objects.get(uuid=body["uuid"])
        self.assertEqual((row.gross_amount, row.total_amount), (Decimal("120.00"), Decimal("100.00")))

    def test_a_discount_larger_than_the_line_and_negative_money_are_refused(self):
        self.assertEqual(self.procedure(quantity=1, unit_price="10.00", discount="15.00").status_code, 400)
        self.assertEqual(self.procedure(unit_price="-1.00").status_code, 400)
        self.assertEqual(self.procedure(quantity=0).status_code, 400)

    def test_complications_are_recordable_and_flagged(self):
        flagged = self.procedure(complications="Bleeding").json()
        clean = self.procedure(name="Other").json()
        with tenant_context(self.tenant):
            self.assertTrue(Procedure.all_objects.get(uuid=flagged["uuid"]).had_complications)
            self.assertFalse(Procedure.all_objects.get(uuid=clean["uuid"]).had_complications)

    def test_an_aborted_procedure_is_distinguishable_from_a_cancelled_one(self):
        aborted = self.procedure(status="aborted").json()
        cancelled = self.procedure(name="Other", status="cancelled").json()
        self.assertNotEqual(aborted["status"], cancelled["status"])
        self.assertNotEqual(aborted["status_label"], cancelled["status_label"])

    def test_reception_cannot_record_or_read_procedures(self):
        self.login("rec")
        self.assertEqual(self.procedure().status_code, 403)
        self.assertEqual(self.client.get(reverse("api:procedure-list")).status_code, 403)


# ---------------------------------------------------------------- lab results


class LabResultTests(ClinicalBase):
    def lab(self, **extra):
        return self.post("api:labresult-list", {
            "patient": str(self.patient.uuid), "test_name": "CBC", **extra,
        })

    def test_a_doctor_orders_a_test_and_it_gets_a_serial(self):
        self.login("doc")
        response = self.lab()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(response.json()["serial_number"])

    def test_a_test_name_is_required(self):
        self.login("doc")
        self.assertEqual(self.lab(test_name="").status_code, 400)

    def test_a_result_can_be_qualitative_not_just_numeric(self):
        self.login("doc")
        for value in ("7.2", "<0.01", "إيجابي", "لم يُكتشف"):
            with self.subTest(value=value):
                response = self.lab(value=value, status="resulted")
                self.assertEqual(response.status_code, 201, response.content)
                self.assertEqual(response.json()["value"], value)

    def test_a_resulted_test_must_carry_a_value(self):
        self.login("doc")
        response = self.lab(status="resulted")
        self.assertEqual(response.status_code, 400, response.content)

    def test_resulted_at_is_stamped_when_the_result_arrives(self):
        self.login("doc")
        ordered = self.lab().json()
        self.assertIsNone(ordered["resulted_at"])
        updated = as_json(self.client, "patch", reverse("api:labresult-detail", args=[ordered["uuid"]]),
                          {"value": "5", "status": "resulted"}).json()
        self.assertIsNotNone(updated["resulted_at"])

    def test_who_needs_attention(self):
        def row(**kw):
            with tenant_context(self.tenant):
                return LabResult.all_objects.create(tenant=self.tenant, patient=self.patient,
                                                    branch=self.branch, test_name="T", **kw)

        self.assertTrue(row(flag="abnormal", status="resulted", value="9").needs_attention)
        self.assertTrue(row(flag="critical", status="resulted", value="9").needs_attention)
        self.assertFalse(row(flag="normal", status="resulted", value="5").needs_attention)
        self.assertFalse(row(flag="abnormal", status="ordered").needs_attention)

    def test_acknowledging_clears_the_need_for_attention_and_keeps_the_first_signature(self):
        self.login("doc")
        with tenant_context(self.tenant):
            lab = LabResult.all_objects.create(tenant=self.tenant, patient=self.patient, branch=self.branch,
                                               test_name="T", flag="critical", status="resulted", value="9")
        self.assertTrue(lab.needs_attention)
        first = self.post("api:labresult-acknowledge", args=[lab.uuid])
        self.assertEqual(first.status_code, 200, first.content)
        lab.refresh_from_db()
        self.assertFalse(lab.needs_attention)
        signed = (lab.acknowledged_by_id, lab.acknowledged_at)
        self.login("admin")
        self.post("api:labresult-acknowledge", args=[lab.uuid])
        lab.refresh_from_db()
        self.assertEqual((lab.acknowledged_by_id, lab.acknowledged_at), signed)

    def test_acknowledgement_cannot_happen_on_a_get_or_as_a_side_effect_of_an_edit(self):
        self.login("doc")
        with tenant_context(self.tenant):
            lab = LabResult.all_objects.create(tenant=self.tenant, patient=self.patient, branch=self.branch,
                                               test_name="T", flag="abnormal", status="resulted", value="9")
        self.assertEqual(self.client.get(reverse("api:labresult-acknowledge", args=[lab.uuid])).status_code, 405)
        as_json(self.client, "patch", reverse("api:labresult-detail", args=[lab.uuid]),
                {"acknowledged_at": timezone.now().isoformat(), "notes": "edited"})
        lab.refresh_from_db()
        self.assertIsNone(lab.acknowledged_at)

    def test_reception_cannot_acknowledge_or_read_results(self):
        with tenant_context(self.tenant):
            lab = LabResult.all_objects.create(tenant=self.tenant, patient=self.patient, branch=self.branch,
                                               test_name="T", flag="abnormal", status="resulted", value="9")
        self.login("rec")
        self.assertEqual(self.post("api:labresult-acknowledge", args=[lab.uuid]).status_code, 403)
        self.assertEqual(self.client.get(reverse("api:labresult-list")).status_code, 403)
        lab.refresh_from_db()
        self.assertIsNone(lab.acknowledged_at)


# ---------------------------------------------------------------- attachments


class AttachmentTests(ClinicalBase):
    def upload(self, content=PDF, name="report.pdf", title="Scan", **extra):
        return self.client.post(reverse("api:attachment-list"), {
            "patient": str(self.patient.uuid), "title": title, "category": "lab_report",
            "file": SimpleUploadedFile(name, content, content_type="application/octet-stream"), **extra,
        })

    def test_a_doctor_uploads_a_document_and_the_columns_are_derived(self):
        import hashlib

        self.login("doc")
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["original_filename"], "report.pdf")
        self.assertEqual(body["content_type"], "application/pdf")   # detected, not declared
        self.assertEqual(body["size_bytes"], len(PDF))
        self.assertEqual(body["checksum"], hashlib.sha256(PDF).hexdigest())
        self.assertNotIn("file", body)

    def test_a_hostile_or_mismatched_upload_is_refused_and_nothing_is_written(self):
        self.login("doc")
        for content, name in ((b"MZ\x90\x00 not a pdf", "report.pdf"), (PDF, "run.exe"), (b"", "empty.pdf")):
            with self.subTest(name=name):
                self.assertEqual(self.upload(content, name).status_code, 400)
        from medical.models import MedicalAttachment

        with tenant_context(self.tenant):
            self.assertEqual(MedicalAttachment.all_objects.count(), 0)

    def test_an_oversized_upload_is_refused(self):
        from django.test import override_settings

        self.login("doc")
        with override_settings(MEDICAL_ATTACHMENT_MAX_BYTES=100):
            self.assertEqual(self.upload(b"%PDF-" + b"0" * 200).status_code, 400)
        # ... and the same file is fine under the real limit.
        self.assertEqual(self.upload(b"%PDF-" + b"0" * 200).status_code, 201)

    def test_a_title_is_required(self):
        self.login("doc")
        self.assertEqual(self.upload(title="").status_code, 400)

    def test_the_file_is_stored_outside_media_root_under_a_random_tenant_partitioned_name(self):
        from django.conf import settings

        from medical.models import MedicalAttachment

        self.login("doc")
        uuid = self.upload().json()["uuid"]
        with tenant_context(self.tenant):
            stored = MedicalAttachment.all_objects.get(uuid=uuid).file
        path = stored.path
        self.assertFalse(path.startswith(str(settings.MEDIA_ROOT)), path)
        self.assertNotIn("report", stored.name)
        self.assertIn(f"tenant-{self.tenant.pk}", stored.name)
        with self.assertRaises(Exception):
            stored.url  # the storage exposes no public URL, by design

    def test_a_doctor_gets_the_file_back_intact_as_an_attachment(self):
        self.login("doc")
        uuid = self.upload().json()["uuid"]
        response = self.client.get(reverse("api:attachment-download", args=[uuid]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), PDF)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_nobody_else_gets_the_file(self):
        self.login("doc")
        uuid = self.upload().json()["uuid"]
        url = reverse("api:attachment-download", args=[uuid])
        self.login("rec")
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.logout()
        self.assertIn(self.client.get(url).status_code, (401, 403))
        rival = Tenant.objects.create(name="Rv3", slug="rv-att", status=Tenant.Status.ACTIVE)
        provision_tenant_defaults(rival)
        with tenant_context(rival):
            branch = Branch.all_objects.create(tenant=rival, name="R", code="R")
        User.objects.create_user(username="rva", email="rva@cl.local", password="pass12345", tenant=rival,
                                 role=ClinicRole.all_objects.get(tenant=rival, name="Admin"), branch=branch)
        self.login("rva")
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_documents_are_absent_from_receptions_view_of_the_patient(self):
        self.login("doc")
        self.upload(title="Secret-Scan-Title")
        self.login("rec")
        timeline = self.client.get(reverse("api:patient-timeline", args=[self.patient.uuid]))
        self.assertNotIn("Secret-Scan-Title", timeline.content.decode())
