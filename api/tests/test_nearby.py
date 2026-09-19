"""The nearest clinic first (docs/16, Phase A).

The public page lists the clinics that offer a service. When the customer says
where they are — a point their browser gave, or a governorate they chose — the
nearest is first and marked. Nothing about where they are is stored or sent back.
"""

from decimal import Decimal

from django.urls import reverse

from api.tests.test_catalogue import CatalogueBase
from branches.models import Branch
from services.nearby import distance_km, normalize, parse_point

CAIRO = ("30.0444", "31.2357")
ALEXANDRIA = ("31.2001", "29.9187")


class NearbyBase(CatalogueBase):
    def setUp(self):
        super().setUp()
        Branch.all_objects.filter(pk=self.a.pk).update(governorate="القاهرة", latitude=Decimal(CAIRO[0]), longitude=Decimal(CAIRO[1]))
        Branch.all_objects.filter(pk=self.b.pk).update(governorate="الإسكندرية", latitude=Decimal(ALEXANDRIA[0]), longitude=Decimal(ALEXANDRIA[1]))

    def ask(self, **params):
        self.client.logout()
        response = self.client.get(self.url("catalog-branches", service=self.laser.uuid), params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def names(self, **params):
        return [b["name"] for b in self.ask(**params)["branches"]]


class OrderingTests(NearbyBase):
    def test_without_a_location_the_clinics_are_by_name_and_none_is_nearest(self):
        body = self.ask()
        self.assertEqual((body["sorted_by"], [b["name"] for b in body["branches"]]), ("name", ["Clinic A", "Clinic B"]))
        self.assertFalse(any(b["nearest"] for b in body["branches"]))
        self.assertTrue(all(b["distance_km"] is None for b in body["branches"]))

    def test_a_point_puts_the_nearest_first_with_the_distance(self):
        near_alex = self.ask(lat="31.1", lng="29.95")  # a little south-east of Alexandria
        self.assertEqual((near_alex["sorted_by"], [b["name"] for b in near_alex["branches"]]), ("distance", ["Clinic B", "Clinic A"]))
        first, second = near_alex["branches"]
        self.assertTrue(first["nearest"] and not second["nearest"])
        self.assertLess(first["distance_km"], 20)
        self.assertGreater(second["distance_km"], 150)  # Cairo is ~180 km away
        in_cairo = self.ask(lat="30.05", lng="31.24")
        self.assertEqual([b["name"] for b in in_cairo["branches"]], ["Clinic A", "Clinic B"])

    def test_a_clinic_with_no_coordinates_comes_after_the_ones_with_a_distance(self):
        Branch.all_objects.filter(pk=self.a.pk).update(latitude=None, longitude=None)
        body = self.ask(lat="30.05", lng="31.24")  # standing in Cairo, but Cairo's clinic has no point
        self.assertEqual([b["name"] for b in body["branches"]], ["Clinic B", "Clinic A"])
        self.assertIsNone(body["branches"][1]["distance_km"])

    def test_a_governorate_is_the_fallback_and_is_matched_loosely(self):
        for spelling in ("الإسكندرية", "الاسكندريه", "  الاسكندرية "):
            with self.subTest(spelling=spelling):
                body = self.ask(governorate=spelling)
                self.assertEqual((body["sorted_by"], body["branches"][0]["name"]), ("governorate", "Clinic B"))
                self.assertTrue(body["branches"][0]["nearest"] and body["branches"][0]["same_governorate"])

    def test_a_governorate_with_no_clinic_marks_nothing_nearest(self):
        body = self.ask(governorate="أسوان")
        self.assertEqual([b["name"] for b in body["branches"]], ["Clinic A", "Clinic B"])
        self.assertFalse(any(b["nearest"] for b in body["branches"]))

    def test_a_point_beats_a_governorate(self):
        body = self.ask(lat="31.1", lng="29.95", governorate="القاهرة")
        self.assertEqual((body["sorted_by"], body["branches"][0]["name"]), ("distance", "Clinic B"))

    def test_a_bad_point_is_ignored_not_an_error(self):
        for params in ({"lat": "abc", "lng": "1"}, {"lat": "95", "lng": "10"}, {"lat": "10"}, {"lat": "nan", "lng": "nan"}):
            with self.subTest(params=params):
                self.assertEqual(self.ask(**params)["sorted_by"], "name")

    def test_the_customers_location_is_never_echoed(self):
        text = self.client.get(self.url("catalog-branches", service=self.laser.uuid), {"lat": "31.1234", "lng": "29.9876"}).content.decode()
        self.assertNotIn("31.1234", text)
        self.assertNotIn("29.9876", text)

    def test_the_public_list_still_holds_only_clinics_that_offer_the_service(self):
        self.assertEqual(self.names(lat="30.0", lng="31.0"), ["Clinic A", "Clinic B"])  # C never appears


class RegionsTests(NearbyBase):
    def test_the_regions_are_the_governorates_of_clinics_with_something_to_book(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url("catalog-regions")).json(), ["الإسكندرية", "القاهرة"])
        # A clinic that offers nothing does not add its governorate.
        Branch.all_objects.filter(pk=self.c.pk).update(governorate="أسوان")
        self.assertEqual(self.client.get(self.url("catalog-regions")).json(), ["الإسكندرية", "القاهرة"])

    def test_the_same_governorate_spelled_twice_is_listed_once(self):
        Branch.all_objects.filter(pk=self.b.pk).update(governorate="القاهره")
        self.assertEqual(len(self.client.get(self.url("catalog-regions")).json()), 1)


class SettingTheLocationTests(NearbyBase):
    def url_for(self, branch):
        return reverse("api:about-detail", args=[branch.uuid])

    def patch(self, who, branch, **body):
        self.login(who)
        return self.client.patch(self.url_for(branch), body, content_type="application/json")

    def test_an_admin_sets_their_clinics_place_and_the_public_sees_the_governorate_only(self):
        response = self.patch("admin-a", self.a, governorate="الجيزة", latitude="30.01", longitude="31.21")
        self.assertEqual(response.status_code, 200, response.content)
        self.a.refresh_from_db()
        self.assertEqual((self.a.governorate, self.a.latitude), ("الجيزة", Decimal("30.010000")))
        self.client.logout()
        about = self.client.get(reverse("api:portal:about", kwargs={"slug": self.tenant.slug})).json()
        shown = next(b for b in about["branches"] if b["name"] == "Clinic A")
        self.assertEqual(shown["governorate"], "الجيزة")
        self.assertNotIn("latitude", shown)

    def test_a_point_needs_both_numbers_and_real_ones(self):
        for body in ({"latitude": None}, {"latitude": "95", "longitude": "10"}, {"latitude": "10", "longitude": "181"}):
            with self.subTest(body=body):
                self.assertEqual(self.patch("admin-a", self.a, **body).status_code, 400)
        self.a.refresh_from_db()
        self.assertEqual(self.a.latitude, Decimal(CAIRO[0]))

    def test_an_admin_cannot_move_another_clinic_and_reception_cannot_edit(self):
        self.assertEqual(self.patch("admin-a", self.b, governorate="X").status_code, 404)
        self.assertEqual(self.patch("rec", self.a, governorate="X").status_code, 403)
        self.assertEqual(self.patch("owner", self.b, governorate="مطروح").status_code, 200)


class MathTests(NearbyBase):
    def test_distance_is_about_right(self):
        km = distance_km(*map(float, CAIRO), *map(float, ALEXANDRIA))
        self.assertTrue(175 < km < 185, km)
        self.assertAlmostEqual(distance_km(30, 31, 30, 31), 0.0)

    def test_parsing_and_normalising(self):
        self.assertEqual(parse_point({"lat": "30.5", "lng": "31"}), (30.5, 31.0))
        self.assertIsNone(parse_point({"lat": "x", "lng": "1"}))
        self.assertEqual(normalize("  الإسكندرية "), normalize("الاسكندريه"))
