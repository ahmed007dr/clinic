"""The clinic's side of a service order (docs/16, Phase C).

The customer's order is approved (or refused) by the **Admin of the chosen
clinic**, customer service — the clinic's reception — phones the customer, and
then the doctor and time are settled, which makes real bookings. Every step tells
the customer by e-mail; a clinic sees and decides only its own orders.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from appointments.models import Appointment
from employees.models import Employee
from portal.models import ServiceOrder
from tenants.context import tenant_context

from .test_orders import OrderBase

User = get_user_model()


class HandlingBase(OrderBase):
    def setUp(self):
        super().setUp()
        with tenant_context(self.a):
            owner_role = ClinicRole.all_objects.get_or_create(tenant=self.a, name="Owner")[0]
            admin_role = ClinicRole.all_objects.get(tenant=self.a, name="Admin")
        User.objects.create_user(username="owner", email="owner@t.local", password="pass12345",
                                 tenant=self.a, role=owner_role, branch=self.branch)
        User.objects.create_user(username="adm-second", email="adm-second@t.local", password="pass12345",
                                 tenant=self.a, role=admin_role, branch=self.second)
        self.clients = {}

    def as_(self, username):
        client = self.clients.get(username)
        if client is None:
            client = self.clients[username] = Client()
            self.assertTrue(client.login(email=f"{username}@t.local", password="pass12345"), username)
        return client

    def order(self, *items):
        """An order the customer sent, as the clinic sees it."""
        (body,) = self.send(*(items or (self.item(),))).json()
        return body

    def url_of(self, name, order, **kw):
        return reverse(f"api:service-order-{name}", args=[order["uuid"]])

    def act(self, who, name, order, body=None):
        return self.do(lambda: self.as_(who).post(self.url_of(name, order), body or {}, content_type="application/json"))

    def status_of(self, order):
        with tenant_context(self.a):
            return ServiceOrder.objects.get(uuid=order["uuid"]).status

    def detail(self, who, order):
        return self.as_(who).get(self.url_of("detail", order))

    def when(self, days=2, hour=10):
        return (timezone.now() + timedelta(days=days)).strftime(f"%Y-%m-%d {hour:02d}:00")

    def schedule_body(self, order_detail, doctor=None, when=None):
        return {"lines": [
            {"line": line["uuid"], "doctor": str((doctor or self.dr_main).uuid), "scheduled_date": when or self.when()}
            for line in order_detail["lines"]
        ]}


class WhoSeesWhatTests(HandlingBase):
    def test_a_clinic_sees_its_own_orders_and_the_owner_sees_all(self):
        with tenant_context(self.a):
            type(self.a).objects.filter(pk=self.a.pk).update(portal_allow_other_branches=True)
        from services.models import BranchService

        with tenant_context(self.a):
            BranchService.all_objects.get_or_create(tenant=self.a, branch=self.second, service=self.service)
        self.send(self.item(), self.item(branch=self.second))
        url = reverse("api:service-orders")
        seen = lambda who: sorted(o["branch_name"] for o in self.as_(who).get(url).json()["results"])
        self.assertEqual(seen("rec"), ["Main"])
        self.assertEqual(seen("adm"), ["Main"])
        self.assertEqual(seen("rec-second"), ["Second"])
        self.assertEqual(seen("owner"), ["Main", "Second"])

    def test_a_doctor_and_the_public_have_no_access(self):
        order = self.order()
        self.assertEqual(self.as_("doc").get(reverse("api:service-orders")).status_code, 403)
        self.assertEqual(self.as_("doc").get(self.url_of("detail", order)).status_code, 403)
        self.assertIn(Client().get(reverse("api:service-orders")).status_code, (401, 403))

    def test_another_clinics_order_is_a_404_not_a_403(self):
        order = self.order()
        for who in ("rec-second", "adm-second"):
            self.assertEqual(self.detail(who, order).status_code, 404, who)
        self.assertEqual(self.act("adm-second", "approve", order).status_code, 404)
        self.assertEqual(self.act("rec-second", "approve", order).status_code, 403)  # not theirs to approve at all

    def test_the_list_says_who_and_what_and_counts_what_waits(self):
        self.order(self.item(self.pulses, quantity="100"))
        body = self.as_("rec").get(reverse("api:service-orders")).json()
        self.assertEqual(body["counts"], {"to_approve": 1, "to_call": 0})
        (row,) = body["results"]
        self.assertEqual((row["patient_name"], row["status"], row["branch_name"]), ("Alice", "submitted", "Main"))
        self.assertEqual(row["lines"][0]["quantity"], "100.00")
        filtered = self.as_("rec").get(reverse("api:service-orders"), {"status": "approved"}).json()
        self.assertEqual(filtered["results"], [])


class ApprovalTests(HandlingBase):
    def test_only_the_admin_approves_reception_cannot(self):
        order = self.order()
        self.assertEqual(self.act("rec", "approve", order).status_code, 403)
        self.assertEqual(self.status_of(order), "submitted")
        response = self.act("adm", "approve", order)
        self.assertEqual((response.status_code, response.json()["status"]), (200, "approved"))
        self.assertEqual(response.json()["reviewed_by"], "adm")
        self.assertEqual(self.act("owner", "approve", self.order()).status_code, 200)

    def test_approving_tells_the_customer_and_customer_service_to_call(self):
        order = self.order()
        mail.outbox.clear()
        self.act("adm", "approve", order)
        (message,) = self.mails()
        self.assertIn("وافقت العيادة", message.subject)
        self.assertIn(order["serial_number"], message.body)
        self.assertEqual(len(self.logged("order_approved")), 1)
        titles = [n.title for n in self.notices("rec")]
        self.assertIn("طلب بانتظار اتصال خدمة العملاء", titles)

    def test_an_order_is_approved_once(self):
        order = self.order()
        self.act("adm", "approve", order)
        self.assertEqual(self.act("adm", "approve", order).status_code, 400)

    def test_refusing_needs_a_reason_and_the_customer_is_told_it(self):
        order = self.order()
        self.assertEqual(self.act("rec", "reject", order, {"note": "x"}).status_code, 403)
        self.assertEqual(self.act("adm", "reject", order, {"note": "  "}).status_code, 400)
        mail.outbox.clear()
        response = self.act("adm", "reject", order, {"note": "الجهاز في الصيانة"})
        self.assertEqual((response.status_code, response.json()["status"]), (200, "rejected"))
        (message,) = self.mails()
        self.assertIn("الجهاز في الصيانة", message.body)
        # The customer sees the reason in «طلباتي».
        (mine,) = self.client.get(self.url("orders")).json()
        self.assertEqual((mine["status"], mine["review_note"]), ("rejected", "الجهاز في الصيانة"))
        self.assertEqual(self.act("adm", "approve", order).status_code, 400)  # a refused order stays refused


class CustomerServiceTests(HandlingBase):
    def test_the_call_is_recorded_only_after_approval(self):
        order = self.order()
        self.assertEqual(self.act("rec", "contacted", order, {"note": "x"}).status_code, 400)
        self.act("adm", "approve", order)
        response = self.act("rec", "contacted", order, {"note": "اتفقنا على السبت"})
        self.assertEqual((response.status_code, response.json()["status"]), (200, "contacted"))
        self.assertEqual((response.json()["contacted_by"], response.json()["contact_note"]), ("rec", "اتفقنا على السبت"))
        self.assertEqual(self.act("rec", "contacted", order).status_code, 400)

    def test_the_other_clinics_desk_cannot_record_it(self):
        order = self.order()
        self.act("adm", "approve", order)
        self.assertEqual(self.act("rec-second", "contacted", order).status_code, 404)


class SchedulingTests(HandlingBase):
    def approved(self, *items):
        order = self.order(*items)
        self.act("adm", "approve", order)
        return order

    def test_the_candidates_are_the_clinics_own_contracted_doctors_with_their_prices(self):
        order = self.approved()
        (line,) = self.detail("rec", order).json()["lines"]
        self.assertEqual(line["candidates"], [{"uuid": str(self.dr_main.uuid), "name": "Dr Main", "price": "150.00"}])

    def test_settling_it_makes_real_bookings_and_tells_the_customer(self):
        order = self.approved(self.item(), self.item(self.pulses, quantity="100"))
        detail = self.detail("rec", order).json()
        mail.outbox.clear()
        response = self.act("rec", "schedule", order, self.schedule_body(detail))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], "scheduled")
        with tenant_context(self.a):
            bookings = list(Appointment.objects.order_by("id"))
        self.assertEqual(len(bookings), 2)
        laser, pulses = bookings
        self.assertEqual((laser.status, laser.source, laser.doctor.name, laser.price), ("waiting", "portal", "Dr Main", Decimal("150.00")))
        self.assertEqual((pulses.quantity, pulses.unit_price, pulses.price, pulses.quantity_is_estimate),
                         (Decimal("100.00"), Decimal("2.00"), Decimal("200.00"), False))
        self.assertEqual(laser.created_by.username, "rec")
        # The customer's e-mail lists the bookings; «طلباتي» shows them.
        (message,) = self.mails()
        self.assertIn("تم تحديد موعدك", message.subject)
        self.assertIn("Dr Main", message.body)
        (mine,) = self.client.get(self.url("orders")).json()
        self.assertEqual((mine["status"], len(mine["appointments"])), ("scheduled", 2))
        self.assertEqual(len(self.client.get(self.url("appointments")).json()), 2)

    def test_a_service_the_doctor_sizes_stays_an_estimate_on_the_booking(self):
        order = self.approved(self.item(self.filler))
        self.act("rec", "schedule", order, self.schedule_body(self.detail("rec", order).json()))
        with tenant_context(self.a):
            (booking,) = Appointment.objects.all()
        self.assertEqual((booking.quantity, booking.quantity_is_estimate, booking.price), (Decimal("1.00"), True, Decimal("1200.00")))

    def test_nothing_is_booked_before_approval_and_never_twice(self):
        order = self.order()
        detail = self.detail("rec", order).json()
        self.assertEqual(self.act("rec", "schedule", order, self.schedule_body(detail)).status_code, 400)
        self.act("adm", "approve", order)
        self.assertEqual(self.act("rec", "schedule", order, self.schedule_body(detail)).status_code, 200)
        self.assertEqual(self.act("rec", "schedule", order, self.schedule_body(detail)).status_code, 400)
        with tenant_context(self.a):
            self.assertEqual(Appointment.objects.count(), 1)

    def test_every_service_needs_a_doctor_and_a_time_and_a_bad_line_books_nothing(self):
        order = self.approved(self.item(), self.item(self.pulses, quantity="100"))
        detail = self.detail("rec", order).json()
        good = self.schedule_body(detail)
        cases = {
            "a missing line": {"lines": good["lines"][:1]},
            "no lines": {},
            "a doctor of another clinic": {"lines": [good["lines"][0], {**good["lines"][1], "doctor": str(self.dr_second.uuid)}]},
            "no doctor": {"lines": [good["lines"][0], {**good["lines"][1], "doctor": ""}]},
            "a time in the past": {"lines": [good["lines"][0], {**good["lines"][1], "scheduled_date": self.when(days=-3)}]},
            "no time": {"lines": [good["lines"][0], {**good["lines"][1], "scheduled_date": "soon"}]},
        }
        for name, body in cases.items():
            with self.subTest(name):
                self.assertEqual(self.act("rec", "schedule", order, body).status_code, 400)
        with tenant_context(self.a):
            self.assertEqual(Appointment.objects.count(), 0)
        self.assertEqual(self.status_of(order), "approved")

    def test_a_doctor_with_a_stopped_login_is_not_offered(self):
        doctor_role = ClinicRole.all_objects.get(tenant=self.a, name="Doctor")
        User.objects.create_user(username="dr-main", email="dr-main@t.local", password="pass12345", tenant=self.a,
                                 role=doctor_role, branch=self.branch, employee=self.dr_main, is_active=False)
        order = self.approved()
        (line,) = self.detail("rec", order).json()["lines"]
        self.assertEqual(line["candidates"], [])

    def test_another_clinics_desk_cannot_schedule_it(self):
        order = self.approved()
        detail = self.detail("rec", order).json()
        self.assertEqual(self.act("rec-second", "schedule", order, self.schedule_body(detail)).status_code, 404)


class WholeJourneyTests(HandlingBase):
    def test_send_approve_call_schedule_and_the_customer_sees_each_step(self):
        (order,) = self.send(self.item()).json()
        seen = lambda: self.client.get(self.url("orders")).json()[0]["status"]
        self.assertEqual(seen(), "submitted")
        self.act("adm", "approve", order)
        self.assertEqual(seen(), "approved")
        self.act("rec", "contacted", order, {"note": "ok"})
        self.assertEqual(seen(), "contacted")
        self.act("rec", "schedule", order, self.schedule_body(self.detail("rec", order).json()))
        self.assertEqual(seen(), "scheduled")
        subjects = [m.subject for m in self.mails()]
        self.assertEqual(len(subjects), 3)  # received, approved, scheduled
