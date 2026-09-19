"""Telling people about a booking (docs/15, Phase 9).

The patient hears by e-mail (through the clinic's e-mail log) that the request
arrived, and when the clinic confirms, cancels or moves it, plus a reminder the
day before. The clinic's own front desk hears in-app about a new website
request, a cancellation and a request to move — and only the desk of *that*
clinic. A mail server that is down never stops a booking.
"""

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from appointments.models import Appointment
from notifications.models import EmailLog, Notification
from tenants.context import tenant_context

from .test_my_bookings import MyBookingBase

User = get_user_model()


class NotifyBase(MyBookingBase):
    def setUp(self):
        super().setUp()
        with tenant_context(self.a):
            self.alice.email = "alice@patient.example"
            self.alice.save()
            reception = ClinicRole.all_objects.get_or_create(tenant=self.a, name="Reception")[0]
            admin = ClinicRole.all_objects.get_or_create(tenant=self.a, name="Admin")[0]
            doctor = ClinicRole.all_objects.get_or_create(tenant=self.a, name="Doctor")[0]
        for name, role, branch in (
            ("rec", reception, self.branch), ("adm", admin, self.branch),
            ("doc", doctor, self.branch), ("rec-second", reception, self.second),
        ):
            User.objects.create_user(username=name, email=f"{name}@t.local", password="pass12345",
                                     tenant=self.a, role=role, branch=branch)
        self.staff = Client()
        self.staff.login(email="rec@t.local", password="pass12345")
        mail.outbox.clear()

    def notices(self, username):
        with tenant_context(self.a):
            return list(Notification.objects.filter(user__username=username))

    def mails(self, to="alice@patient.example"):
        return [m for m in mail.outbox if to in m.to]

    def logged(self, kind):
        with tenant_context(self.a):
            return list(EmailLog.objects.filter(kind=kind))

    def do(self, callable_):
        """Run a request and the on-commit hooks it queued (a TestCase never commits)."""
        with self.captureOnCommitCallbacks(execute=True):
            return callable_()

    def set_status(self, appointment, status):
        return self.do(lambda: self.staff.post(
            reverse("api:appointment-set-status", args=[appointment.uuid]), {"status": status},
            content_type="application/json"))


class NewRequestTests(NotifyBase):
    def test_the_patient_is_told_it_arrived_and_the_desk_is_told_to_call(self):
        response = self.do(self.book)
        self.assertEqual(response.status_code, 201, response.content)
        (message,) = self.mails()
        self.assertIn("طلب موعدك", message.subject)
        for expected in ("Dr Main", "Laser", "Main", self.day.isoformat(), "09:00"):
            self.assertIn(expected, message.body)
        self.assertEqual([r.kind for r in self.logged("booking_received")], ["booking_received"])
        for username in ("rec", "adm"):
            (notice,) = self.notices(username)
            self.assertEqual((notice.type, notice.title), ("appointment", "طلب موعد جديد من الموقع"))
            self.assertIn("Alice", notice.message)
        # Not the doctor, and not another clinic's desk.
        self.assertEqual(self.notices("doc"), [])
        self.assertEqual(self.notices("rec-second"), [])

    def test_a_clinic_that_confirms_at_once_sends_the_confirmation_instead(self):
        self.confirm_at_once()
        self.do(self.book)
        (message,) = self.mails()
        self.assertIn("تم تأكيد موعدك", message.subject)
        self.assertEqual(self.logged("booking_received"), [])
        self.assertEqual(len(self.logged("booking_confirmed")), 1)

    def test_a_patient_with_no_address_gets_no_mail_but_the_desk_is_still_told(self):
        with tenant_context(self.a):
            self.alice.email = ""
            self.alice.save()
        self.assertEqual(self.do(self.book).status_code, 201)
        self.assertEqual(mail.outbox, [])
        self.assertEqual(len(self.notices("rec")), 1)

    def test_a_broken_mail_server_never_stops_a_booking(self):
        with mock.patch("platform_admin.mailer.sender_for", side_effect=RuntimeError("smtp down")):
            response = self.do(self.book)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(len(self.appointments(patient=self.alice)), 1)
        self.assertEqual(len(self.notices("rec")), 1)

    def test_nothing_is_sent_for_a_booking_that_was_refused(self):
        self.do(lambda: self.book(slot=self.slot("10:10")))  # off the doctor's grid
        self.assertEqual(mail.outbox, [])
        self.assertEqual(self.notices("rec"), [])


class ClinicChangesTests(NotifyBase):
    def setUp(self):
        super().setUp()
        self.do(self.book)
        mail.outbox.clear()
        (self.booking,) = self.appointments(patient=self.alice)

    def test_confirming_tells_the_patient(self):
        self.assertEqual(self.set_status(self.booking, "waiting").status_code, 200)
        (message,) = self.mails()
        self.assertIn("تم تأكيد موعدك", message.subject)
        self.assertIn("الدفع عند الوصول", message.body)

    def test_declining_tells_the_patient(self):
        self.set_status(self.booking, "cancelled")
        (message,) = self.mails()
        self.assertIn("تم إلغاء موعدك", message.subject)

    def test_other_moves_through_the_queue_send_nothing(self):
        self.set_status(self.booking, "waiting")
        mail.outbox.clear()
        for status in ("called", "entered"):
            self.set_status(self.booking, status)
        self.assertEqual(mail.outbox, [])

    def test_changing_the_time_of_a_confirmed_booking_tells_the_patient(self):
        self.set_status(self.booking, "waiting")
        mail.outbox.clear()
        moved = (timezone.now() + timedelta(days=6)).replace(microsecond=0)
        response = self.do(lambda: self.staff.patch(
            reverse("api:appointment-detail", args=[self.booking.uuid]),
            {"scheduled_date": moved.strftime("%Y-%m-%d %H:%M")}, content_type="application/json"))
        self.assertEqual(response.status_code, 200, response.content)
        (message,) = self.mails()
        self.assertIn("تم تعديل موعدك", message.subject)
        self.assertIn(moved.strftime("%H:%M"), message.body)

    def test_fixing_the_time_of_an_unconfirmed_request_is_silent_until_it_is_confirmed(self):
        moved = (timezone.now() + timedelta(days=6)).strftime("%Y-%m-%d %H:%M")
        self.do(lambda: self.staff.patch(reverse("api:appointment-detail", args=[self.booking.uuid]),
                                         {"scheduled_date": moved}, content_type="application/json"))
        self.assertEqual(mail.outbox, [])
        self.set_status(self.booking, "waiting")
        (message,) = self.mails()
        self.assertIn("تم تأكيد موعدك", message.subject)
        self.assertIn(moved[-5:], message.body)

    def test_a_confirmation_from_the_edit_form_is_announced_too(self):
        self.do(lambda: self.staff.patch(reverse("api:appointment-detail", args=[self.booking.uuid]),
                                         {"status": "waiting"}, content_type="application/json"))
        self.assertEqual(len(self.mails()), 1)


class WhoMayBeEmailedTests(NotifyBase):
    def desk_booking(self, **patient_fields):
        with tenant_context(self.a):
            for key, value in patient_fields.items():
                setattr(self.bob, key, value)
            self.bob.email = "bob@patient.example"
            self.bob.save()
            return Appointment.objects.create(
                tenant=self.a, patient=self.bob, branch=self.branch, status="requested",
                scheduled_date=timezone.now() + timedelta(days=3), source="reception",
            )

    def test_a_walk_in_patient_who_never_agreed_to_email_is_not_emailed(self):
        booking = self.desk_booking(contact_by_email=False)
        self.set_status(booking, "waiting")
        self.assertEqual(self.mails("bob@patient.example"), [])

    def test_one_who_agreed_is(self):
        booking = self.desk_booking(contact_by_email=True)
        self.set_status(booking, "waiting")
        self.assertEqual(len(self.mails("bob@patient.example")), 1)

    def test_a_website_patient_is_emailed_even_for_a_booking_made_at_the_desk(self):
        booking = self.desk_booking(contact_by_email=False)
        self.enrol(self.bob)  # has a portal account
        self.set_status(booking, "waiting")
        self.assertEqual(len(self.mails("bob@patient.example")), 1)


class PatientActionsTests(NotifyBase):
    def test_the_desk_hears_when_a_patient_cancels_or_asks_to_move(self):
        booking = self.make(status="waiting", hours_ahead=72)
        self.do(lambda: self.reschedule(booking, f"{self.day.isoformat()} 09:45"))
        (notice,) = self.notices("rec")
        self.assertEqual(notice.title, "طلب تغيير موعد")
        self.do(lambda: self.cancel(booking))
        titles = sorted(n.title for n in self.notices("rec"))
        self.assertEqual(titles, ["ألغى المريض حجزه", "طلب تغيير موعد"])
        self.assertEqual(self.notices("rec-second"), [])


class ReminderTests(NotifyBase):
    def tomorrow_at(self, hour, **fields):
        day = timezone.now().date() + timedelta(days=1)
        with tenant_context(self.a):
            return Appointment.objects.create(
                tenant=self.a, patient=self.alice, branch=self.branch, doctor=self.dr_main, service=self.service,
                status=fields.pop("status", "waiting"), source="portal", price=150,
                scheduled_date=timezone.now().replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(days=1),
                **fields,
            ), day

    def test_tomorrows_confirmed_bookings_get_one_reminder(self):
        self.tomorrow_at(10)
        call_command("send_booking_reminders", stdout=mock.MagicMock())
        (message,) = self.mails()
        self.assertIn("تذكير بموعدك", message.subject)
        self.assertIn("Dr Main", message.body)
        self.assertEqual(len(self.logged("booking_reminder")), 1)

    def test_running_it_again_the_same_day_sends_nothing_more(self):
        self.tomorrow_at(10)
        call_command("send_booking_reminders", stdout=mock.MagicMock())
        call_command("send_booking_reminders", stdout=mock.MagicMock())
        self.assertEqual(len(self.mails()), 1)

    def test_only_bookings_still_ahead_and_wanted_are_reminded(self):
        for status in ("requested", "cancelled", "no_show", "completed", "entered"):
            self.tomorrow_at(9, status=status)
        with tenant_context(self.a):
            self.alice.email = ""
            self.alice.save()
        self.tomorrow_at(11)  # confirmed, but no address
        call_command("send_booking_reminders", stdout=mock.MagicMock())
        self.assertEqual(mail.outbox, [])

    def test_other_days_are_left_alone_and_a_date_can_be_named(self):
        booking, day = self.tomorrow_at(10)
        call_command("send_booking_reminders", "--date", (day + timedelta(days=3)).isoformat(), stdout=mock.MagicMock())
        self.assertEqual(mail.outbox, [])
        call_command("send_booking_reminders", "--date", day.isoformat(), stdout=mock.MagicMock())
        self.assertEqual(len(self.mails()), 1)

    def test_a_group_that_is_not_running_is_skipped(self):
        self.tomorrow_at(10)
        self.a.status = "suspended"
        self.a.save()
        call_command("send_booking_reminders", stdout=mock.MagicMock())
        self.assertEqual(mail.outbox, [])
