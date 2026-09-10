"""The group owner's dashboard: right totals, right scope, nobody else's data.

The fixture is built so that naive aggregation would give wrong answers: a
clinic with two payments on one appointment *and* two expenses (a join between
them would double both), a cancelled appointment with a price (must not be
billed), and a second group with its own large numbers (must never appear).
"""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from appointments.models import Appointment
from billing.models import Expense, ExpenseCategory, Payment
from branches.models import Branch
from employees.models import Attendance, Employee, EmployeeType
from patients.models import Patient
from tenants.context import tenant_context
from tenants.models import Tenant

User = get_user_model()
PASSWORD = "pass12345"


class OwnerDashboardTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        today = date.today()
        now = timezone.now()
        with tenant_context(self.tenant):
            roles = {n: ClinicRole.all_objects.get_or_create(tenant=self.tenant, name=n)[0]
                     for n in ("Owner", "Admin", "Doctor")}
            self.a = Branch.all_objects.create(tenant=self.tenant, name="Clinic A", code="OA")
            self.b = Branch.all_objects.create(tenant=self.tenant, name="Clinic B", code="OB")
            doctor_type, _ = EmployeeType.all_objects.get_or_create(tenant=self.tenant, name="Doctor")
            self.dr_a = Employee.all_objects.create(tenant=self.tenant, name="Dr A", branch=self.a,
                                                    national_id="1", salary_value=1, employee_type=doctor_type)
            self.dr_b = Employee.all_objects.create(tenant=self.tenant, name="Dr B", branch=self.b,
                                                    national_id="2", salary_value=1, employee_type=doctor_type)
            p1 = Patient.all_objects.create(tenant=self.tenant, name="P1", branch=self.a)
            p2 = Patient.all_objects.create(tenant=self.tenant, name="P2", branch=self.b)
            # A returning patient: an appointment long before the period, one inside it.
            Appointment.all_objects.create(tenant=self.tenant, patient=p1, branch=self.a, doctor=self.dr_a,
                                           scheduled_date=now - timedelta(days=60), status="completed", price=10)
            appt1 = Appointment.all_objects.create(tenant=self.tenant, patient=p1, branch=self.a, doctor=self.dr_a,
                                                   scheduled_date=now, status="completed", price=300)
            Appointment.all_objects.create(tenant=self.tenant, patient=p1, branch=self.a, doctor=self.dr_a,
                                           scheduled_date=now, status="cancelled", price=200)
            appt3 = Appointment.all_objects.create(tenant=self.tenant, patient=p2, branch=self.b, doctor=self.dr_b,
                                                   scheduled_date=now, status="no_show", price=100)
            # Two payments on one appointment, two expenses in the same clinic.
            Payment.all_objects.create(tenant=self.tenant, appointment=appt1, patient=p1, receipt_number="O1",
                                       amount=100, branch=self.a)
            Payment.all_objects.create(tenant=self.tenant, appointment=appt1, patient=p1, receipt_number="O2",
                                       amount=150, branch=self.a)
            Payment.all_objects.create(tenant=self.tenant, appointment=appt3, patient=p2, receipt_number="O3",
                                       amount=80, branch=self.b)
            rent = ExpenseCategory.all_objects.create(tenant=self.tenant, name="Rent")
            for amount, branch in ((40, self.a), (60, self.a), (30, self.b)):
                Expense.all_objects.create(tenant=self.tenant, branch=branch, category=rent, amount=amount, date=today)
            Attendance.all_objects.create(tenant=self.tenant, employee=self.dr_a, branch=self.a, date=today, status="present")
            Attendance.all_objects.create(tenant=self.tenant, employee=self.dr_b, branch=self.b, date=today, status="absent")

        # Another group, with numbers that would be obvious if they leaked.
        self.other = Tenant.objects.create(name="Other group", slug="other-owner", status="active")
        with tenant_context(self.other):
            ob = Branch.all_objects.create(tenant=self.other, name="Their clinic", code="TC")
            op = Patient.all_objects.create(tenant=self.other, name="Theirs", branch=ob)
            oa = Appointment.all_objects.create(tenant=self.other, patient=op, branch=ob, scheduled_date=now, price=999)
            Payment.all_objects.create(tenant=self.other, appointment=oa, patient=op, receipt_number="X", amount=999, branch=ob)
            Expense.all_objects.create(tenant=self.other, branch=ob, amount=999, date=today)
            self.their_branch = ob

        def make(name, role, branch):
            return User.objects.create_user(username=name, email=f"{name}@owner.local", password=PASSWORD,
                                            tenant=self.tenant, role=roles[role], branch=branch)
        self.owner = make("owner", "Owner", self.a)
        self.admin = make("admin", "Admin", self.a)
        self.doctor = make("doctor", "Doctor", self.a)
        self.client.login(email="owner@owner.local", password=PASSWORD)
        self.week = {"from": (today - timedelta(days=7)).isoformat(), "to": today.isoformat()}

    def overview(self, **params):
        return self.client.get(reverse("api:owner-overview"), {**self.week, **params})

    def test_group_totals_are_right_and_not_double_counted(self):
        data = self.overview().json()
        self.assertEqual(float(data["finance"]["revenue"]), 330)
        self.assertEqual(float(data["finance"]["expenses"]), 130)
        self.assertEqual(float(data["finance"]["net"]), 200)
        clinics = {c["name"]: c for c in data["clinics"]}
        self.assertEqual(float(clinics["Clinic A"]["revenue"]), 250)   # two payments, not 250×2
        self.assertEqual(float(clinics["Clinic A"]["expenses"]), 100)  # two expenses, not ×2
        self.assertEqual(float(clinics["Clinic B"]["revenue"]), 80)

    def test_billed_collected_and_outstanding(self):
        finance = self.overview().json()["finance"]
        # Cancelled and no-show appointments are not billed.
        self.assertEqual(float(finance["billed"]), 300)
        self.assertEqual(float(finance["collected"]), 250)
        self.assertEqual(float(finance["outstanding"]), 50)

    def test_revenue_by_doctor(self):
        rows = {r["name"]: r for r in self.overview().json()["revenue_by_doctor"]}
        self.assertEqual(float(rows["Dr A"]["total"]), 250)
        self.assertEqual(rows["Dr A"]["count"], 2)
        self.assertEqual(float(rows["Dr B"]["total"]), 80)

    def test_appointment_and_patient_statistics(self):
        data = self.overview().json()
        self.assertEqual(data["appointments"]["by_status"],
                         {"completed": 1, "cancelled": 1, "no_show": 1})
        self.assertEqual(data["patients"]["returning"], 1)   # P1, counted once
        self.assertEqual(data["patients"]["total"], 2)

    def test_attendance_by_clinic(self):
        clinics = {c["name"]: c for c in self.overview().json()["clinics"]}
        self.assertEqual(clinics["Clinic A"]["attendance_rate"], 100.0)
        self.assertEqual(clinics["Clinic B"]["attendance_rate"], 0.0)
        self.assertEqual(clinics["Clinic B"]["absences"], 1)

    def test_filtering_by_clinic(self):
        data = self.overview(branch=str(self.b.uuid)).json()
        self.assertEqual(float(data["finance"]["revenue"]), 80)
        self.assertEqual([c["name"] for c in data["clinics"]], ["Clinic B"])

    def test_filtering_by_date(self):
        past = date.today() - timedelta(days=30)
        data = self.overview(**{"from": (past - timedelta(days=5)).isoformat(), "to": past.isoformat()}).json()
        self.assertEqual(float(data["finance"]["revenue"]), 0)
        self.assertEqual(float(data["finance"]["expenses"]), 0)

    def test_another_groups_data_never_appears(self):
        data = self.overview().json()
        self.assertNotIn("999", str(data["finance"]))
        self.assertNotIn("Their clinic", [b["name"] for b in data["branches"]])
        self.assertEqual(self.overview(branch=str(self.their_branch.uuid)).status_code, 404)

    def test_only_the_owner_sees_it(self):
        for user in (self.admin, self.doctor):
            with self.subTest(role=user.role.name):
                self.client.logout()
                self.client.login(email=user.email, password=PASSWORD)
                self.assertEqual(self.overview().status_code, 403)

    def test_bad_dates_are_refused(self):
        self.assertEqual(self.overview(**{"from": "not-a-date"}).status_code, 400)
        self.assertEqual(self.overview(**{"from": "2026-02-10", "to": "2026-02-01"}).status_code, 400)
