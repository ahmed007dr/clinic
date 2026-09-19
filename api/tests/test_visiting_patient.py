"""A patient of one clinic with a confirmed booking at another (docs/15, Phase 5a, D10).

Patient "Pat" belongs to clinic A and has a confirmed booking at clinic B. The
minimum B needs is to receive, call and treat them — and nothing of A's
history, notes or identity papers beyond that. Every test here is a way of
checking that B gets exactly that and no more, and that C gets nothing.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from api.serializers.patients import VISITING_FIELDS
from appointments.models import Appointment
from billing.models import Payment, PaymentMethod
from branches.models import Branch
from employees.models import Employee, EmployeeType
from medical.models import Allergy, LabResult, Prescription, Visit
from patients.models import Patient
from tenants.context import tenant_context
from tenants.models import Tenant
from tenants.provisioning import provision_tenant_defaults
from tenants.testing import act_as_tenant

User = get_user_model()
PASSWORD = "pass12345"


class VisitingBase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        act_as_tenant(self, self.tenant)
        provision_tenant_defaults(self.tenant)
        self.a = Branch.all_objects.create(tenant=self.tenant, name="Clinic A", code="CA")
        self.b = Branch.all_objects.create(tenant=self.tenant, name="Clinic B", code="CB")
        self.c = Branch.all_objects.create(tenant=self.tenant, name="Clinic C", code="CC")
        doctor_type = EmployeeType.all_objects.get(tenant=self.tenant, name="Doctor")

        def role(name):
            return ClinicRole.all_objects.get(tenant=self.tenant, name=name)

        def user(username, role_name, branch, employee=None):
            return User.objects.create_user(
                username=username, email=f"{username}@vis.local", password=PASSWORD,
                tenant=self.tenant, role=role(role_name), branch=branch, employee=employee,
            )

        def doctor(name, national_id, branch):
            return Employee.all_objects.create(
                tenant=self.tenant, name=name, branch=branch, employee_type=doctor_type,
                national_id=national_id, salary_value=0,
            )

        self.dr_a = doctor("Dr A", "DA", self.a)
        self.dr_b = doctor("Dr B", "DB", self.b)
        self.dr_b2 = doctor("Dr B2", "DB2", self.b)

        self.owner = user("owner", "Owner", self.a)
        self.admin_a = user("admin-a", "Admin", self.a)
        self.admin_b = user("admin-b", "Admin", self.b)
        self.rec_a = user("rec-a", "Reception", self.a)
        self.rec_b = user("rec-b", "Reception", self.b)
        self.rec_c = user("rec-c", "Reception", self.c)
        self.doc_b = user("doc-b", "Doctor", self.b, employee=self.dr_b)
        self.doc_b2 = user("doc-b2", "Doctor", self.b, employee=self.dr_b2)

        self.pat = Patient.all_objects.create(
            tenant=self.tenant, name="Pat Visitor", branch=self.a, phone1="01011112222", phone2="01033334444",
            national_id="NID-SECRET", notes="internal note about Pat", address="12 Secret St",
            email="pat@secret.example", emergency_contact_name="Ec Secret", whatsapp="01055556666",
            birth_date=timezone.now().date().replace(year=1990),
        )
        self.quin = Patient.all_objects.create(tenant=self.tenant, name="Quin Stranger", branch=self.a, phone1="01099990000")

        # Pat's booking at clinic B — confirmed.
        self.visit_booking = self.booking(self.b, self.dr_b, "waiting")

        # Pat's history at her own clinic A.
        self.a_booking = self.booking(self.a, self.dr_a, "completed")
        self.a_visit = Visit.all_objects.create(
            tenant=self.tenant, patient=self.pat, doctor=self.dr_a, branch=self.a,
            appointment=self.a_booking, diagnosis="A-diagnosis",
        )
        self.a_rx = Prescription.all_objects.create(tenant=self.tenant, patient=self.pat, visit=self.a_visit, notes="A-rx")
        self.a_lab = LabResult.all_objects.create(tenant=self.tenant, patient=self.pat, branch=self.a, test_name="A-lab")
        method = PaymentMethod.all_objects.get_or_create(tenant=self.tenant, name="Cash")[0]
        self.a_payment = Payment.all_objects.create(
            tenant=self.tenant, appointment=self.a_booking, patient=self.pat, method=method,
            receipt_number="R-A-1", amount=Decimal("123"), branch=self.a,
        )
        self.allergy = Allergy.all_objects.create(tenant=self.tenant, patient=self.pat, substance="Penicillin", severity="severe")

    def booking(self, branch, doctor, status, patient=None):
        return Appointment.all_objects.create(
            tenant=self.tenant, patient=patient or self.pat, doctor=doctor, branch=branch, status=status,
            scheduled_date=timezone.now() + timedelta(hours=2), price=100,
        )

    def login(self, username):
        self.client.logout()
        self.assertTrue(self.client.login(email=f"{username}@vis.local", password=PASSWORD))

    def names(self, username, **params):
        self.login(username)
        response = self.client.get(reverse("api:patient-list"), params)
        self.assertEqual(response.status_code, 200, response.content)
        return [row["name"] for row in response.json()["results"]]

    def detail(self, username, patient=None):
        self.login(username)
        return self.client.get(reverse("api:patient-detail", args=[(patient or self.pat).uuid]))


class ReachTests(VisitingBase):
    def test_the_clinic_with_the_booking_sees_the_patient_and_the_others_do_not(self):
        self.assertIn("Pat Visitor", self.names("rec-b"))
        self.assertIn("Pat Visitor", self.names("admin-b"))
        self.assertNotIn("Pat Visitor", self.names("rec-c"))
        self.assertEqual(self.detail("rec-c").status_code, 404)

    def test_the_patients_home_clinic_and_the_owner_see_everything_as_before(self):
        for username in ("rec-a", "admin-a", "owner"):
            with self.subTest(username=username):
                body = self.detail(username).json()
                self.assertEqual(body["national_id"], "NID-SECRET")
                self.assertNotIn("visiting", body)

    def test_only_a_confirmed_booking_opens_the_file(self):
        for status in ("requested", "cancelled", "no_show"):
            with self.subTest(status=status):
                Appointment.all_objects.filter(pk=self.visit_booking.pk).update(status=status)
                self.assertEqual(self.detail("rec-b").status_code, 404)
                self.assertNotIn("Pat Visitor", self.names("rec-b"))
        for status in ("waiting", "called", "entered", "quick", "completed"):
            with self.subTest(status=status):
                Appointment.all_objects.filter(pk=self.visit_booking.pk).update(status=status)
                self.assertEqual(self.detail("rec-b").status_code, 200)

    def test_cancelling_closes_it_again(self):
        self.assertEqual(self.detail("rec-b").status_code, 200)
        Appointment.all_objects.filter(pk=self.visit_booking.pk).update(status="cancelled")
        self.assertEqual(self.detail("rec-b").status_code, 404)

    def test_another_patient_with_no_booking_here_stays_out_of_reach(self):
        self.assertNotIn("Quin Stranger", self.names("rec-b"))
        self.assertEqual(self.detail("rec-b", self.quin).status_code, 404)

    def test_a_booking_at_a_third_clinic_opens_nothing_at_b(self):
        Appointment.all_objects.filter(pk=self.visit_booking.pk).update(branch=self.c)
        self.assertEqual(self.detail("rec-b").status_code, 404)
        self.assertEqual(self.detail("rec-c").status_code, 200)

    def test_a_doctor_reaches_only_a_patient_booked_with_them(self):
        self.assertIn("Pat Visitor", self.names("doc-b"))
        self.assertNotIn("Pat Visitor", self.names("doc-b2"))
        self.assertEqual(self.detail("doc-b2").status_code, 404)


class LimitedViewTests(VisitingBase):
    def test_a_visiting_patient_shows_only_what_receiving_and_treating_them_needs(self):
        body = self.detail("rec-b").json()
        self.assertEqual(set(body), {*VISITING_FIELDS, "visiting"})
        self.assertTrue(body["visiting"])
        self.assertEqual((body["name"], body["phone1"]), ("Pat Visitor", "01011112222"))
        text = str(body)
        for secret in ("NID-SECRET", "internal note", "Secret St", "pat@secret", "Ec Secret", "01033334444", "01055556666"):
            self.assertNotIn(secret, text)

    def test_the_list_row_is_marked_and_carries_no_more(self):
        self.login("rec-b")
        rows = {r["name"]: r for r in self.client.get(reverse("api:patient-list")).json()["results"]}
        self.assertTrue(rows["Pat Visitor"]["visiting"])
        self.assertNotIn("national_id", rows["Pat Visitor"])

    def test_it_can_be_read_but_never_changed_from_the_other_clinic(self):
        url = reverse("api:patient-detail", args=[self.pat.uuid])
        for username in ("rec-b", "admin-b"):
            self.login(username)
            self.assertEqual(self.client.patch(url, {"phone1": "0100"}, content_type="application/json").status_code, 403, username)
            self.assertEqual(self.client.delete(url).status_code, 403, username)
            self.assertEqual(self.client.post(reverse("api:patient-portal-invite", args=[self.pat.uuid])).status_code, 403, username)
        self.pat.refresh_from_db()
        self.assertEqual(self.pat.phone1, "01011112222")

    def test_the_home_clinic_can_still_edit(self):
        self.login("rec-a")
        response = self.client.patch(reverse("api:patient-detail", args=[self.pat.uuid]), {"phone1": "01000000000"},
                                     content_type="application/json")
        self.assertEqual(response.status_code, 200, response.content)


class HistoryStaysAtHomeTests(VisitingBase):
    def timeline_ids(self, username):
        self.login(username)
        response = self.client.get(reverse("api:patient-timeline", args=[self.pat.uuid]))
        self.assertEqual(response.status_code, 200, response.content)
        return {entry["uuid"] for entry in response.json()["entries"]}

    def test_the_other_clinic_sees_only_its_own_booking_never_the_home_clinics_records(self):
        seen = self.timeline_ids("admin-b")
        self.assertEqual(seen, {str(self.visit_booking.uuid)})
        for hidden in (self.a_booking, self.a_visit, self.a_rx, self.a_lab, self.a_payment):
            self.assertNotIn(str(hidden.uuid), seen)

    def test_the_home_clinic_does_not_see_the_other_clinics_booking_either(self):
        seen = self.timeline_ids("admin-a")
        self.assertIn(str(self.a_visit.uuid), seen)
        self.assertNotIn(str(self.visit_booking.uuid), seen)

    def test_the_owner_sees_the_whole_history(self):
        seen = self.timeline_ids("owner")
        for row in (self.visit_booking, self.a_booking, self.a_visit, self.a_rx, self.a_lab, self.a_payment):
            self.assertIn(str(row.uuid), seen)

    def test_reception_at_the_other_clinic_gets_no_money_or_clinical_lines(self):
        seen = self.timeline_ids("rec-b")
        self.assertEqual(seen, {str(self.visit_booking.uuid)})

    def test_other_lists_are_still_cut_by_the_records_own_clinic(self):
        self.login("admin-b")
        self.assertEqual(self.client.get(reverse("api:visit-list")).json()["results"], [])
        self.assertEqual(self.client.get(reverse("api:labresult-list")).json()["results"], [])
        self.assertEqual(self.client.get(reverse("api:payment-list")).json()["results"], [])


def rows_of(response):
    """The allergy list is not paginated; the others are."""
    data = response.json()
    return data["results"] if isinstance(data, dict) else data


class TreatingTheVisitorTests(VisitingBase):
    def test_the_doctor_sees_the_allergy_and_may_add_one(self):
        self.login("doc-b")
        rows = rows_of(self.client.get(reverse("api:allergy-list")))
        self.assertEqual([r["substance"] for r in rows], ["Penicillin"])
        added = self.client.post(reverse("api:allergy-list"), {
            "patient": str(self.pat.uuid), "substance": "Latex", "severity": "mild",
        }, content_type="application/json")
        self.assertEqual(added.status_code, 201, added.content)

    def test_a_doctor_who_is_not_booked_with_them_sees_no_allergies(self):
        self.login("doc-b2")
        self.assertEqual(rows_of(self.client.get(reverse("api:allergy-list"))), [])

    def test_the_reported_history_is_readable_by_the_doctor_and_never_written(self):
        self.login("doc-b")
        url = reverse("api:patient-history", args=[self.pat.uuid])
        self.assertEqual(self.client.get(url).status_code, 200)
        put = self.client.put(url, {"current_medications": "x", "conditions": []}, content_type="application/json")
        self.assertEqual(put.status_code, 403)
        self.login("rec-b")  # reception never reads clinical history
        self.assertEqual(self.client.get(url).status_code, 403)
        self.login("rec-c")
        self.assertIn(self.client.get(url).status_code, (403, 404))

    def test_the_desk_can_book_the_visitor_again_and_a_stranger_clinic_cannot(self):
        body = {
            "patient": str(self.pat.uuid), "branch": str(self.b.uuid), "doctor": str(self.dr_b.uuid),
            "scheduled_date": (timezone.now() + timedelta(days=3)).strftime("%Y-%m-%d %H:%M"),
        }
        self.login("rec-b")
        self.assertEqual(self.client.post(reverse("api:appointment-list"), body, content_type="application/json").status_code, 201)
        self.login("rec-c")
        refused = self.client.post(reverse("api:appointment-list"), {**body, "branch": str(self.c.uuid)},
                                   content_type="application/json")
        self.assertEqual(refused.status_code, 400)

    def test_the_visitor_is_not_counted_among_the_clinics_own_patients(self):
        self.login("admin-b")
        total = self.client.get(reverse("api:dashboard")).json()["patients"]["total"]
        self.assertEqual(total, 0)

    def test_the_patient_export_never_carries_a_visitor(self):
        self.login("admin-b")
        response = self.client.get(reverse("patients:patient_list_export"), {"export": "excel"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"NID-SECRET", response.content)
        self.assertNotIn("Pat Visitor".encode(), response.content)
