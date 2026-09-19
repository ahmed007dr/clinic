"""Booking from the catalogue (docs/15, Phase 5): service → clinic → doctor → time.

The server re-decides everything the page showed: the choice must still be
bookable, the time must still be one of the doctor's offered times, and a
patient of one clinic reaches another only when the group allows it. By default
the result is a *request* that holds no time; a clinic that confirms website
bookings at once gets a confirmed one that does.
"""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from appointments.models import Appointment, DoctorSchedule
from billing.models import DoctorServiceRate
from branches.models import Branch
from employees.models import Employee, EmployeeType
from services.models import BranchService, Service
from tenants.context import tenant_context

from .tests import PASSWORD, PortalBase

User = get_user_model()


def next_monday(at_least_days=2):
    day = timezone.now().date() + timedelta(days=at_least_days)
    while day.weekday() != 0:
        day += timedelta(days=1)
    return day


class BookingBase(PortalBase):
    def setUp(self):
        super().setUp()
        self.day = next_monday()
        with tenant_context(self.a):
            self.second = Branch.all_objects.create(tenant=self.a, name="Second", code="SC")
            doctor_type, _ = EmployeeType.all_objects.get_or_create(tenant=self.a, name="Doctor")
            self.service = Service.all_objects.create(
                tenant=self.a, name="Laser", base_price=Decimal("100"), duration_minutes=45
            )

            def doctor(name, national_id, branch, price):
                employee = Employee.all_objects.create(
                    tenant=self.a, name=name, branch=branch, employee_type=doctor_type,
                    national_id=national_id, salary_value=0, show_publicly=True,
                )
                DoctorServiceRate.all_objects.create(tenant=self.a, doctor=employee, service=self.service, price=price)
                DoctorSchedule.all_objects.create(
                    tenant=self.a, doctor=employee, branch=branch, weekday=0, start_time=time(9), end_time=time(13),
                )
                BranchService.all_objects.get_or_create(tenant=self.a, branch=branch, service=self.service)
                return employee

            self.dr_main = doctor("Dr Main", "M1", self.branch, Decimal("150"))
            self.dr_second = doctor("Dr Second", "S1", self.second, Decimal("250"))
        self.enrol(self.alice)

    def slot(self, hhmm="09:00"):
        return f"{self.day.isoformat()} {hhmm}"

    def body(self, **overrides):
        body = {
            "service": str(self.service.uuid), "branch": str(self.branch.uuid),
            "doctor": str(self.dr_main.uuid), "slot": self.slot(),
        }
        body.update(overrides)
        return body

    def book(self, client=None, **overrides):
        return (client or self.client).post(
            self.url("appointments"), self.body(**overrides), content_type="application/json"
        )

    def appointments(self, **filters):
        with tenant_context(self.a):
            return list(Appointment.objects.filter(**filters))

    def confirm_at_once(self, branch=None):
        Branch.all_objects.filter(pk=(branch or self.branch).pk).update(online_booking_confirms_at_once=True)


class RequestModeTests(BookingBase):
    def test_a_booking_is_a_request_that_carries_the_choice_and_the_contract_price(self):
        response = self.book(notes="  itchy  ")
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual((body["status"], body["doctor_name"], body["service_name"], body["branch_name"]),
                         ("requested", "Dr Main", "Laser", "Main"))
        (appointment,) = self.appointments(patient=self.alice)
        self.assertEqual(appointment.source, "portal")
        self.assertEqual(appointment.price, Decimal("150"))  # the contract's, not the catalogue's 100
        self.assertEqual(appointment.scheduled_date, datetime.combine(self.day, time(9)))
        self.assertEqual(appointment.notes, "[طلب من بوابة المرضى] itchy")
        self.assertIsNone(appointment.created_by)

    def test_a_request_holds_no_time_so_another_patient_may_ask_for_the_same_one(self):
        self.assertEqual(self.book().status_code, 201)
        other = Client()
        self.enrol(self.bob, client=other)
        self.assertEqual(self.book(client=other).status_code, 201)
        self.assertEqual(len(self.appointments(status="requested")), 2)

    def test_the_time_must_be_one_the_doctor_is_offered(self):
        for slot in ("10:10", "13:00", "08:00", "23:30"):  # off the 45-minute grid, closing, before opening
            with self.subTest(slot=slot):
                self.assertEqual(self.book(slot=self.slot(slot)).status_code, 409)
        past = (timezone.now().date() - timedelta(days=7)).isoformat() + " 09:00"
        self.assertEqual(self.book(slot=past).status_code, 409)
        self.assertEqual(self.appointments(), [])

    def test_a_malformed_time_is_refused(self):
        for bad in ("", "tomorrow", "2030-13-40 09:00"):
            with self.subTest(bad=bad):
                self.assertEqual(self.book(slot=bad).status_code, 400)

    def test_only_what_the_catalogue_offers_can_be_booked(self):
        with tenant_context(self.a):
            hidden = Employee.all_objects.get(pk=self.dr_main.pk)
        cases = {
            "a doctor of another clinic": {"doctor": str(self.dr_second.uuid)},
            "an unknown doctor": {"doctor": "00000000-0000-0000-0000-000000000000"},
            "no doctor": {"doctor": ""},
            "not a uuid": {"service": "laser"},
        }
        for name, override in cases.items():
            with self.subTest(name):
                self.assertEqual(self.book(**override).status_code, 400)
        # Switching the service off in the clinic, stopping it, hiding the doctor, or removing
        # the contract each take the choice away.
        for undo in (
            lambda: BranchService.all_objects.filter(branch=self.branch).update(is_active=False),
            lambda: BranchService.all_objects.filter(branch=self.branch).update(is_active=True, online_bookable=False),
            lambda: (BranchService.all_objects.filter(branch=self.branch).update(online_bookable=True),
                     Service.all_objects.filter(pk=self.service.pk).update(is_active=False)),
            lambda: (Service.all_objects.filter(pk=self.service.pk).update(is_active=True),
                     Employee.all_objects.filter(pk=hidden.pk).update(show_publicly=False)),
            lambda: (Employee.all_objects.filter(pk=hidden.pk).update(show_publicly=True),
                     DoctorServiceRate.all_objects.filter(doctor=hidden).update(is_active=False)),
        ):
            undo()
            self.assertEqual(self.book().status_code, 400)
        DoctorServiceRate.all_objects.filter(doctor=hidden).update(is_active=True)
        self.assertEqual(self.book().status_code, 201)  # everything restored: bookable again

    def test_the_old_free_time_request_still_works_without_a_clinic(self):
        when = (timezone.now() + timedelta(days=3)).replace(microsecond=0).isoformat()
        response = self.client.post(self.url("appointments"), {"scheduled_date": when, "notes": "call me"},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 201, response.content)

    def test_three_unconfirmed_requests_at_most(self):
        for hhmm in ("09:00", "09:45", "10:30"):
            self.assertEqual(self.book(slot=self.slot(hhmm)).status_code, 201)
        self.assertEqual(self.book(slot=self.slot("11:15")).status_code, 400)

    def test_the_same_doctor_and_time_twice_is_refused(self):
        self.assertEqual(self.book().status_code, 201)
        self.assertEqual(self.book().status_code, 400)

    def test_it_needs_a_portal_sign_in(self):
        self.assertIn(self.book(client=Client()).status_code, (401, 403))
        self.assertEqual(self.appointments(patient=self.alice), [])

    def test_the_patient_lists_their_booking_with_its_clinic(self):
        self.book()
        rows = self.client.get(self.url("appointments")).json()
        self.assertEqual([(r["branch_name"], r["status"]) for r in rows], [("Main", "requested")])


class InstantConfirmTests(BookingBase):
    def setUp(self):
        super().setUp()
        self.confirm_at_once()

    def test_a_confirming_clinic_books_at_once_and_the_time_is_held(self):
        response = self.book()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["status"], "waiting")
        # The doctor no longer offers that time to anyone.
        self.client.logout()
        offered = self.client.get(self.url("catalog-availability"), {
            "service": str(self.service.uuid), "branch": str(self.branch.uuid),
            "doctor": str(self.dr_main.uuid), "date": self.day.isoformat(),
        }).json()["slots"]
        self.assertNotIn("09:00", offered)
        self.assertIn("09:45", offered)

    def test_the_second_person_to_choose_the_same_time_is_told_it_is_gone(self):
        self.assertEqual(self.book().status_code, 201)
        other = Client()
        self.enrol(self.bob, client=other)
        response = other.post(self.url("appointments"), self.body(), content_type="application/json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(len(self.appointments(status="waiting")), 1)

    def test_a_held_time_stays_held_whatever_mode_the_clinic_is_in_later(self):
        self.assertEqual(self.book().status_code, 201)
        Branch.all_objects.filter(pk=self.branch.pk).update(online_booking_confirms_at_once=False)
        other = Client()
        self.enrol(self.bob, client=other)
        # Back in request mode, the time the confirmed booking holds is still not offered.
        self.assertEqual(other.post(self.url("appointments"), self.body(), content_type="application/json").status_code, 409)


class OtherClinicTests(BookingBase):
    """Alice belongs to Main; Second is another clinic of the same group."""

    def other_clinic(self):
        return {"branch": str(self.second.uuid), "doctor": str(self.dr_second.uuid)}

    def test_by_default_a_patient_books_at_their_own_clinic_only(self):
        response = self.book(**self.other_clinic())
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.appointments(patient=self.alice), [])

    def test_when_the_group_allows_it_the_booking_lands_at_the_chosen_clinic(self):
        self.a.portal_allow_other_branches = True
        self.a.save()
        response = self.book(**self.other_clinic())
        self.assertEqual(response.status_code, 201, response.content)
        (appointment,) = self.appointments(patient=self.alice)
        self.assertEqual((appointment.branch, appointment.doctor), (self.second, self.dr_second))
        self.assertEqual(appointment.price, Decimal("250"))
        # Alice's own clinic on file is untouched.
        with tenant_context(self.a):
            self.alice.refresh_from_db()
            self.assertEqual(self.alice.branch, self.branch)

    def test_staff_of_the_chosen_clinic_see_the_request_and_its_source(self):
        self.a.portal_allow_other_branches = True
        self.a.save()
        self.book(**self.other_clinic())
        with tenant_context(self.a):
            role = ClinicRole.all_objects.get_or_create(tenant=self.a, name="Reception")[0]
        for name, branch in (("rec-second", self.second), ("rec-main", self.branch)):
            User.objects.create_user(username=name, email=f"{name}@t.local", password="pass12345",
                                     tenant=self.a, role=role, branch=branch)
        staff = Client()
        staff.login(email="rec-second@t.local", password="pass12345")
        rows = staff.get(reverse("api:appointment-list")).json()["results"]
        self.assertEqual([(r["patient_name"], r["source"], r["status"]) for r in rows], [("Alice", "portal", "requested")])
        # The clinic Alice belongs to does not see a booking made elsewhere.
        home = Client()
        home.login(email="rec-main@t.local", password="pass12345")
        self.assertEqual(home.get(reverse("api:appointment-list")).json()["results"], [])
        # The booking source can be filtered.
        self.assertEqual(len(staff.get(reverse("api:appointment-list"), {"source": "portal"}).json()["results"]), 1)
        self.assertEqual(staff.get(reverse("api:appointment-list"), {"source": "phone"}).json()["results"], [])


class SourceTests(BookingBase):
    def setUp(self):
        super().setUp()
        with tenant_context(self.a):
            role = ClinicRole.all_objects.get_or_create(tenant=self.a, name="Reception")[0]
        User.objects.create_user(username="rec", email="rec@t.local", password="pass12345",
                                 tenant=self.a, role=role, branch=self.branch)
        self.staff = Client()
        self.staff.login(email="rec@t.local", password="pass12345")

    def test_a_staff_booking_defaults_to_reception_and_may_say_phone_or_whatsapp(self):
        body = {"patient": str(self.alice.uuid), "scheduled_date": self.slot(), "branch": str(self.branch.uuid)}
        first = self.staff.post(reverse("api:appointment-list"), body, content_type="application/json")
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(first.json()["source"], "reception")
        second = self.staff.post(reverse("api:appointment-list"), {**body, "source": "whatsapp"}, content_type="application/json")
        self.assertEqual((second.status_code, second.json()["source"]), (201, "whatsapp"))

    def test_staff_cannot_claim_a_booking_came_from_the_website(self):
        body = {"patient": str(self.alice.uuid), "scheduled_date": self.slot(), "branch": str(self.branch.uuid), "source": "portal"}
        self.assertEqual(self.staff.post(reverse("api:appointment-list"), body, content_type="application/json").status_code, 400)

    def test_a_website_booking_keeps_its_source(self):
        self.book()
        (appointment,) = self.appointments(patient=self.alice)
        response = self.staff.patch(reverse("api:appointment-detail", args=[appointment.uuid]), {"source": "phone"},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)
        confirmed = self.staff.post(reverse("api:appointment-set-status", args=[appointment.uuid]), {"status": "waiting"},
                                    content_type="application/json")
        self.assertEqual(confirmed.status_code, 200, confirmed.content)
        self.assertEqual(confirmed.json()["source"], "portal")

    def test_the_backfill_marks_only_the_website_bookings_made_before_the_field_existed(self):
        from importlib import import_module

        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        self.book()
        with tenant_context(self.a):
            desk = Appointment.objects.create(
                tenant=self.a, patient=self.bob, branch=self.branch, scheduled_date=datetime.now(), notes="walk-in",
            )
            Appointment.objects.filter(patient=self.alice).update(source="reception")  # as before the field
        state = MigrationExecutor(connection).loader.project_state([
            ("appointments", "0010_appointment_source"), ("tenants", "0021_tenant_public_media"),
        ])
        import_module("appointments.migrations.0011_backfill_appointment_source").backfill(state.apps, None)
        with tenant_context(self.a):
            self.assertEqual(Appointment.objects.get(patient=self.alice).source, "portal")
            self.assertEqual(Appointment.objects.get(pk=desk.pk).source, "reception")
