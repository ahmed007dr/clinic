"""The public surface of the booking portal, checked as a whole (docs/15, Phase 10).

Not one feature's tests but the properties that must hold across all of them:
everything anonymous can read carries no internal identifier or private field;
every staff endpoint added for this work refuses patients and anonymous callers;
a session of one group is worthless in another; and every write needs the CSRF
token. A green front end proves none of this — these are the server's answers.
"""

import json

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from accounts.models import ClinicRole
from tenants.context import tenant_context
from tenants.models import Tenant

from .test_my_bookings import MyBookingBase

User = get_user_model()

#: Names that must never appear as a key anywhere in a public response.
FORBIDDEN_KEYS = {
    "id", "pk", "tenant", "tenant_id", "national_id", "salary", "salary_value", "commission",
    "commission_percent", "email", "phone2", "notes", "user", "password", "created_by",
    "media_reviewed_by", "review_note", "pending_logo", "pending_cover", "reason",
    "profile_status", "pending_profile", "whatsapp", "consent", "serial_number",
}


def keys_in(value, path=""):
    """Every dict key in a JSON value, with where it was found."""
    found = []
    if isinstance(value, dict):
        for key, inner in value.items():
            found.append((key, f"{path}/{key}"))
            found.extend(keys_in(inner, f"{path}/{key}"))
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            found.extend(keys_in(inner, f"{path}[{index}]"))
    return found


class SurfaceBase(MyBookingBase):
    def setUp(self):
        super().setUp()
        self.public_paths = [
            self.url("about"),
            self.url("links"),
            self.url("catalog-services"),
            self.url("catalog-branches", service=self.service.uuid),
            self.url("catalog-doctors", service=self.service.uuid, branch=self.branch.uuid),
            self.url("catalog-availability") + f"?service={self.service.uuid}&branch={self.branch.uuid}"
                f"&doctor={self.dr_main.uuid}&date={self.day.isoformat()}",
            self.url("catalog-availability-days") + f"?service={self.service.uuid}&branch={self.branch.uuid}"
                f"&doctor={self.dr_main.uuid}",
        ]
        # Give the public page every private field a leak could show.
        with tenant_context(self.a):
            self.dr_main.public_profile = {"tagline": "Hello", "links": {}}
            self.dr_main.email = "secret@doctor.example"
            self.dr_main.national_id = "SECRET-NID"
            self.dr_main.salary_value = 9876543
            self.dr_main.commission_percent = 33
            self.dr_main.save()
        self.anonymous = Client()


class PublicReadsTests(SurfaceBase):
    def test_every_public_read_works_without_signing_in_and_leaks_no_private_field(self):
        for path in self.public_paths:
            with self.subTest(path=path):
                response = self.anonymous.get(path)
                self.assertEqual(response.status_code, 200, response.content)
                found = [where for key, where in keys_in(response.json()) if key in FORBIDDEN_KEYS]
                self.assertEqual(found, [], f"private keys in {path}")
                text = response.content.decode()
                for secret in ("secret@doctor.example", "SECRET-NID", "9876543"):
                    self.assertNotIn(secret, text)

    def test_public_reads_do_not_accept_writes(self):
        for path in self.public_paths:
            with self.subTest(path=path):
                self.assertEqual(self.anonymous.post(path.split("?")[0], {}, content_type="application/json").status_code, 405)
                self.assertEqual(self.anonymous.delete(path.split("?")[0]).status_code, 405)

    def test_a_stopped_group_serves_no_public_page(self):
        Tenant.objects.filter(pk=self.a.pk).update(status="suspended")
        for path in self.public_paths:
            with self.subTest(path=path):
                self.assertEqual(self.anonymous.get(path).status_code, 403)

    def test_an_unknown_group_is_a_404_not_a_guess(self):
        response = self.anonymous.get(reverse("api:portal:catalog-services", kwargs={"slug": "no-such-group"}))
        self.assertEqual(response.status_code, 404)

    def test_no_public_response_names_a_patient(self):
        for path in self.public_paths:
            self.assertNotIn("Alice", self.anonymous.get(path).content.decode())


class StaffEndpointsAreClosedToPatientsTests(SurfaceBase):
    def setUp(self):
        super().setUp()
        self.staff_endpoints = [
            ("get", reverse("api:public-media")),
            ("post", reverse("api:public-media-group")),
            ("post", reverse("api:public-media-branch", args=[self.branch.uuid])),
            ("post", reverse("api:public-media-review", args=[self.branch.uuid])),
            ("get", reverse("api:branch-services")),
            ("put", reverse("api:branch-services")),
            ("get", reverse("api:schedules")),
            ("put", reverse("api:schedules")),
            ("get", reverse("api:doctortimeoff-list")),
            ("get", reverse("api:branchholiday-list")),
            ("get", reverse("api:patient-list")),
            ("get", reverse("api:appointment-list")),
        ]

    def call(self, client, method, url):
        return getattr(client, method)(url, {} if method != "get" else None, **(
            {"content_type": "application/json"} if method != "get" else {}))

    def test_anonymous_callers_are_refused(self):
        for method, url in self.staff_endpoints:
            with self.subTest(url=url):
                self.assertIn(self.call(self.anonymous, method, url).status_code, (401, 403))

    def test_a_patients_portal_session_is_refused_by_every_one(self):
        # `self.client` holds Alice's portal cookie.
        for method, url in self.staff_endpoints:
            with self.subTest(url=url):
                self.assertIn(self.call(self.client, method, url).status_code, (401, 403))

    def test_reception_cannot_reach_the_management_only_ones(self):
        with tenant_context(self.a):
            role = ClinicRole.all_objects.get_or_create(tenant=self.a, name="Reception")[0]
        User.objects.create_user(username="rec", email="rec@t.local", password="pass12345",
                                 tenant=self.a, role=role, branch=self.branch)
        staff = Client()
        staff.login(email="rec@t.local", password="pass12345")
        for method, url in self.staff_endpoints[:10]:
            with self.subTest(url=url):
                self.assertEqual(self.call(staff, method, url).status_code, 403)

    def test_a_staff_session_means_nothing_to_the_portals_new_endpoints(self):
        with tenant_context(self.a):
            role = ClinicRole.all_objects.get_or_create(tenant=self.a, name="Owner")[0]
        User.objects.create_user(username="own", email="own@t.local", password="pass12345",
                                 tenant=self.a, role=role, branch=self.branch)
        staff = Client()
        staff.login(email="own@t.local", password="pass12345")
        for name in ("profile", "appointments"):
            self.assertIn(staff.get(self.url(name)).status_code, (401, 403), name)
        self.assertIn(staff.post(self.url("account-verify"), {"ticket": "x", "code": "1"},
                                 content_type="application/json").status_code, (400, 404))


class AcrossGroupsTests(SurfaceBase):
    def test_a_portal_session_of_one_group_is_worthless_in_another(self):
        for name in ("me", "profile", "appointments"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(self.url(name, tenant=self.b)).status_code, 401)

    def test_a_booking_uuid_of_one_group_is_not_found_through_another(self):
        booking = self.make()
        self.assertEqual(self.client.get(self.url("appointment-detail", uuid=booking.uuid, tenant=self.b)).status_code, 401)


class CsrfTests(SurfaceBase):
    """Every write needs the token: a forged form on another site cannot act
    for a signed-in patient, nor open a public write path."""

    def strict(self, client=None):
        source = client or self.client
        strict = Client(enforce_csrf_checks=True)
        strict.cookies = source.cookies
        return strict

    def test_the_public_writes_refuse_a_request_without_the_token(self):
        for name, body in (
            ("account-start", {"name": "X"}),
            ("account-verify", {"ticket": "x", "code": "1"}),
            ("login", {"phone": "1", "password": "x"}),
            ("otp-request", {"identifier": "a@b.c"}),
        ):
            with self.subTest(name=name):
                response = Client(enforce_csrf_checks=True).post(self.url(name), body, content_type="application/json")
                self.assertEqual(response.status_code, 403)

    def test_a_signed_in_patients_writes_refuse_a_request_without_the_token(self):
        booking = self.make()
        strict = self.strict()
        for method, url, body in (
            ("post", self.url("appointments"), self.body()),
            ("post", self.url("appointment-cancel", uuid=booking.uuid), {}),
            ("post", self.url("appointment-reschedule", uuid=booking.uuid), {"slot": self.slot("09:45")}),
            ("patch", self.url("profile"), {"address": "x"}),
            ("post", self.url("email-change"), {"email": "a@b.example"}),
        ):
            with self.subTest(url=url):
                response = getattr(strict, method)(url, json.dumps(body), content_type="application/json")
                self.assertIn(response.status_code, (401, 403))
        self.assertEqual(self.reload(booking).status, "requested")
        self.assertEqual(len(self.appointments(patient=self.alice)), 1)  # only the fixture
