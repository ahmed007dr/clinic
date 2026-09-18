"""The queue's turn numbers: how many are ahead of a booking, per doctor.

The group owner's rules (2026-09-18): the count is per doctor; someone already
in with the doctor is shown separately and is never "ahead"; the oldest
booking is first.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from appointments.models import Appointment
from branches.models import Branch
from employees.models import Employee, EmployeeType
from patients.models import Patient
from tenants.context import tenant_context
from tenants.models import Tenant

User = get_user_model()
PASSWORD = "pass12345"


class QueueTurnTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            self.branch = Branch.all_objects.create(tenant=self.tenant, name="Qt", code="QT")
            self.other_branch = Branch.all_objects.create(tenant=self.tenant, name="Qt2", code="QT2")
            roles = {
                n: ClinicRole.all_objects.get_or_create(tenant=self.tenant, name=n)[0]
                for n in ("Reception", "Doctor")
            }
            doctor_type = EmployeeType.all_objects.get_or_create(tenant=self.tenant, name="Doctor")[0]
            self.nadia = self.doctor("Dr Nadia", "QT-1", doctor_type)
            self.omar = self.doctor("Dr Omar", "QT-2", doctor_type)
            self.patients = [
                Patient.all_objects.create(tenant=self.tenant, name=f"P{i}", branch=self.branch)
                for i in range(5)
            ]
        User.objects.create_user(
            username="desk-qt", email="desk-qt@x.local", password=PASSWORD,
            tenant=self.tenant, role=roles["Reception"], branch=self.branch,
        )
        User.objects.create_user(
            username="desk-qt2", email="desk-qt2@x.local", password=PASSWORD,
            tenant=self.tenant, role=roles["Reception"], branch=self.other_branch,
        )
        self.client.login(email="desk-qt@x.local", password=PASSWORD)

    def doctor(self, name, national_id, doctor_type):
        return Employee.all_objects.create(
            tenant=self.tenant, name=name, branch=self.branch, employee_type=doctor_type,
            national_id=national_id, salary_value=0,
        )

    def book(self, patient, *, minutes=0, status="waiting", doctor="nadia"):
        doctor = {"nadia": self.nadia, "omar": self.omar, None: None}[doctor]
        with tenant_context(self.tenant):
            return Appointment.all_objects.create(
                tenant=self.tenant, patient=patient, doctor=doctor, branch=self.branch,
                status=status, scheduled_date=timezone.now() + timedelta(minutes=minutes),
            )

    def queue(self, **params):
        response = self.client.get(reverse("api:appointment-waiting"), params)
        self.assertEqual(response.status_code, 200, response.content)
        return {row["uuid"]: row for row in response.json()}, [row["uuid"] for row in response.json()]

    def test_oldest_first_and_counted_from_the_front(self):
        late = self.book(self.patients[0], minutes=10)
        early = self.book(self.patients[1], minutes=-10)
        middle = self.book(self.patients[2], minutes=0)
        rows, order = self.queue()
        self.assertEqual(order, [str(early.uuid), str(middle.uuid), str(late.uuid)])
        self.assertEqual([rows[u]["ahead_count"] for u in order], [0, 1, 2])

    def test_each_doctor_has_their_own_queue(self):
        self.book(self.patients[0], minutes=-10, doctor="nadia")
        theirs = self.book(self.patients[1], minutes=0, doctor="omar")
        rows, _ = self.queue()
        self.assertEqual(rows[str(theirs.uuid)]["ahead_count"], 0)

    def test_someone_with_the_doctor_is_listed_but_not_counted_ahead(self):
        inside = self.book(self.patients[0], minutes=-20, status="entered")
        waiting = self.book(self.patients[1], minutes=0)
        rows, _ = self.queue()
        self.assertIsNone(rows[str(inside.uuid)]["ahead_count"])
        self.assertEqual(rows[str(waiting.uuid)]["ahead_count"], 0)

    def test_called_and_quick_bookings_are_in_the_queue_and_counted(self):
        called = self.book(self.patients[0], minutes=-10, status="called")
        quick = self.book(self.patients[1], minutes=-5, status="quick")
        waiting = self.book(self.patients[2], minutes=0)
        rows, order = self.queue()
        self.assertEqual(order, [str(called.uuid), str(quick.uuid), str(waiting.uuid)])
        self.assertEqual(rows[str(waiting.uuid)]["ahead_count"], 2)

    def test_finished_cancelled_and_unconfirmed_bookings_do_not_count(self):
        for patient, status in zip(self.patients, ("completed", "cancelled", "no_show", "requested")):
            self.book(patient, minutes=-10, status=status)
        waiting = self.book(self.patients[4], minutes=0)
        rows, _ = self.queue()
        self.assertEqual(list(rows), [str(waiting.uuid)])
        self.assertEqual(rows[str(waiting.uuid)]["ahead_count"], 0)

    def test_a_booking_with_no_doctor_has_no_turn(self):
        booking = self.book(self.patients[0], doctor=None)
        rows, _ = self.queue()
        self.assertIsNone(rows[str(booking.uuid)]["ahead_count"])

    def test_a_search_does_not_shrink_the_count(self):
        self.book(self.patients[0], minutes=-10)
        target = self.book(self.patients[1], minutes=0)
        rows, _ = self.queue(search="P1")
        self.assertEqual(list(rows), [str(target.uuid)])
        self.assertEqual(rows[str(target.uuid)]["ahead_count"], 1)

    def test_another_branchs_queue_is_invisible_and_uncounted(self):
        booking = self.book(self.patients[0], minutes=0)
        self.client.logout()
        self.client.login(email="desk-qt2@x.local", password=PASSWORD)
        rows, _ = self.queue()
        self.assertNotIn(str(booking.uuid), rows)
