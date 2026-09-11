"""Stopping accounts and clinics, stopped services, voided money, paid
bookings, and each clinic's own printed look (the group owner's rules,
2026-09-11)."""

import io
import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.test.client import BOUNDARY, MULTIPART_CONTENT, encode_multipart
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from accounts.models import ClinicRole
from appointments.models import Appointment
from billing.models import CashShift, DoctorCommission, Payment
from branches.models import Branch
from employees.models import Employee, EmployeeType
from patients.models import Patient
from services.models import Service
from tenants.context import tenant_context
from tenants.models import Tenant

User = get_user_model()


def png(size=(8, 8)):
    buffer = io.BytesIO()
    Image.new("RGB", size, "teal").save(buffer, "PNG")
    return SimpleUploadedFile("logo.png", buffer.getvalue(), content_type="image/png")


TEST_MEDIA = tempfile.mkdtemp(prefix="clinic-test-media-")


# Uploaded logos go to a throwaway folder, never the project's media/.
@override_settings(MEDIA_ROOT=TEST_MEDIA)
class PhaseSixTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA, ignore_errors=True)

    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            self.branch = Branch.all_objects.create(tenant=self.tenant, name="Six", code="SX")
            self.other = Branch.all_objects.create(tenant=self.tenant, name="Seven", code="SV")
            self.roles = {
                n: ClinicRole.all_objects.get_or_create(tenant=self.tenant, name=n)[0]
                for n in ("Owner", "Admin", "Doctor", "Reception")
            }
            doctor_type, _ = EmployeeType.all_objects.get_or_create(tenant=self.tenant, name="Doctor")
            self.doctor = Employee.all_objects.create(
                tenant=self.tenant, name="Dr Six", branch=self.branch, employee_type=doctor_type,
                national_id="P6-1", salary_value=0, commission_percent=Decimal("50"),
            )
            self.service = Service.all_objects.create(tenant=self.tenant, name="Consult P6", base_price=200)
            self.patient = Patient.all_objects.create(tenant=self.tenant, name="Hana", branch=self.branch)
        self.users = {}
        for key, role, branch in (
            ("owner", "Owner", self.branch), ("admin", "Admin", self.branch),
            ("admin2", "Admin", self.branch), ("far", "Admin", self.other),
            ("desk", "Reception", self.branch), ("doc", "Doctor", self.branch),
        ):
            self.users[key] = User.objects.create_user(
                username=key, email=f"{key}@p6.local", password="pass12345",
                tenant=self.tenant, role=self.roles[role], branch=branch,
                employee=self.doctor if key == "doc" else None,
            )

    def login(self, key):
        self.client.logout()
        self.assertTrue(self.client.login(email=f"{key}@p6.local", password="pass12345"))

    def post(self, name, data=None, args=None):
        return self.client.post(reverse(name, args=args), data or {}, content_type="application/json")

    def book(self, **extra):
        return self.post("api:appointment-list", {
            "patient": str(self.patient.uuid), "doctor": str(self.doctor.uuid),
            "service": str(self.service.uuid), "scheduled_date": timezone.now().isoformat(), **extra,
        })

    # ------------------------------------------------------------ accounts

    def test_an_admin_stops_employee_and_doctor_accounts_only(self):
        self.login("admin")
        for key, expected in (("desk", 204), ("doc", 204), ("admin2", 403), ("admin", 403)):
            with self.subTest(target=key):
                response = self.client.delete(reverse("api:staff-detail", args=[self.users[key].uuid]))
                self.assertEqual(response.status_code, expected)

    def test_the_owner_stops_an_admin_but_not_themselves(self):
        self.login("owner")
        self.assertEqual(
            self.client.delete(reverse("api:staff-detail", args=[self.users["admin"].uuid])).status_code, 204
        )
        self.assertEqual(
            self.client.delete(reverse("api:staff-detail", args=[self.users["owner"].uuid])).status_code, 403
        )

    def test_a_stopped_account_is_signed_out_at_once(self):
        desk = self.client_class()
        self.assertTrue(desk.login(email="desk@p6.local", password="pass12345"))
        self.login("admin")
        self.client.delete(reverse("api:staff-detail", args=[self.users["desk"].uuid]))
        self.assertIn(desk.get(reverse("api:patient-list")).status_code, (401, 403))

    # ------------------------------------------------------------- clinics

    def stop_branch(self, key="owner", branch=None):
        self.login(key)
        return self.client.patch(
            reverse("api:branch-detail", args=[(branch or self.branch).uuid]), {"is_active": False},
            content_type="application/json",
        )

    def test_only_the_owner_stops_a_clinic(self):
        self.assertEqual(self.stop_branch("admin").status_code, 403)
        self.assertEqual(self.stop_branch("owner").status_code, 200)

    def test_a_stopped_clinic_signs_its_staff_out_and_refuses_sign_in(self):
        desk = self.client_class()
        self.assertTrue(desk.login(email="desk@p6.local", password="pass12345"))
        self.stop_branch()
        self.assertIn(desk.get(reverse("api:patient-list")).status_code, (401, 403))
        again = self.client_class().post(
            reverse("api:login"), {"email": "desk@p6.local", "password": "pass12345"},
            content_type="application/json",
        )
        self.assertEqual(again.status_code, 403)
        self.assertIn("إيقاف", again.json()["detail"])
        # The Owner is unaffected and still sees the stopped clinic.
        self.login("owner")
        names = {b["name"] for b in self.client.get(reverse("api:branch-list")).json()["results"]}
        self.assertIn("Six", names)

    def test_a_stopped_clinic_leaves_the_pickers(self):
        self.stop_branch(branch=self.other)
        self.login("admin")
        names = {b["name"] for b in self.client.get(reverse("api:branch-list")).json()["results"]}
        self.assertNotIn("Seven", names)

    # ------------------------------------------------------------ services

    def test_a_stopped_service_is_hidden_and_refused_for_new_bookings(self):
        self.login("desk")
        booked = self.book()
        self.assertEqual(booked.status_code, 201, booked.content)
        with tenant_context(self.tenant):
            Service.all_objects.filter(pk=self.service.pk).update(is_active=False)
        self.assertEqual(self.client.get(reverse("api:service-list")).json()["results"], [])
        self.assertEqual(self.book().status_code, 400)
        # What was already booked under it can still be edited.
        edited = self.client.patch(
            reverse("api:appointment-detail", args=[booked.json()["uuid"]]), {"notes": "ok"},
            content_type="application/json",
        )
        self.assertEqual(edited.status_code, 200, edited.content)
        self.login("admin")
        self.assertEqual(len(self.client.get(reverse("api:service-list")).json()["results"]), 1)

    def test_a_stopped_doctor_is_not_bookable(self):
        self.login("admin")
        self.client.delete(reverse("api:staff-detail", args=[self.users["doc"].uuid]))
        self.login("desk")
        names = {d["name"] for d in self.client.get(reverse("api:doctor-list")).json()["results"]}
        self.assertNotIn("Dr Six", names)
        self.assertEqual(self.book().status_code, 400)

    # ---------------------------------------------------------------- money

    def paid_booking(self, amount="200.00"):
        self.login("desk")
        self.post("api:shift-open", {"opening_balance": "0"})
        booking = self.book().json()
        payment = self.post("api:payment-list", {
            "appointment": booking["uuid"], "patient": str(self.patient.uuid),
            "receipt_number": f"P6-{amount}", "amount": amount,
        })
        self.assertEqual(payment.status_code, 201, payment.content)
        return booking, payment.json()

    def test_management_voids_a_payment_with_a_reason(self):
        _, payment = self.paid_booking()
        # Reception may not.
        self.assertEqual(self.post("api:payment-void", {"reason": "x"}, args=[payment["uuid"]]).status_code, 400)

        self.login("admin")
        self.assertEqual(self.post("api:payment-void", {}, args=[payment["uuid"]]).status_code, 400)
        voided = self.post("api:payment-void", {"reason": "duplicate receipt"}, args=[payment["uuid"]])
        self.assertEqual(voided.status_code, 200, voided.content)

        receipts = [p["receipt_number"] for p in self.client.get(reverse("api:payment-list")).json()["results"]]
        self.assertNotIn(payment["receipt_number"], receipts)
        cancelled = self.client.get(reverse("api:payment-list"), {"voided": "1"}).json()["results"]
        self.assertEqual([p["void_reason"] for p in cancelled], ["duplicate receipt"])
        report = self.client.get(reverse("api:financialreport-list")).json()
        self.assertEqual(float(report["revenue"]), 0.0)
        with tenant_context(self.tenant):
            self.assertFalse(DoctorCommission.all_objects.exists())
            self.assertTrue(Payment.all_objects.filter(uuid=payment["uuid"]).exists())
            shift = CashShift.all_objects.get()
        summary = self.client.get(reverse("api:shift-detail", args=[shift.uuid])).json()["summary"]
        self.assertEqual(summary["revenue"], "0.00")

    def test_management_voids_an_expense(self):
        self.login("desk")
        self.post("api:shift-open", {"opening_balance": "0"})
        expense = self.post("api:expense-list", {"amount": "40.00"})
        self.assertEqual(expense.status_code, 201, expense.content)
        self.login("admin")
        self.assertEqual(
            self.post("api:expense-void", {"reason": "wrong amount"}, args=[expense.json()["uuid"]]).status_code,
            200,
        )
        self.assertEqual(self.client.get(reverse("api:expense-list")).json()["count"], 0)

    # -------------------------------------------------------- paid bookings

    def test_the_desk_sees_which_bookings_are_paid(self):
        booking, _ = self.paid_booking("200.00")
        with tenant_context(self.tenant):
            Appointment.all_objects.filter(uuid=booking["uuid"]).update(
                scheduled_date=timezone.now() + timedelta(days=3)
            )
        self.book()  # today, unpaid
        rows = self.client.get(reverse("api:appointment-list"), {"upcoming": "1"}).json()["results"]
        self.assertEqual([(r["uuid"], r["payment_status"]) for r in rows], [(booking["uuid"], "paid")])
        unpaid = self.client.get(reverse("api:appointment-list"), {"paid": "0"}).json()["results"]
        self.assertEqual({r["payment_status"] for r in unpaid}, {"unpaid"})
        self.login("doc")
        row = self.client.get(reverse("api:appointment-detail", args=[booking["uuid"]])).json()
        self.assertIsNone(row["payment_status"])

    # --------------------------------------------------------------- printing

    def settings_url(self, branch=None):
        return reverse("api:print-settings", args=[(branch or self.branch).uuid])

    def upload(self, data):
        # The test client does not encode multipart for PATCH; a browser does.
        return self.client.patch(
            self.settings_url(), encode_multipart(BOUNDARY, data), content_type=MULTIPART_CONTENT
        )

    def test_the_clinic_admin_designs_their_own_paper(self):
        self.login("admin")
        response = self.client.patch(self.settings_url(), {
            "print_header_title": "Six Dermatology", "address": "12 Nile St",
            "print_accent_color": "#aa3300", "intake_sections": ["personal", "consent"],
            "intake_extra_fields": ["Referred by"],
        }, content_type="application/json")
        self.assertEqual(response.status_code, 200, response.content)
        logo = self.upload({"logo": png()})
        self.assertEqual(logo.status_code, 200, logo.content)
        self.assertTrue(logo.json()["logo_url"])
        self.assertEqual(self.client.get(self.settings_url(self.other)).status_code, 403)
        self.login("desk")
        self.assertEqual(self.client.get(self.settings_url()).status_code, 403)

    def test_bad_logos_and_colours_are_refused(self):
        self.login("owner")
        svg = SimpleUploadedFile("x.svg", b"<svg onload='alert(1)'/>", content_type="image/svg+xml")
        self.assertEqual(self.upload({"logo": svg}).status_code, 400)
        self.assertEqual(self.client.patch(
            self.settings_url(), {"print_accent_color": "red;}"}, content_type="application/json"
        ).status_code, 400)

    def test_the_printed_intake_form_uses_the_clinics_design(self):
        self.login("admin")
        self.client.patch(self.settings_url(), {
            "print_header_title": "Six Dermatology", "intake_form_title": "New patient sheet",
            "intake_sections": ["personal", "consent"], "intake_extra_fields": ["Referred by"],
        }, content_type="application/json")
        self.login("desk")
        page = self.client.get(reverse("patients:intake_form_print"), {"patient": str(self.patient.uuid)})
        self.assertEqual(page.status_code, 200)
        for text in ("Six Dermatology", "New patient sheet", "Referred by", "Hana"):
            self.assertContains(page, text)
        self.assertNotContains(page, "الأدوية الحالية")
        self.login("doc")
        self.assertEqual(self.client.get(reverse("patients:intake_form_print")).status_code, 302)
