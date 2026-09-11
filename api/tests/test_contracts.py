"""Doctor contracts, fixed prices, doctor shares and the doctor's emails.

The group owner's rules (2026-09-11): management sets each doctor's price and
percentage per service; nobody else sets a price or a discount; the doctor's
share is a percentage of what is actually paid, pending until management
records it received; the doctor sees only their own; and is emailed on each
patient sent in and each payment, with the service, original price, percentage
and share.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from appointments.models import Appointment
from billing.models import DoctorCommission, DoctorServiceRate, Payment
from branches.models import Branch
from employees.models import Employee, EmployeeType
from medical.models import Visit
from patients.models import Patient
from services.models import Service
from tenants.context import tenant_context
from tenants.models import Tenant

User = get_user_model()


class ContractTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            self.branch = Branch.all_objects.create(tenant=self.tenant, name="Pay", code="PY")
            roles = {
                n: ClinicRole.all_objects.get_or_create(tenant=self.tenant, name=n)[0]
                for n in ("Owner", "Admin", "Doctor", "Reception")
            }
            doctor_type, _ = EmployeeType.all_objects.get_or_create(tenant=self.tenant, name="Doctor")

            def doctor(name, nid, percent=None):
                return Employee.all_objects.create(
                    tenant=self.tenant, name=name, branch=self.branch, employee_type=doctor_type,
                    national_id=nid, salary_value=0, email=f"{nid}@doctors.local",
                    commission_percent=percent,
                )

            self.dr_a = doctor("Dr A", "CT-1", percent=Decimal("30"))
            self.dr_b = doctor("Dr B", "CT-2")
            self.consult = Service.all_objects.create(tenant=self.tenant, name="Consult CT", base_price=200)
            self.laser = Service.all_objects.create(tenant=self.tenant, name="Laser CT", base_price=1000)
            self.patient = Patient.all_objects.create(tenant=self.tenant, name="Mona", branch=self.branch)
        for key, role, employee in (
            ("admin", "Admin", None), ("desk", "Reception", None),
            ("doc-a", "Doctor", self.dr_a), ("doc-b", "Doctor", self.dr_b),
        ):
            User.objects.create_user(
                username=key, email=f"{key}@ct.local", password="pass12345",
                tenant=self.tenant, role=roles[role], branch=self.branch, employee=employee,
            )
        self.receipt = 0

    def login(self, key):
        self.client.logout()
        self.assertTrue(self.client.login(email=f"{key}@ct.local", password="pass12345"))

    def post(self, name, data=None, args=None):
        return self.client.post(reverse(name, args=args), data or {}, content_type="application/json")

    def rate(self, doctor, service, price=None, percent=None):
        with tenant_context(self.tenant):
            return DoctorServiceRate.all_objects.create(
                tenant=self.tenant, doctor=doctor, service=service, price=price, commission_percent=percent,
            )

    def book(self, doctor=None, service=None, price=None):
        response = self.post("api:appointment-list", {
            "patient": str(self.patient.uuid),
            "doctor": str((doctor or self.dr_a).uuid),
            "service": str((service or self.laser).uuid),
            "scheduled_date": timezone.now().isoformat(),
            **({"price": price} if price is not None else {}),
        })
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def pay(self, appointment_uuid, amount):
        self.receipt += 1
        response = self.post("api:payment-list", {
            "appointment": appointment_uuid, "patient": str(self.patient.uuid),
            "receipt_number": f"CT-{self.receipt}", "amount": amount,
        })
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def open_shift(self):
        self.post("api:shift-open", {"opening_balance": "0"})

    # ------------------------------------------------------------ contracts

    def test_only_management_writes_contracts_and_doctors_read_their_own(self):
        self.login("admin")
        created = self.post("api:doctorrate-list", {
            "doctor": str(self.dr_a.uuid), "service": str(self.laser.uuid),
            "price": "800.00", "commission_percent": "40",
        })
        self.assertEqual(created.status_code, 201, created.content)
        self.rate(self.dr_b, self.laser, percent=Decimal("20"))

        self.login("doc-a")
        rows = self.client.get(reverse("api:doctorrate-list")).json()["results"]
        self.assertEqual([r["doctor_name"] for r in rows], ["Dr A"])
        self.assertEqual(self.post("api:doctorrate-list", {
            "doctor": str(self.dr_a.uuid), "service": str(self.consult.uuid), "commission_percent": "90",
        }).status_code, 403)

        self.login("desk")
        self.assertEqual(self.client.get(reverse("api:doctorrate-list")).status_code, 403)

    # --------------------------------------------------------------- prices

    def test_a_booking_gets_the_contract_price_whatever_the_desk_sends(self):
        self.rate(self.dr_a, self.laser, price=Decimal("800"))
        self.login("desk")
        self.assertEqual(self.book(price="1.00")["price"], "800.00")
        # No contract price → the catalogue price.
        self.assertEqual(self.book(doctor=self.dr_b)["price"], "1000.00")

    def test_management_may_set_another_price(self):
        self.rate(self.dr_a, self.laser, price=Decimal("800"))
        self.login("admin")
        self.assertEqual(self.book(price="650.00")["price"], "650.00")

    def test_a_doctor_cannot_price_or_discount_a_procedure(self):
        self.rate(self.dr_a, self.laser, price=Decimal("800"))
        with tenant_context(self.tenant):
            visit = Visit.all_objects.create(
                tenant=self.tenant, patient=self.patient, doctor=self.dr_a, branch=self.branch,
            )
        self.login("doc-a")
        response = self.post("api:procedure-list", {
            "visit": str(visit.uuid), "patient": str(self.patient.uuid), "name": "Laser",
            "service": str(self.laser.uuid), "quantity": 2, "unit_price": "1.00", "discount": "500.00",
        })
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["unit_price"], "800.00")
        self.assertEqual(response.json()["discount"], "0.00")

    # ---------------------------------------------------------------- shares

    def test_the_share_is_a_percentage_of_what_was_paid(self):
        self.rate(self.dr_a, self.laser, percent=Decimal("40"))
        self.login("desk")
        self.open_shift()
        booking = self.book()
        self.pay(booking["uuid"], "500.00")  # a part payment of a 1000 service
        with tenant_context(self.tenant):
            share = DoctorCommission.all_objects.get()
        self.assertEqual((share.percent, share.amount), (Decimal("40.00"), Decimal("200.00")))
        self.assertEqual(share.original_price, Decimal("1000.00"))
        self.assertEqual(share.status, "pending")

    def test_the_doctors_default_percentage_applies_without_a_contract_line(self):
        self.login("desk")
        self.open_shift()
        self.pay(self.book(service=self.consult)["uuid"], "200.00")
        with tenant_context(self.tenant):
            self.assertEqual(DoctorCommission.all_objects.get().amount, Decimal("60.00"))

    def test_no_percentage_agreed_means_nothing_accrues(self):
        self.login("desk")
        self.open_shift()
        self.pay(self.book(doctor=self.dr_b)["uuid"], "300.00")
        with tenant_context(self.tenant):
            self.assertFalse(DoctorCommission.all_objects.exists())

    def test_a_contract_change_leaves_earned_shares_alone(self):
        line = self.rate(self.dr_a, self.laser, percent=Decimal("40"))
        self.login("desk")
        self.open_shift()
        self.pay(self.book()["uuid"], "1000.00")
        with tenant_context(self.tenant):
            DoctorServiceRate.all_objects.filter(pk=line.pk).update(commission_percent=Decimal("10"))
            self.assertEqual(DoctorCommission.all_objects.get().amount, Decimal("400.00"))

    def test_each_doctor_sees_only_their_own_and_the_desk_none(self):
        self.rate(self.dr_b, self.laser, percent=Decimal("50"))
        self.login("desk")
        self.open_shift()
        self.pay(self.book()["uuid"], "100.00")
        self.pay(self.book(doctor=self.dr_b)["uuid"], "100.00")
        self.assertEqual(self.client.get(reverse("api:commission-list")).json()["results"], [])

        self.login("doc-a")
        rows = self.client.get(reverse("api:commission-list")).json()["results"]
        self.assertEqual([(r["doctor_name"], r["amount"]) for r in rows], [("Dr A", "30.00")])
        summary = self.client.get(reverse("api:commission-summary")).json()
        self.assertEqual(summary["pending"], "30.00")
        dashboard = self.client.get(reverse("api:dashboard")).json()
        self.assertEqual(dashboard["commissions"]["pending"], "30.00")

    def test_management_records_the_share_received(self):
        self.login("desk")
        self.open_shift()
        payment = self.pay(self.book(service=self.consult)["uuid"], "200.00")
        with tenant_context(self.tenant):
            share = DoctorCommission.all_objects.get()

        self.login("doc-a")
        self.assertEqual(self.post("api:commission-settle", {"uuids": [str(share.uuid)]}).status_code, 403)

        self.login("admin")
        self.assertEqual(self.post("api:commission-settle", {"uuids": [str(share.uuid)]}).json(), {"settled": 1})
        # A settled share is never rewritten by a later correction.
        self.client.patch(
            reverse("api:payment-detail", args=[payment["uuid"]]), {"amount": "50.00"},
            content_type="application/json",
        )
        with tenant_context(self.tenant):
            share.refresh_from_db()
        self.assertEqual((share.status, share.amount), ("settled", Decimal("60.00")))

    def test_a_pending_share_follows_corrections_and_removal(self):
        self.login("desk")
        self.open_shift()
        payment = self.pay(self.book(service=self.consult)["uuid"], "200.00")
        self.login("admin")
        self.client.patch(
            reverse("api:payment-detail", args=[payment["uuid"]]), {"amount": "100.00"},
            content_type="application/json",
        )
        with tenant_context(self.tenant):
            self.assertEqual(DoctorCommission.all_objects.get().amount, Decimal("30.00"))
        self.client.delete(reverse("api:payment-detail", args=[payment["uuid"]]))
        with tenant_context(self.tenant):
            self.assertFalse(DoctorCommission.all_objects.exists())

    # ---------------------------------------------------------------- emails

    def test_the_doctor_is_emailed_on_check_in_and_on_payment(self):
        self.rate(self.dr_a, self.laser, price=Decimal("800"), percent=Decimal("40"))
        self.login("desk")
        self.open_shift()
        booking = self.book()
        with self.captureOnCommitCallbacks(execute=True):
            self.post("api:appointment-set-status", {"status": "entered"}, args=[booking["uuid"]])
        with self.captureOnCommitCallbacks(execute=True):
            self.pay(booking["uuid"], "800.00")

        self.assertEqual(len(mail.outbox), 2)
        checkin, payment = mail.outbox
        self.assertEqual(checkin.to, ["CT-1@doctors.local"])
        for text in ("Mona", "Laser CT", "800.00", "40"):
            self.assertIn(text, checkin.body)
        for text in ("800.00", "40", "320.00", "معلّقة"):
            self.assertIn(text, payment.body)
