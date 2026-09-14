"""The queue ticket: printable only for today's waiting queue, its content
follows the clinic's own design, and only reception (or admin/owner) prints it
(the group owner's rule, 2026-09-12)."""

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


class TicketTestsBase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            self.branch = Branch.all_objects.create(tenant=self.tenant, name="Ticket Branch", code="TK")
            self.other_branch = Branch.all_objects.create(tenant=self.tenant, name="Other Branch", code="TKO")
            roles = {
                n: ClinicRole.all_objects.get_or_create(tenant=self.tenant, name=n)[0]
                for n in ("Admin", "Doctor", "Reception")
            }
            doctor_type, _ = EmployeeType.all_objects.get_or_create(tenant=self.tenant, name="Doctor")
            self.doctor = Employee.all_objects.create(
                tenant=self.tenant, name="Dr Nadia", branch=self.branch,
                employee_type=doctor_type, national_id="TK-1", salary_value=0,
            )
            self.patient = Patient.all_objects.create(tenant=self.tenant, name="Youssef", branch=self.branch)
            self.other_patient = Patient.all_objects.create(tenant=self.tenant, name="Laila", branch=self.branch)
        self.desk = User.objects.create_user(
            username="desk-tk", email="desk-tk@x.local", password=PASSWORD,
            tenant=self.tenant, role=roles["Reception"], branch=self.branch,
        )
        self.doc_user = User.objects.create_user(
            username="doc-tk", email="doc-tk@x.local", password=PASSWORD,
            tenant=self.tenant, role=roles["Doctor"], branch=self.branch, employee=self.doctor,
        )
        self.other_desk = User.objects.create_user(
            username="desk-tk-2", email="desk-tk-2@x.local", password=PASSWORD,
            tenant=self.tenant, role=roles["Reception"], branch=self.other_branch,
        )

    def book(self, patient, *, minutes=0, status="waiting", doctor=None):
        with tenant_context(self.tenant):
            return Appointment.all_objects.create(
                tenant=self.tenant, patient=patient, doctor=doctor if doctor is not None else self.doctor,
                branch=self.branch, status=status,
                scheduled_date=timezone.now() + timedelta(minutes=minutes),
            )

    def ticket_url(self, appointment):
        return reverse("appointments:appointment_ticket_print", args=[appointment.uuid])


class QueueTicketContentTests(TicketTestsBase):
    def setUp(self):
        super().setUp()
        self.client.login(email="desk-tk@x.local", password=PASSWORD)

    def test_a_lone_patient_is_told_their_turn_is_now(self):
        appointment = self.book(self.patient)
        response = self.client.get(self.ticket_url(appointment))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("Youssef", body)
        self.assertIn("Dr Nadia", body)
        self.assertIn(appointment.serial_number, body)
        self.assertIn("دورك الآن", body)

    def test_someone_ahead_for_the_same_doctor_is_counted(self):
        first = self.book(self.patient, minutes=0)
        second = self.book(self.other_patient, minutes=5)
        body = self.client.get(self.ticket_url(second)).content.decode()
        self.assertIn(">1<", body)
        self.assertIn("قبلك", body)
        # The first patient still has nobody ahead of them.
        first_body = self.client.get(self.ticket_url(first)).content.decode()
        self.assertIn("دورك الآن", first_body)

    def test_a_different_doctors_queue_does_not_count(self):
        with tenant_context(self.tenant):
            other_doctor = Employee.all_objects.create(
                tenant=self.tenant, name="Dr Omar", branch=self.branch,
                employee_type=self.doctor.employee_type, national_id="TK-2", salary_value=0,
            )
        self.book(self.patient, minutes=0)  # ahead, but for Dr Nadia
        theirs = self.book(self.other_patient, minutes=5, doctor=other_doctor)
        body = self.client.get(self.ticket_url(theirs)).content.decode()
        self.assertIn("دورك الآن", body)

    def test_someone_already_with_the_doctor_still_counts_as_ahead(self):
        self.book(self.patient, minutes=-5, status="entered")
        waiting = self.book(self.other_patient, minutes=0)
        body = self.client.get(self.ticket_url(waiting)).content.decode()
        self.assertIn(">1<", body)


class QueueTicketAvailabilityTests(TicketTestsBase):
    def setUp(self):
        super().setUp()
        self.client.login(email="desk-tk@x.local", password=PASSWORD)

    def test_a_future_bookings_ticket_cannot_be_printed_yet(self):
        appointment = self.book(self.patient, minutes=60 * 24 * 3)
        body = self.client.get(self.ticket_url(appointment)).content.decode()
        self.assertIn("تعذّر الطباعة", body)
        self.assertNotIn(appointment.serial_number, body)

    def test_a_completed_visit_has_no_more_ticket(self):
        appointment = self.book(self.patient, status="completed")
        body = self.client.get(self.ticket_url(appointment)).content.decode()
        self.assertIn("تعذّر الطباعة", body)

    def test_a_requested_but_unconfirmed_booking_has_no_ticket(self):
        appointment = self.book(self.patient, status="requested")
        body = self.client.get(self.ticket_url(appointment)).content.decode()
        self.assertIn("تعذّر الطباعة", body)


class QueueTicketPermissionTests(TicketTestsBase):
    def test_a_doctor_cannot_open_the_print_page(self):
        appointment = self.book(self.patient)
        self.client.login(email="doc-tk@x.local", password=PASSWORD)
        response = self.client.get(self.ticket_url(appointment))
        self.assertEqual(response.status_code, 302)  # user_passes_test bounces to login

    def test_receptions_own_branch_only(self):
        appointment = self.book(self.patient)
        self.client.login(email="desk-tk-2@x.local", password=PASSWORD)
        response = self.client.get(self.ticket_url(appointment))
        self.assertEqual(response.status_code, 404)

    def test_an_anonymous_visitor_is_redirected_to_login(self):
        appointment = self.book(self.patient)
        response = self.client.get(self.ticket_url(appointment))
        self.assertEqual(response.status_code, 302)


class QueueTicketDesignTests(TicketTestsBase):
    """The Admin/Owner controls which lines show — api/views/print_settings.py."""

    def setUp(self):
        super().setUp()
        self.client.login(email="desk-tk@x.local", password=PASSWORD)

    def test_hiding_fields_removes_them_from_the_printed_ticket(self):
        with tenant_context(self.tenant):
            self.branch.ticket_fields = ["checkin_time", "reception_name"]  # doctor & queue_position dropped
            self.branch.save(update_fields=["ticket_fields"])
        appointment = self.book(self.patient)
        body = self.client.get(self.ticket_url(appointment)).content.decode()
        self.assertNotIn("Dr Nadia", body)
        self.assertNotIn("دورك الآن", body)
        self.assertIn("desk-tk", body)  # reception_name still shown

    def test_a_new_clinic_with_no_choice_made_shows_everything(self):
        appointment = self.book(self.patient)
        body = self.client.get(self.ticket_url(appointment)).content.decode()
        self.assertIn("Dr Nadia", body)
        self.assertIn("دورك الآن", body)

    def test_paper_width_and_note_are_honoured(self):
        with tenant_context(self.tenant):
            self.branch.ticket_paper_width = "58mm"
            self.branch.ticket_note = "برجاء الانتظار حتى يُنادى اسمك"
            self.branch.save(update_fields=["ticket_paper_width", "ticket_note"])
        appointment = self.book(self.patient)
        body = self.client.get(self.ticket_url(appointment)).content.decode()
        self.assertIn("58mm", body)
        self.assertIn("برجاء الانتظار حتى يُنادى اسمك", body)
