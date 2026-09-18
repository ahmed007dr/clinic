"""Doctors' shares: pick several doctors, filter by service, print for signature."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from billing.models import DoctorCommission
from branches.models import Branch
from employees.models import Employee, EmployeeType
from patients.models import Patient
from services.models import Service
from tenants.context import tenant_context
from tenants.models import Tenant

User = get_user_model()
PASSWORD = "pass12345"


class CommissionFilterAndPrintTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            self.branch = Branch.all_objects.create(tenant=self.tenant, name="Cm", code="CM")
            roles = {
                n: ClinicRole.all_objects.get_or_create(tenant=self.tenant, name=n)[0]
                for n in ("Admin", "Doctor", "Reception")
            }
            doctor_type = EmployeeType.all_objects.get_or_create(tenant=self.tenant, name="Doctor")[0]
            self.nadia = self.doctor("Dr Nadia", "CM-1", "01011112222", doctor_type)
            self.omar = self.doctor("Dr Omar", "CM-2", "01033334444", doctor_type)
            self.laila = self.doctor("Dr Laila", "CM-3", "01055556666", doctor_type)
            self.patient = Patient.all_objects.create(tenant=self.tenant, name="Mona", branch=self.branch)
            self.laser = Service.all_objects.create(tenant=self.tenant, name="Laser-Cm", base_price=100)
            self.peel = Service.all_objects.create(tenant=self.tenant, name="Peel-Cm", base_price=100)
            self.share(self.nadia, self.laser, "10.00")
            self.share(self.nadia, self.peel, "20.00", status="settled")
            self.share(self.omar, self.laser, "30.00")
            self.share(self.laila, self.peel, "40.00")
        self.admin = User.objects.create_user(
            username="admin-cm", email="admin-cm@x.local", password=PASSWORD,
            tenant=self.tenant, role=roles["Admin"], branch=self.branch,
        )
        self.desk = User.objects.create_user(
            username="desk-cm", email="desk-cm@x.local", password=PASSWORD,
            tenant=self.tenant, role=roles["Reception"], branch=self.branch,
        )
        self.doc = User.objects.create_user(
            username="doc-cm", email="doc-cm@x.local", password=PASSWORD,
            tenant=self.tenant, role=roles["Doctor"], branch=self.branch, employee=self.nadia,
        )

    def doctor(self, name, national_id, phone, doctor_type):
        return Employee.all_objects.create(
            tenant=self.tenant, name=name, branch=self.branch, employee_type=doctor_type,
            national_id=national_id, salary_value=0, phone1=phone,
        )

    def share(self, doctor, service, amount, status="pending"):
        return DoctorCommission.all_objects.create(
            tenant=self.tenant, doctor=doctor, branch=self.branch, patient=self.patient,
            service=service, description=service.name, original_price=100,
            paid_amount=100, percent=Decimal(amount) , amount=Decimal(amount), status=status,
            settled_at=timezone.now() if status == "settled" else None,
        )

    def as_(self, key):
        self.client.logout()
        self.assertTrue(self.client.login(email=f"{key}@x.local", password=PASSWORD))

    def amounts(self, **params):
        response = self.client.get(reverse("api:commission-list"), params)
        self.assertEqual(response.status_code, 200, response.content)
        return sorted(Decimal(row["amount"]) for row in response.json()["results"])

    # ------------------------------------------------------------ filters

    def test_one_or_several_doctors_can_be_chosen(self):
        self.as_("admin-cm")
        self.assertEqual(self.amounts(doctor=self.omar.uuid), [Decimal("30.00")])
        both = f"{self.omar.uuid},{self.laila.uuid}"
        self.assertEqual(self.amounts(doctor=both), [Decimal("30.00"), Decimal("40.00")])

    def test_filtering_by_service_and_the_totals_follow(self):
        self.as_("admin-cm")
        self.assertEqual(self.amounts(service=self.laser.uuid), [Decimal("10.00"), Decimal("30.00")])
        summary = self.client.get(
            reverse("api:commission-summary"), {"service": str(self.laser.uuid)}
        ).json()
        self.assertEqual(summary["total"], "40.00")

    def test_doctors_are_found_by_name_or_by_phone(self):
        self.as_("admin-cm")
        by_phone = self.client.get(reverse("api:doctor-list"), {"search": "01033334444"}).json()
        self.assertEqual([row["name"] for row in by_phone["results"]], ["Dr Omar"])
        by_name = self.client.get(reverse("api:doctor-list"), {"search": "Laila"}).json()
        self.assertEqual([row["name"] for row in by_name["results"]], ["Dr Laila"])

    def test_only_management_sees_a_doctors_phone_in_the_picker(self):
        self.as_("admin-cm")
        row = self.client.get(reverse("api:doctor-list"), {"search": "Omar"}).json()["results"][0]
        self.assertEqual(row["phone1"], "01033334444")
        self.as_("desk-cm")
        row = self.client.get(reverse("api:doctor-list"), {"search": "Omar"}).json()["results"][0]
        self.assertIsNone(row["phone1"])

    # -------------------------------------------------------------- print

    def report(self, **params):
        return self.client.get(reverse("billing:commission_report_print"), params)

    def test_the_report_has_a_block_and_signature_lines_per_doctor(self):
        self.as_("admin-cm")
        body = self.report(status="pending").content.decode()
        self.assertIn("المعلّقة", body)
        for name in ("Dr Nadia", "Dr Omar", "Dr Laila"):
            self.assertIn(name, body)
        self.assertEqual(body.count("توقيع الأدمن"), 3)
        self.assertEqual(body.count("توقيع الطبيب بالاستلام"), 3)
        # The settled share is not in a "pending" report.
        self.assertNotIn("20.00", body)

    def test_the_report_follows_the_screens_filters(self):
        self.as_("admin-cm")
        body = self.report(status="settled", doctor=str(self.nadia.uuid)).content.decode()
        self.assertIn("المستلمة", body)
        self.assertIn("Dr Nadia", body)
        self.assertNotIn("Dr Omar", body)
        both = self.report(doctor=f"{self.omar.uuid},{self.laila.uuid}", service=str(self.peel.uuid)).content.decode()
        self.assertIn("Dr Laila", both)
        self.assertNotIn("Dr Omar", both)

    def test_a_doctor_prints_only_their_own(self):
        self.as_("doc-cm")
        response = self.report()
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("Dr Nadia", body)
        self.assertNotIn("Dr Omar", body)
        self.assertNotIn("Dr Laila", body)

    def test_the_front_desk_cannot_print_it(self):
        self.as_("desk-cm")
        self.assertEqual(self.report().status_code, 403)
