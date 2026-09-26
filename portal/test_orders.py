"""«طلباتي» — the customer's service orders (docs/16, Phase B).

A basket of services becomes one order per clinic, holding no doctor's time.
The server re-decides everything the page showed: each service must still be
orderable at that clinic, the quantity inside the service's limits, the price is
worked out here. The customer is e-mailed a summary and the clinic's desk is told.
"""

from decimal import Decimal

from django.core import mail
from django.test import Client

from billing.models import DoctorServiceRate
from employees.models import Employee, EmployeeType
from portal.models import ServiceOrder
from services.models import BranchService, Service
from tenants.context import tenant_context

from .test_notifications import NotifyBase


class OrderBase(NotifyBase):
    def setUp(self):
        super().setUp()
        with tenant_context(self.a):
            # Pulses: 2 EGP a pulse from Dr Main, between 50 and 800 pulses.
            self.pulses = Service.all_objects.create(
                tenant=self.a, name="Pulses", base_price=Decimal("3"), requires_quantity=True,
                quantity_unit="نبضة", min_quantity=Decimal("50"), max_quantity=Decimal("800"),
            )
            # Filler: by the ml, and the doctor decides how many in the room.
            self.filler = Service.all_objects.create(
                tenant=self.a, name="Filler", base_price=Decimal("1000"), requires_quantity=True,
                doctor_sets_quantity=True, quantity_unit="مل", min_quantity=Decimal("1"), max_quantity=Decimal("10"),
            )
            # Priced after the doctor has seen the patient.
            self.consult = Service.all_objects.create(
                tenant=self.a, name="Consult", base_price=Decimal("500"),
                price_display=Service.PriceDisplay.AFTER_EVALUATION,
            )
            for service, price in ((self.pulses, "2"), (self.filler, "1200"), (self.consult, None)):
                DoctorServiceRate.all_objects.create(
                    tenant=self.a, doctor=self.dr_main, service=service, price=Decimal(price) if price else None)
                BranchService.all_objects.get_or_create(tenant=self.a, branch=self.branch, service=service)

    def item(self, service=None, branch=None, **extra):
        return {"service": str((service or self.service).uuid), "branch": str((branch or self.branch).uuid), **extra}

    def send(self, *items, client=None, **extra):
        return self.do(lambda: (client or self.client).post(
            self.url("orders"), {"items": list(items), **extra}, content_type="application/json"))

    def orders(self, **filters):
        with tenant_context(self.a):
            return list(ServiceOrder.objects.filter(**filters).prefetch_related("lines"))


class SendingTests(OrderBase):
    def test_a_basket_becomes_an_order_that_holds_no_time_and_waits_for_the_clinic(self):
        response = self.send(self.item(), notes="  after work  ", preferred_contact="مساءً")
        self.assertEqual(response.status_code, 201, response.content)
        (body,) = response.json()
        self.assertEqual((body["status"], body["is_open"], body["branch"]["name"]), ("submitted", True, "Main"))
        self.assertTrue(body["serial_number"].startswith("SO-"))
        (line,) = body["lines"]
        # One doctor at Main charges 150 and the service is a fixed one: the price is final.
        self.assertEqual((line["service_name"], line["unit_price"], line["price"], line["price_is_final"]),
                         ("Laser", "150.00", "150.00", True))
        (order,) = self.orders()
        self.assertEqual((order.patient, order.notes, order.preferred_contact), (self.alice, "after work", "مساءً"))
        # No booking, so no doctor time is held.
        from appointments.models import Appointment
        with tenant_context(self.a):
            self.assertFalse(Appointment.objects.exists())

    def test_two_clinics_make_two_orders_each_with_its_own_lines(self):
        with tenant_context(self.a):
            type(self.a).objects.filter(pk=self.a.pk).update(portal_allow_other_branches=True)
        response = self.send(self.item(), self.item(branch=self.second), self.item(self.pulses, quantity="100"))
        self.assertEqual(response.status_code, 201, response.content)
        by_branch = {o["branch"]["name"]: o for o in response.json()}
        self.assertEqual(set(by_branch), {"Main", "Second"})
        self.assertEqual([l["service_name"] for l in by_branch["Main"]["lines"]], ["Laser", "Pulses"])
        self.assertEqual(by_branch["Second"]["lines"][0]["price"], "250.00")
        self.assertEqual(by_branch["Main"]["total"], "350.00")  # 150 + 100 × 2
        self.assertEqual(len(self.orders()), 2)

    def test_the_price_is_worked_out_on_the_server(self):
        response = self.send(self.item(self.pulses, quantity="100", price="1"))  # a price sent is ignored
        (line,) = response.json()[0]["lines"]
        self.assertEqual((line["quantity"], line["unit_price"], line["price"], line["quantity_unit"]),
                         ("100.00", "2.00", "200.00", "نبضة"))

    def test_the_price_is_only_from_when_it_depends_on_who_treats_you(self):
        with tenant_context(self.a):
            doctor_type = EmployeeType.all_objects.get(tenant=self.a, name="Doctor")
            other = Employee.all_objects.create(
                tenant=self.a, name="Dr Other", branch=self.branch, employee_type=doctor_type,
                national_id="O1", salary_value=0, show_publicly=True)
            DoctorServiceRate.all_objects.create(tenant=self.a, doctor=other, service=self.service, price=Decimal("300"))
            from appointments.models import DoctorSchedule
            from datetime import time
            DoctorSchedule.all_objects.create(tenant=self.a, doctor=other, branch=self.branch, weekday=0,
                                              start_time=time(9), end_time=time(13))
        (line,) = self.send(self.item()).json()[0]["lines"]
        self.assertEqual((line["unit_price"], line["price_is_final"]), ("150.00", False))  # the lowest, not final

    def test_a_quantity_the_doctor_sets_may_be_left_out_and_is_only_an_estimate(self):
        body = self.send(self.item(self.filler)).json()[0]
        (line,) = body["lines"]
        self.assertEqual((line["quantity"], line["price"], line["price_is_final"]), ("1.00", "1200.00", False))
        self.assertTrue(body["total_is_estimate"])

    def test_a_service_priced_after_evaluation_has_no_figure(self):
        (line,) = self.send(self.item(self.consult)).json()[0]["lines"]
        self.assertEqual((line["unit_price"], line["price"], line["price_is_final"]), (None, "0.00", False))


class RefusalTests(OrderBase):
    def refused(self, *items, status=400, **extra):
        response = self.send(*items, **extra)
        self.assertEqual(response.status_code, status, response.content)
        self.assertEqual(self.orders(), [])
        return response.json()

    def test_an_empty_or_malformed_basket_is_refused(self):
        for items in ([], None, "x", [1], [{}]):
            with self.subTest(items=items):
                response = self.do(lambda: self.client.post(
                    self.url("orders"), {"items": items}, content_type="application/json"))
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.orders(), [])

    def test_only_what_the_catalogue_offers_at_that_clinic_can_be_ordered(self):
        self.refused(self.item(branch=self.second))  # the service is not offered... and is another clinic
        self.refused({"service": "00000000-0000-0000-0000-000000000000", "branch": str(self.branch.uuid)})
        BranchService.all_objects.filter(branch=self.branch, service=self.service).update(is_active=False)
        self.refused(self.item())
        BranchService.all_objects.filter(branch=self.branch, service=self.service).update(is_active=True)
        Service.all_objects.filter(pk=self.service.pk).update(is_active=False)
        self.refused(self.item())

    def test_a_quantity_outside_the_limits_is_refused(self):
        for quantity in ("10", "801", "", None, "abc"):
            with self.subTest(quantity=quantity):
                self.refused(self.item(self.pulses, quantity=quantity))

    def test_the_same_service_twice_at_one_clinic_is_refused(self):
        self.refused(self.item(), self.item())

    def test_more_than_ten_lines_are_refused(self):
        self.refused(*[self.item()] * 11)

    def test_a_customer_orders_at_their_own_clinic_unless_the_owner_allows_others(self):
        self.refused(self.item(branch=self.second), status=400)  # not offered there either — same refusal
        with tenant_context(self.a):
            BranchService.all_objects.get_or_create(tenant=self.a, branch=self.second, service=self.service)
        body = self.refused(self.item(branch=self.second))
        self.assertIn("عيادتك فقط", str(body))
        with tenant_context(self.a):
            type(self.a).objects.filter(pk=self.a.pk).update(portal_allow_other_branches=True)
        self.assertEqual(self.send(self.item(branch=self.second)).status_code, 201)

    def test_at_most_three_orders_are_open_at_once(self):
        with tenant_context(self.a):
            type(self.a).objects.filter(pk=self.a.pk).update(portal_allow_other_branches=True)
        for _ in range(3):
            self.assertEqual(self.send(self.item(self.pulses, quantity="100")).status_code, 201)
        self.assertEqual(self.send(self.item()).status_code, 400)
        # Withdrawing one makes room.
        first = self.orders()[0]
        self.client.post(self.url("order-cancel", uuid=first.uuid), content_type="application/json")
        self.assertEqual(self.send(self.item()).status_code, 201)

    def test_sending_needs_a_signed_in_customer(self):
        response = self.send(self.item(), client=Client())
        self.assertIn(response.status_code, (401, 403))
        self.assertEqual(self.orders(), [])


class MyOrdersTests(OrderBase):
    def test_a_customer_sees_only_their_own_orders(self):
        self.send(self.item())
        other = Client()
        self.enrol(self.bob, client=other)
        self.assertEqual(other.get(self.url("orders")).json(), [])
        (mine,) = self.client.get(self.url("orders")).json()
        self.assertEqual(other.get(self.url("order-detail", uuid=mine["uuid"])).status_code, 404)
        self.assertEqual(other.post(self.url("order-cancel", uuid=mine["uuid"]), content_type="application/json").status_code, 404)

    def test_another_group_cannot_read_it(self):
        self.send(self.item())
        (mine,) = self.client.get(self.url("orders")).json()
        other_group = Client()
        self.enrol(self.carol, tenant=self.b, client=other_group)
        self.assertEqual(other_group.get(self.url("order-detail", tenant=self.b, uuid=mine["uuid"])).status_code, 404)

    def test_the_customer_can_withdraw_an_open_order_but_not_a_finished_one(self):
        (mine,) = self.send(self.item()).json()
        withdrawn = self.do(lambda: self.client.post(self.url("order-cancel", uuid=mine["uuid"]), content_type="application/json"))
        self.assertEqual((withdrawn.status_code, withdrawn.json()["status"]), (200, "cancelled"))
        again = self.client.post(self.url("order-cancel", uuid=mine["uuid"]), content_type="application/json")
        self.assertEqual(again.status_code, 400)
        (done,) = self.send(self.item()).json()
        ServiceOrder.all_objects.filter(uuid=done["uuid"]).update(status="scheduled")
        self.assertEqual(self.client.post(self.url("order-cancel", uuid=done["uuid"]), content_type="application/json").status_code, 400)


class TellingPeopleTests(OrderBase):
    def test_the_customer_gets_one_email_with_every_order_and_the_desk_is_told(self):
        with tenant_context(self.a):
            type(self.a).objects.filter(pk=self.a.pk).update(portal_allow_other_branches=True)
            BranchService.all_objects.get_or_create(tenant=self.a, branch=self.second, service=self.service)
        mail.outbox.clear()
        self.send(self.item(), self.item(branch=self.second), self.item(self.pulses, quantity="100"))
        (message,) = self.mails()
        self.assertIn("استلمنا طلبك", message.subject)
        for text in ("Laser", "Pulses", "100 نبضة", "Main", "Second", "SO-", "موافقة العيادة"):
            self.assertIn(text, message.body)
        self.assertEqual(len(self.logged("order_received")), 1)
        # The desk of each clinic is told about its own order only.
        (notice,) = self.notices("rec")
        self.assertEqual(notice.title, "طلب خدمات جديد من الموقع")
        self.assertIn("Laser", notice.message)
        self.assertNotIn("Second", notice.message)
        (second,) = self.notices("rec-second")
        self.assertIn("Laser", second.message)

    def test_no_email_without_an_address_and_the_order_still_stands(self):
        with tenant_context(self.a):
            self.alice.email = ""
            self.alice.save()
        mail.outbox.clear()
        self.assertEqual(self.send(self.item()).status_code, 201)
        self.assertEqual(mail.outbox, [])
        self.assertEqual(len(self.orders()), 1)

    def test_a_dead_mail_server_never_stops_an_order(self):
        from unittest import mock

        with mock.patch("notifications.orders.deliver", side_effect=RuntimeError("smtp down")):
            self.assertEqual(self.send(self.item()).status_code, 201)
        self.assertEqual(len(self.orders()), 1)

    def test_withdrawing_tells_the_desk(self):
        (mine,) = self.send(self.item()).json()
        self.do(lambda: self.client.post(self.url("order-cancel", uuid=mine["uuid"]), content_type="application/json"))
        titles = [n.title for n in self.notices("rec")]
        self.assertIn("ألغى العميل طلبه", titles)


class PreferredTimeTests(OrderBase):
    """The customer picks a day and time when adding (docs/16, R2): a preference
    that holds nothing, drawn from what the doctors really offer."""

    def times(self, **params):
        return self.client.get(self.url("catalog-branch-times"), {
            "service": str(self.service.uuid), "branch": str(self.branch.uuid), "date": self.day.isoformat(), **params})

    def test_the_clinics_days_and_times_are_the_union_of_its_doctors(self):
        days = self.client.get(self.url("catalog-branch-days"), {
            "service": str(self.service.uuid), "branch": str(self.branch.uuid)}).json()["days"]
        self.assertIn(self.day.isoformat(), days)
        body = self.times().json()
        self.assertEqual(body["times"][0], {"time": "09:00", "doctors": [{"uuid": str(self.dr_main.uuid), "name": "Dr Main"}]})
        self.assertEqual(self.times(doctor=str(self.dr_main.uuid)).json()["times"][0]["time"], "09:00")
        self.assertEqual(self.times(doctor=str(self.dr_second.uuid)).status_code, 404)  # not this clinic's doctor

    def test_it_needs_no_login_and_a_bad_choice_is_a_404(self):
        self.assertEqual(Client().get(self.url("catalog-branch-days"), {
            "service": str(self.service.uuid), "branch": str(self.branch.uuid)}).status_code, 200)
        self.assertEqual(self.client.get(self.url("catalog-branch-days"), {"service": "x", "branch": "y"}).status_code, 404)
        self.assertEqual(self.client.get(self.url("catalog-branch-times"), {
            "service": str(self.service.uuid), "branch": str(self.branch.uuid), "date": "nope"}).status_code, 400)

    def test_an_offered_time_is_kept_as_a_preference_with_the_doctor_who_has_it(self):
        slot = f"{self.day.isoformat()} 09:45"
        (body,) = self.send(self.item(slot=slot)).json()
        (line,) = body["lines"]
        self.assertEqual((line["preferred_doctor"], line["preferred_at"]), ("Dr Main", f"{self.day.isoformat()}T09:45:00"))
        (order,) = self.orders()
        self.assertEqual(order.lines.get().preferred_doctor.name, "Dr Main")
        # It holds nothing: no booking, and another customer may prefer the same time.
        with tenant_context(self.a):
            from appointments.models import Appointment
            self.assertFalse(Appointment.objects.exists())
        other = Client()
        self.enrol(self.bob, client=other)
        self.assertEqual(self.send(self.item(slot=slot), client=other).status_code, 201)

    def test_a_named_doctor_prices_the_line_and_only_an_offered_time_is_accepted(self):
        (body,) = self.send(self.item(doctor=str(self.dr_main.uuid))).json()
        self.assertEqual((body["lines"][0]["preferred_doctor"], body["lines"][0]["preferred_at"]), ("Dr Main", None))
        for slot in (f"{self.day.isoformat()} 10:10", f"{self.day.isoformat()} 13:00", "2020-01-06 09:00", "garbage"):
            with self.subTest(slot=slot):
                response = self.send(self.item(slot=slot))
                self.assertIn(response.status_code, (400, 409), response.content)
        self.assertEqual(self.send(self.item(doctor=str(self.dr_second.uuid))).status_code, 400)  # not this clinic's

    def test_the_email_says_when_the_customer_would_like_it(self):
        mail.outbox.clear()
        self.send(self.item(slot=f"{self.day.isoformat()} 09:00"))
        (message,) = self.mails()
        self.assertIn(f"{self.day.isoformat()} 09:00", message.body)


class PaymentPreferenceTests(OrderBase):
    def test_the_customer_says_online_or_manual_and_manual_is_the_default(self):
        (default,) = self.send(self.item()).json()
        self.assertEqual((default["payment_preference"], default["payment_preference_label"]), ("manual", "يدوي: تحويل أو عند الوصول"))
        (online,) = self.send(self.item(self.pulses, quantity="100"), payment_preference="online").json()
        self.assertEqual(online["payment_preference"], "online")

    def test_anything_else_is_refused(self):
        response = self.send(self.item(), payment_preference="bitcoin")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.orders(), [])
