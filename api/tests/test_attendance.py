"""Attendance: recorded per clinic, one row per employee per day."""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import ClinicRole
from branches.models import Branch
from employees.models import Attendance, Employee
from tenants.context import tenant_context
from tenants.models import Tenant

User = get_user_model()
PASSWORD = "pass12345"


class AttendanceTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            roles = {n: ClinicRole.all_objects.get_or_create(tenant=self.tenant, name=n)[0]
                     for n in ("Owner", "Admin", "Doctor")}
            self.a = Branch.all_objects.create(tenant=self.tenant, name="Clinic A", code="AA")
            self.b = Branch.all_objects.create(tenant=self.tenant, name="Clinic B", code="AB")
            self.emp_a = Employee.all_objects.create(tenant=self.tenant, name="Emp A", branch=self.a,
                                                     national_id="1", salary_value=1)
            self.emp_b = Employee.all_objects.create(tenant=self.tenant, name="Emp B", branch=self.b,
                                                     national_id="2", salary_value=1)
        for name, role in (("admin", "Admin"), ("owner", "Owner"), ("doctor", "Doctor")):
            User.objects.create_user(username=name, email=f"{name}@att.local", password=PASSWORD,
                                     tenant=self.tenant, role=roles[role], branch=self.a)
        self.today = date.today().isoformat()

    def login(self, name):
        self.client.logout()
        self.client.login(email=f"{name}@att.local", password=PASSWORD)

    def save_sheet(self, entries, day=None):
        return self.client.post(reverse("api:attendance-sheet"), {"date": day or self.today, "entries": entries},
                                content_type="application/json")

    def rows(self):
        with tenant_context(self.tenant):
            return list(Attendance.all_objects.filter(tenant=self.tenant).values_list("employee__name", "status"))

    def test_a_clinic_admin_records_their_clinic(self):
        self.login("admin")
        sheet = self.client.get(reverse("api:attendance-sheet")).json()
        self.assertEqual([e["employee_name"] for e in sheet["entries"]], ["Emp A"])
        response = self.save_sheet([{"employee": str(self.emp_a.uuid), "status": "late",
                                     "check_in": "09:20", "minutes_late": 20}])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.rows(), [("Emp A", "late")])

    def test_a_clinic_admin_cannot_record_another_clinic(self):
        self.login("admin")
        response = self.save_sheet([{"employee": str(self.emp_b.uuid), "status": "absent"}])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.rows(), [])

    def test_the_owner_records_every_clinic(self):
        self.login("owner")
        response = self.save_sheet([{"employee": str(self.emp_a.uuid), "status": "present"},
                                    {"employee": str(self.emp_b.uuid), "status": "absent"}])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(sorted(self.rows()), [("Emp A", "present"), ("Emp B", "absent")])

    def test_one_row_per_employee_per_day(self):
        self.login("admin")
        self.save_sheet([{"employee": str(self.emp_a.uuid), "status": "present", "check_in": "09:00"}])
        self.save_sheet([{"employee": str(self.emp_a.uuid), "status": "absent", "check_in": "09:00"}])
        self.assertEqual(self.rows(), [("Emp A", "absent")])
        with tenant_context(self.tenant):
            self.assertIsNone(Attendance.all_objects.get(employee=self.emp_a).check_in)  # absent clears times

    def test_leaving_before_arriving_is_refused(self):
        self.login("admin")
        response = self.client.post(reverse("api:attendance-list"), {
            "employee": str(self.emp_a.uuid), "date": self.today, "status": "present",
            "check_in": "10:00", "check_out": "09:00",
        }, content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_a_future_day_is_refused(self):
        self.login("admin")
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        self.assertEqual(self.save_sheet([{"employee": str(self.emp_a.uuid), "status": "present"}],
                                         day=tomorrow).status_code, 400)

    def test_doctors_do_not_record_attendance(self):
        self.login("doctor")
        self.assertEqual(self.client.get(reverse("api:attendance-sheet")).status_code, 403)
