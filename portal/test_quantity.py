"""Things sold by quantity, on the website (the group owner's request, 2026-09-19).

A service the Owner or an Admin marked as sold by quantity shows its price per
unit in the public catalogue; booking it needs a quantity within the clinic's
limits, and the total is unit price × quantity — worked out by the server.
"""

from decimal import Decimal

from billing.models import DoctorServiceRate
from services.models import BranchService, Service
from tenants.context import tenant_context

from .test_booking import BookingBase


class QuantityBookingBase(BookingBase):
    def setUp(self):
        super().setUp()
        with tenant_context(self.a):
            self.pulses = Service.all_objects.create(
                tenant=self.a, name="Laser pulses", base_price=Decimal("3"), duration_minutes=45,
                requires_quantity=True, quantity_unit="نبضة", min_quantity=Decimal("10"), max_quantity=Decimal("500"),
            )
            DoctorServiceRate.all_objects.create(tenant=self.a, doctor=self.dr_main, service=self.pulses, price=Decimal("2"))
            BranchService.all_objects.create(tenant=self.a, branch=self.branch, service=self.pulses)

    def order(self, **overrides):
        return self.book(service=str(self.pulses.uuid), quantity="200", **overrides)


class CatalogueTests(QuantityBookingBase):
    def test_the_catalogue_says_which_services_are_sold_by_quantity_and_the_price_is_per_unit(self):
        self.client.logout()
        rows = {r["name"]: r for r in self.client.get(self.url("catalog-services")).json()}
        pulses, plain = rows["Laser pulses"], rows["Laser"]
        self.assertEqual((pulses["requires_quantity"], pulses["quantity_unit"], pulses["min_quantity"],
                          pulses["max_quantity"], pulses["from_price"]), (True, "نبضة", "10.00", "500.00", "2.00"))
        self.assertFalse(plain["requires_quantity"])
        detail = self.client.get(self.url("catalog-branches", service=self.pulses.uuid)).json()["service"]
        self.assertEqual((detail["requires_quantity"], detail["quantity_unit"]), (True, "نبضة"))
        doctors = self.client.get(self.url("catalog-doctors", service=self.pulses.uuid, branch=self.branch.uuid)).json()
        self.assertEqual(doctors["service"]["requires_quantity"], True)
        self.assertEqual([d["price"] for d in doctors["doctors"]], ["2.00"])


class BookingTests(QuantityBookingBase):
    def test_the_total_is_worked_out_by_the_server_and_kept_with_the_unit_price(self):
        response = self.order()
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual((body["quantity"], body["unit_price"], body["price"], body["quantity_unit"]),
                         ("200.00", "2.00", "400.00", "نبضة"))
        (appointment,) = self.appointments(patient=self.alice)
        self.assertEqual((appointment.quantity, appointment.unit_price, appointment.price),
                         (Decimal("200.00"), Decimal("2.00"), Decimal("400.00")))

    def test_a_quantity_is_required_and_kept_within_the_limits(self):
        for quantity, ok in (("", False), ("abc", False), ("9.99", False), ("501", False), ("10", True), ("500", True)):
            with self.subTest(quantity=quantity):
                response = self.book(service=str(self.pulses.uuid), quantity=quantity, slot=self.slot(
                    "09:00" if quantity in ("10",) else "09:45" if quantity == "500" else "09:00"))
                self.assertEqual(response.status_code, 201 if ok else 400, response.content)
                if not ok:
                    self.assertIn("quantity", response.json())
        self.assertEqual({a.quantity for a in self.appointments(patient=self.alice)}, {Decimal("10.00"), Decimal("500.00")})

    def test_a_missing_quantity_names_the_unit(self):
        message = self.book(service=str(self.pulses.uuid)).json()["quantity"][0]
        self.assertIn("نبضة", message)

    def test_a_service_not_sold_by_quantity_ignores_a_quantity_that_is_sent(self):
        response = self.book(quantity="5")
        self.assertEqual(response.status_code, 201, response.content)
        (appointment,) = self.appointments(patient=self.alice)
        self.assertEqual((appointment.quantity, appointment.unit_price, appointment.price),
                         (None, None, Decimal("150.00")))

    def test_the_patient_cannot_set_the_price(self):
        response = self.order(price="1", unit_price="0.01", total="1")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["price"], "400.00")

    def test_the_older_free_time_request_refuses_a_service_sold_by_quantity(self):
        from datetime import timedelta

        from django.utils import timezone

        when = (timezone.now() + timedelta(days=3)).replace(microsecond=0).isoformat()
        # Its doctor list is the patient's own clinic's: Dr Main, under contract for the service.
        response = self.client.post(
            self.url("appointments"),
            {"scheduled_date": when, "doctor": str(self.dr_main.uuid), "service": str(self.pulses.uuid)},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("service", response.json())


class DoctorSizedTests(QuantityBookingBase):
    """A service whose quantity the doctor sets in the room: the website books an estimate."""

    def setUp(self):
        super().setUp()
        Service.all_objects.filter(pk=self.pulses.pk).update(doctor_sets_quantity=True)

    def test_the_catalogue_says_the_doctor_sets_it(self):
        self.client.logout()
        rows = {r["name"]: r for r in self.client.get(self.url("catalog-services")).json()}
        self.assertTrue(rows["Laser pulses"]["doctor_sets_quantity"])
        self.assertFalse(rows["Laser"]["doctor_sets_quantity"])

    def test_no_quantity_books_the_smallest_as_an_estimate(self):
        response = self.book(service=str(self.pulses.uuid))
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual((body["quantity"], body["price"], body["quantity_is_estimate"]), ("10.00", "20.00", True))

    def test_a_quantity_asked_for_is_still_an_estimate(self):
        body = self.order().json()
        self.assertEqual((body["quantity"], body["price"], body["quantity_is_estimate"]), ("200.00", "400.00", True))

    def test_the_limits_still_hold_for_an_estimate_that_is_given(self):
        self.assertEqual(self.book(service=str(self.pulses.uuid), quantity="5").status_code, 400)

    def test_a_service_sold_by_quantity_that_the_doctor_does_not_size_still_needs_one(self):
        Service.all_objects.filter(pk=self.pulses.pk).update(doctor_sets_quantity=False)
        self.assertEqual(self.book(service=str(self.pulses.uuid)).status_code, 400)
