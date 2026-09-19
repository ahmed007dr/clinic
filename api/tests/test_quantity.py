"""Things sold by quantity (the group owner's request, 2026-09-19).

The Owner or an Admin decides, per service, whether it is sold by quantity —
pulses, millilitres, units. Where it is, the price on the service is a price per
unit and a booking asks how many: the total is unit price × quantity. A service
that is not sold that way is priced as one thing, exactly as before.
"""

from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from api.tests.test_catalogue import CatalogueBase
from billing.models import DiscountCoupon, DoctorServiceRate
from patients.models import Patient
from services.models import Service


class QuantityBase(CatalogueBase):
    def setUp(self):
        super().setUp()
        self.patient = Patient.all_objects.create(tenant=self.tenant, name="Pat", branch=self.a)
        # Laser priced per pulse: 2 EGP a pulse, between 10 and 500 pulses.
        self.pulses = Service.all_objects.create(
            tenant=self.tenant, name="Laser pulses", base_price=Decimal("3"), requires_quantity=True,
            quantity_unit="نبضة", min_quantity=Decimal("10"), max_quantity=Decimal("500"),
        )
        DoctorServiceRate.all_objects.create(
            tenant=self.tenant, doctor=self.ahmed, service=self.pulses, price=Decimal("2"),
        )

    def body(self, **overrides):
        body = {
            "patient": str(self.patient.uuid), "doctor": str(self.ahmed.uuid), "service": str(self.pulses.uuid),
            "branch": str(self.a.uuid), "quantity": "200",
            "scheduled_date": (timezone.now() + timedelta(days=2)).strftime("%Y-%m-%d %H:%M"),
        }
        body.update({k: v for k, v in overrides.items() if v is not None})
        for key in [k for k, v in overrides.items() if v is None]:
            body.pop(key, None)
        return body

    def book(self, user="rec", **overrides):
        self.login(user)
        return self.client.post(reverse("api:appointment-list"), self.body(**overrides), content_type="application/json")

    def patch(self, uuid, **body):
        return self.client.patch(reverse("api:appointment-detail", args=[uuid]), body, content_type="application/json")


class ServiceSettingsTests(QuantityBase):
    def test_a_service_is_not_sold_by_quantity_unless_management_says_so(self):
        self.assertFalse(self.laser.requires_quantity)
        self.login("owner")
        rows = {r["name"]: r for r in self.client.get(reverse("api:service-list")).json()["results"]}
        self.assertFalse(rows["Laser Hair Removal"]["requires_quantity"])
        self.assertEqual(rows["Laser pulses"]["quantity_unit"], "نبضة")

    def test_the_owner_and_an_admin_set_it_and_reception_cannot(self):
        url = reverse("api:service-detail", args=[self.laser.uuid])
        patch = {"requires_quantity": True, "quantity_unit": "مل", "min_quantity": "1", "max_quantity": "20"}
        for who, expected in (("owner", 200), ("admin-a", 200), ("rec", 403)):
            self.login(who)
            response = self.client.patch(url, patch, content_type="application/json")
            self.assertEqual(response.status_code, expected, who)
        self.laser.refresh_from_db()
        self.assertTrue(self.laser.requires_quantity)
        self.assertEqual((self.laser.quantity_unit, self.laser.max_quantity), ("مل", Decimal("20.00")))

    def test_the_limits_must_make_sense(self):
        self.login("owner")
        url = reverse("api:service-detail", args=[self.laser.uuid])
        for bad in ({"requires_quantity": True, "min_quantity": "0"},
                    {"requires_quantity": True, "min_quantity": "10", "max_quantity": "5"}):
            with self.subTest(bad=bad):
                self.assertEqual(self.client.patch(url, bad, content_type="application/json").status_code, 400)

    def test_the_booking_form_is_told_which_services_take_a_quantity(self):
        self.login("rec")
        offers = self.client.get(reverse("api:doctor-offerings"), {"doctor": str(self.ahmed.uuid)}).json()["services"]
        by_name = {o["name"]: o for o in offers}
        self.assertEqual(
            (by_name["Laser pulses"]["price"], by_name["Laser pulses"]["requires_quantity"],
             by_name["Laser pulses"]["quantity_unit"], by_name["Laser pulses"]["min_quantity"],
             by_name["Laser pulses"]["max_quantity"]),
            ("2.00", True, "نبضة", "10.00", "500.00"),
        )
        self.assertFalse(by_name["Laser Hair Removal"]["requires_quantity"])


class PricingTests(QuantityBase):
    def test_the_total_is_the_unit_price_times_the_quantity(self):
        response = self.book()
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual((body["quantity"], body["unit_price"], body["price"], body["quantity_unit"]),
                         ("200.00", "2.00", "400.00", "نبضة"))
        self.assertEqual(body["net_price"], "400.00")

    def test_a_quantity_is_required_and_kept_within_the_limits(self):
        for quantity, ok in ((None, False), ("9", False), ("501", False), ("10", True), ("500", True)):
            with self.subTest(quantity=quantity):
                response = self.book(quantity=quantity)
                self.assertEqual(response.status_code, 201 if ok else 400, response.content)
                if not ok:
                    self.assertIn("quantity", response.json())

    def test_reception_cannot_type_a_price_it_is_always_the_contracts_times_the_quantity(self):
        response = self.book(price="1")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["price"], "400.00")

    def test_management_may_type_another_price_and_gets_the_computed_one_otherwise(self):
        typed = self.book(user="admin-a", price="350")
        self.assertEqual((typed.status_code, typed.json()["price"]), (201, "350.00"))
        computed = self.book(user="admin-a")
        self.assertEqual(computed.json()["price"], "400.00")

    def test_a_service_not_sold_by_quantity_keeps_its_price_and_ignores_a_quantity(self):
        response = self.book(service=str(self.laser.uuid), quantity="5")
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual((body["quantity"], body["unit_price"], body["price"]), (None, None, "500.00"))

    def test_changing_the_quantity_reprices_and_changing_nothing_keeps_the_figures(self):
        uuid = self.book().json()["uuid"]
        again = self.patch(uuid, quantity="300")
        self.assertEqual((again.status_code, again.json()["price"]), (200, "600.00"))
        # The contract moves on; an edit that touches neither doctor, service nor quantity does not reprice.
        DoctorServiceRate.all_objects.filter(doctor=self.ahmed, service=self.pulses).update(price=Decimal("9"))
        untouched = self.patch(uuid, notes="called")
        self.assertEqual((untouched.json()["price"], untouched.json()["unit_price"]), ("600.00", "2.00"))

    def test_switching_the_service_to_one_without_quantity_drops_it(self):
        uuid = self.book().json()["uuid"]
        response = self.patch(uuid, service=str(self.laser.uuid))
        body = response.json()
        self.assertEqual((response.status_code, body["quantity"], body["unit_price"], body["price"]),
                         (200, None, None, "500.00"))

    def test_a_coupon_discounts_the_total_and_what_is_owed_follows_it(self):
        with_coupon = DiscountCoupon.all_objects.create(
            tenant=self.tenant, patient=self.patient, amount=Decimal("100"), service=self.pulses,
        )
        response = self.book(coupon=str(with_coupon.uuid))
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual((body["price"], body["discount"], body["net_price"], body["amount_due"]),
                         ("400.00", "100.00", "300.00", "300.00"))

    def test_a_price_per_unit_of_nothing_is_not_a_quantity_service(self):
        # Turning the setting off makes the service an ordinary one again.
        Service.all_objects.filter(pk=self.pulses.pk).update(requires_quantity=False)
        response = self.book(quantity=None)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["price"], "2.00")
