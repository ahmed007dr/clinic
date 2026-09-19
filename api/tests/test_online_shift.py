"""Online payments are recorded inside a shift (the group owner's rule, 2026-09-19).

A payment the gateway confirmed is not "paid" — not on the booking, not in the
books, not shown to the patient — until it has been confirmed *and* recorded
inside a shift. The clinic's online payments are gathered in one shift of their
own, opened by the system and reviewed and closed by management; if recording
fails, nothing is kept and the gateway's next callback tries again.
"""

from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from api.tests.test_platform_business import (
    PASSWORD,
    PAYMOB,
    Kind,
    Scope,
    credential,
    make_group,
    paymob_signature,
    paymob_transaction,
)
from appointments.models import Appointment
from billing import shifts
from billing.models import CashShift, Payment
from branches.models import Branch
from patients.models import Patient
from platform_admin.models import ClinicCheckout
from portal.models import PortalInvitation
from tenants.context import tenant_context

User = get_user_model()


class OnlineShiftBase(TestCase):
    def setUp(self):
        cache.clear()
        self.tenant, self.branch = make_group("online-shift")
        with tenant_context(self.tenant):
            self.second = Branch.all_objects.create(tenant=self.tenant, name="Second", code="SEC")
            self.patient = Patient.all_objects.create(
                tenant=self.tenant, name="Mona", branch=self.branch, phone1="01000000009"
            )
            self.appointment = self.booking(self.branch, "300")
            _, token = PortalInvitation.issue(self.patient)
            roles = {n: ClinicRole.all_objects.get_or_create(tenant=self.tenant, name=n)[0]
                     for n in ("Owner", "Admin", "Reception")}
        for username, role, branch in (
            ("owner", "Owner", self.branch), ("admin-a", "Admin", self.branch),
            ("admin-b", "Admin", self.second), ("rec", "Reception", self.branch),
        ):
            User.objects.create_user(username=username, email=f"{username}@os.local", password=PASSWORD,
                                     tenant=self.tenant, role=roles[role], branch=branch)
        response = self.client.post(
            reverse("api:portal:accept-invite", kwargs={"slug": self.tenant.slug}),
            {"token": token, "password": PASSWORD}, content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        credential(Kind.PAYMOB, Scope.GROUP, PAYMOB, customer=self.tenant)

    def booking(self, branch, price):
        return Appointment.all_objects.create(
            tenant=self.tenant, patient=self.patient, branch=branch, status="waiting",
            scheduled_date=timezone.now(), price=Decimal(price),
        )

    def url(self, name, **kwargs):
        return reverse(f"api:portal:{name}", kwargs={"slug": self.tenant.slug, **kwargs})

    def start(self, appointment=None):
        replies = [{"token": "auth"}, {"id": 9}, {"token": "paykey"}]
        with mock.patch("platform_admin.gateways._request", side_effect=replies):
            response = self.client.post(
                self.url("appointment-pay", uuid=(appointment or self.appointment).uuid),
                {"method": "paymob"}, content_type="application/json",
            )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["reference"]

    def settle(self, reference, cents=30000, client=None):
        transaction_ = paymob_transaction(reference, cents)
        return (client or Client()).post(
            reverse("api:gateway-callback", args=["paymob"])
            + f"?hmac={paymob_signature(transaction_, PAYMOB['hmac_secret'])}",
            {"obj": transaction_}, content_type="application/json",
        )

    def online_shifts(self, **filters):
        return list(CashShift.all_objects.filter(kind="online", **filters).order_by("id"))

    def payments(self, appointment=None):
        return list(Payment.all_objects.filter(appointment=appointment or self.appointment))

    def staff(self, username):
        client = Client()
        self.assertTrue(client.login(email=f"{username}@os.local", password=PASSWORD))
        return client


class RecordedInAShiftTests(OnlineShiftBase):
    def test_a_confirmed_payment_is_recorded_inside_the_clinics_online_shift(self):
        reference = self.start()
        self.assertEqual(self.online_shifts(), [])  # nothing is opened by merely starting
        self.assertEqual(self.settle(reference).status_code, 200)
        (shift,) = self.online_shifts()
        self.assertEqual((shift.branch, shift.status, shift.user), (self.branch, "open", None))
        (payment,) = self.payments()
        self.assertEqual((payment.shift, payment.amount, payment.branch), (shift, Decimal("300.00"), self.branch))
        self.assertEqual(ClinicCheckout.objects.get(reference=reference).status, "confirmed")

    def test_every_online_payment_of_a_clinic_gathers_in_the_same_open_shift(self):
        other = self.booking(self.branch, "120")
        self.settle(self.start())
        self.settle(self.start(other), cents=12000)
        (shift,) = self.online_shifts()
        self.assertEqual(Payment.all_objects.filter(shift=shift).count(), 2)
        summary = shifts.summarize(shift)
        self.assertEqual(summary["revenue"], "420.00")
        self.assertEqual([(m["method"], m["revenue"], m["payments_count"]) for m in summary["by_method"]],
                         [("دفع إلكتروني", "420.00", 2)])

    def test_each_clinic_has_its_own_online_shift(self):
        elsewhere = self.booking(self.second, "50")
        self.settle(self.start())
        self.settle(self.start(elsewhere), cents=5000)
        self.assertEqual({s.branch_id for s in self.online_shifts()}, {self.branch.pk, self.second.pk})

    def test_after_management_closes_it_the_next_payment_opens_a_fresh_one(self):
        self.settle(self.start())
        (first,) = self.online_shifts()
        admin = User.objects.get(username="admin-a")
        with tenant_context(self.tenant):
            shifts.close_shift(admin, first)
        first.refresh_from_db()
        self.assertEqual(first.status, "closed")
        self.assertEqual(first.closing_summary["revenue"], "300.00")
        other = self.booking(self.branch, "80")
        self.settle(self.start(other), cents=8000)
        second = self.online_shifts(status="open")
        self.assertEqual(len(second), 1)
        self.assertNotEqual(second[0].pk, first.pk)
        self.assertEqual(Payment.all_objects.filter(shift=first).count(), 1)  # the closed one is untouched

    def test_only_one_online_shift_can_be_open_per_clinic(self):
        self.settle(self.start())
        with self.assertRaises(IntegrityError), transaction.atomic():
            CashShift.all_objects.create(tenant=self.tenant, branch=self.branch, kind="online", user=None)

    def test_a_person_shift_must_have_its_person(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            CashShift.all_objects.create(tenant=self.tenant, branch=self.branch, kind="cashier", user=None)

    def test_a_payment_that_exceeds_what_is_now_due_is_still_recorded_with_a_warning(self):
        reference = self.start()
        with tenant_context(self.tenant):
            # Paid at the desk while the patient was at the gateway.
            Payment.objects.create(tenant=self.tenant, appointment=self.appointment, patient=self.patient,
                                   receipt_number="R-DESK", amount=Decimal("300"), branch=self.branch)
        self.settle(reference)
        online = [p for p in self.payments() if p.receipt_number == reference]
        self.assertEqual(len(online), 1)
        self.assertIn("رد الفرق", online[0].notes)


class NotPaidUntilRecordedTests(OnlineShiftBase):
    def test_if_recording_fails_nothing_is_kept_and_the_patient_is_not_shown_as_paid(self):
        reference = self.start()
        with mock.patch("billing.shifts.online_shift", side_effect=RuntimeError("database hiccup")):
            response = self.settle(reference)
        self.assertEqual(response.status_code, 503)  # the gateway will call again
        self.assertEqual(ClinicCheckout.objects.get(reference=reference).status, "pending")
        self.assertEqual(self.payments(), [])
        self.assertEqual(self.online_shifts(), [])  # not even an empty shift is left behind
        row = self.client.get(self.url("appointments")).json()[0]
        self.assertEqual((row["due"], row["payment_status"], row["paid"]), ("300.00", "unpaid", "0.00"))

    def test_the_gateways_next_callback_records_it_once(self):
        reference = self.start()
        with mock.patch("billing.shifts.online_shift", side_effect=RuntimeError("down")):
            self.assertEqual(self.settle(reference).status_code, 503)
        self.assertEqual(self.settle(reference).status_code, 200)
        self.assertEqual(self.settle(reference).status_code, 200)  # repeated: still one payment
        self.assertEqual(len(self.payments()), 1)
        row = self.client.get(self.url("appointments")).json()[0]
        self.assertEqual((row["due"], row["payment_status"]), ("0.00", "paid"))

    def test_a_booking_with_no_clinic_cannot_be_recorded_and_so_is_not_confirmed(self):
        with tenant_context(self.tenant):
            Patient.all_objects.filter(pk=self.patient.pk).update(branch=None)
            Appointment.all_objects.filter(pk=self.appointment.pk).update(branch=None)
        reference = self.start()
        with tenant_context(self.tenant):
            ClinicCheckout.objects.filter(reference=reference).update(branch_id=None)
        self.assertEqual(self.settle(reference).status_code, 503)
        self.assertEqual(ClinicCheckout.objects.get(reference=reference).status, "pending")
        self.assertEqual(self.payments(), [])

    def test_the_browser_returning_before_it_is_recorded_is_told_it_is_pending(self):
        reference = self.start()
        with mock.patch("platform_admin.clinic_pay.confirm", side_effect=RuntimeError("down")):
            response = Client().get(reverse("api:gateway-callback", args=["paymob"]), {"merchant_order_id": reference})
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"/app/portal/{self.tenant.slug}/?payment=pending", response["Location"])

    def test_a_forged_confirmation_records_nothing_and_opens_no_shift(self):
        reference = self.start()
        response = self.settle(reference, cents=100)  # the amount does not match
        self.assertEqual(response.status_code, 400)
        self.assertEqual((self.payments(), self.online_shifts()), ([], []))

    def test_a_test_environment_payment_never_reaches_a_shift(self):
        ClinicCheckout.objects.all().delete()
        from platform_admin.models import IntegrationCredential

        IntegrationCredential.objects.all().delete()
        credential(Kind.PAYMOB, Scope.GROUP, PAYMOB, customer=self.tenant, mode="test")
        self.settle(self.start())
        self.assertEqual((self.payments(), self.online_shifts()), ([], []))


class ManagementOfTheOnlineShiftTests(OnlineShiftBase):
    def setUp(self):
        super().setUp()
        self.settle(self.start())
        (self.shift,) = self.online_shifts()

    def test_management_of_that_clinic_sees_it_labelled_and_with_its_payments(self):
        for username in ("admin-a", "owner"):
            with self.subTest(username=username):
                client = self.staff(username)
                rows = client.get(reverse("api:shift-list"), {"kind": "online"}).json()["results"]
                self.assertEqual([(r["kind"], r["user_name"]) for r in rows], [("online", "الدفع الإلكتروني")])
                detail = client.get(reverse("api:shift-detail", args=[self.shift.uuid])).json()
                self.assertEqual(detail["summary"]["revenue"], "300.00")
                self.assertEqual([p["amount"] for p in detail["payments"]], ["300.00"])
                self.assertEqual(detail["payments"][0]["shift_user_name"], "الدفع الإلكتروني")
                self.assertEqual([b["patient_name"] for b in detail["bookings"]], ["Mona"])

    def test_the_other_clinics_admin_and_the_reception_do_not_see_it(self):
        for username in ("admin-b", "rec"):
            with self.subTest(username=username):
                client = self.staff(username)
                self.assertEqual(client.get(reverse("api:shift-list")).json()["results"], [])
                self.assertEqual(client.get(reverse("api:shift-detail", args=[self.shift.uuid])).status_code, 404)

    def test_management_closes_it_and_reception_cannot(self):
        client = self.staff("admin-a")
        closed = client.post(reverse("api:shift-close", args=[self.shift.uuid]), {}, content_type="application/json")
        self.assertEqual(closed.status_code, 200, closed.content)
        self.assertEqual(closed.json()["status"], "closed")
        self.assertEqual(closed.json()["closing_summary"]["revenue"], "300.00")
        rec = self.staff("rec")
        self.assertIn(rec.post(reverse("api:shift-close", args=[self.shift.uuid]), {},
                               content_type="application/json").status_code, (400, 403, 404))

    def test_it_prints_like_any_shift_and_names_the_online_shift_as_its_cashier(self):
        client = self.staff("admin-a")
        response = client.get(reverse("billing:shift_print", args=[self.shift.uuid]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("الدفع الإلكتروني", response.content.decode())

    def test_the_payments_list_says_which_shift_the_online_money_sits_in(self):
        client = self.staff("owner")
        rows = client.get(reverse("api:payment-list")).json()["results"]
        self.assertEqual([(r["method_name"], r["shift_user_name"], r["shift_status"]) for r in rows],
                         [("دفع إلكتروني", "الدفع الإلكتروني", "open")])

    def test_cashier_shifts_are_unchanged_and_never_take_the_online_shift(self):
        rec = User.objects.get(username="rec")
        with tenant_context(self.tenant):
            mine = shifts.open_shift(rec)
            self.assertEqual(shifts.shift_for_recording(rec), mine)
            self.assertNotEqual(mine.pk, self.shift.pk)
        self.assertEqual(mine.kind, "cashier")
        # Opening the cashier's shift did not close, or move payments out of, the online one.
        self.shift.refresh_from_db()
        self.assertEqual(self.shift.status, "open")
