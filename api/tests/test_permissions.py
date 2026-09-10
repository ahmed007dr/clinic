"""Roles, branches, and who the API refuses.

The clinic's rule is that Reception books, registers and takes payment, and
never sees a diagnosis. That rule was enforced by the server-rendered views;
the API is a second door onto the same records, so it has to be enforced —
and demonstrated — again here.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from appointments.models import Appointment
from billing.models import Payment
from branches.models import Branch
from medical.models import Visit
from patients.models import Patient
from tenants.context import tenant_context
from tenants.models import Tenant

User = get_user_model()

CLINICAL_ENDPOINTS = [
    "api:visit-list",
    "api:prescription-list",
    "api:treatmentplan-list",
    "api:treatmentsession-list",
    "api:procedure-list",
    "api:labresult-list",
    "api:attachment-list",
]


class RoleTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            self.branch = Branch.all_objects.create(
                tenant=self.tenant, name="Main", code="MN"
            )
            self.other = Branch.all_objects.create(
                tenant=self.tenant, name="Other", code="OT"
            )
            roles = {}
            for name in ("Admin", "Reception", "Doctor"):
                roles[name], _ = ClinicRole.all_objects.get_or_create(
                    tenant=self.tenant, name=name
                )
            self.patient = Patient.all_objects.create(
                tenant=self.tenant, name="Here", branch=self.branch
            )
            self.far_patient = Patient.all_objects.create(
                tenant=self.tenant, name="There", branch=self.other
            )
            self.visit = Visit.all_objects.create(
                tenant=self.tenant, patient=self.patient, branch=self.branch,
                diagnosis="private",
            )

        self.users = {}
        for name in ("Admin", "Reception", "Doctor"):
            self.users[name] = User.objects.create_user(
                username=name.lower(), email=f"{name.lower()}-perm@t.local",
                password="pass12345", tenant=self.tenant,
                role=roles[name], branch=self.branch,
            )

    def login(self, role):
        self.assertTrue(
            self.client.login(
                email=f"{role.lower()}-perm@t.local", password="pass12345"
            )
        )

    # ------------------------------------------------------------- clinical

    def test_reception_is_refused_every_clinical_endpoint(self):
        self.login("Reception")
        for name in CLINICAL_ENDPOINTS:
            with self.subTest(endpoint=name):
                response = self.client.get(reverse(name))
                self.assertEqual(
                    response.status_code, 403,
                    f"{name} answered {response.status_code} to Reception",
                )

    def test_reception_cannot_read_one_clinical_record_either(self):
        """A list that is refused but a detail that is not would be no
        protection at all — the UUID is in the appointment they just made."""
        self.login("Reception")
        response = self.client.get(reverse("api:visit-detail", args=[self.visit.uuid]))
        self.assertEqual(response.status_code, 403)

    def test_reception_cannot_write_a_clinical_record(self):
        self.login("Reception")
        response = self.client.post(
            reverse("api:visit-list"),
            {"patient": str(self.patient.uuid), "diagnosis": "invented"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Visit.all_objects.filter(diagnosis="invented").count(), 0)

    def test_doctors_and_admins_may_read_clinical_records(self):
        for role in ("Doctor", "Admin"):
            with self.subTest(role=role):
                self.login(role)
                response = self.client.get(reverse("api:visit-list"))
                self.assertEqual(response.status_code, 200)

    def test_no_diagnosis_reaches_reception_through_the_patient_timeline(self):
        """The timeline merges six record types into one list, which is
        exactly the shape of thing that leaks by forgetting one branch of an
        `if`. Asserted on the response body, not on the query."""
        self.login("Reception")
        response = self.client.get(
            reverse("api:patient-timeline", args=[self.patient.uuid])
        )
        self.assertEqual(response.status_code, 200)
        kinds = {entry["kind"] for entry in response.json()["entries"]}
        self.assertNotIn("visit", kinds)
        self.assertNotIn("prescription", kinds)
        self.assertNotIn("lab", kinds)
        self.assertNotIn("private", response.content.decode())

    # ------------------------------------------------------------ administration

    def test_only_an_admin_may_manage_staff(self):
        for role, expected in (("Admin", 200), ("Doctor", 403), ("Reception", 403)):
            with self.subTest(role=role):
                self.login(role)
                self.assertEqual(
                    self.client.get(reverse("api:staff-list")).status_code, expected
                )

    def test_only_an_admin_may_see_salaries(self):
        for role, expected in (("Admin", 200), ("Doctor", 403), ("Reception", 403)):
            with self.subTest(role=role):
                self.login(role)
                self.assertEqual(
                    self.client.get(reverse("api:employee-list")).status_code, expected
                )

    def test_everyone_may_read_reference_data_but_only_admin_may_change_it(self):
        for role in ("Doctor", "Reception"):
            with self.subTest(role=role):
                self.login(role)
                self.assertEqual(
                    self.client.get(reverse("api:service-list")).status_code, 200
                )
                created = self.client.post(
                    reverse("api:service-list"),
                    {"name": "Invented", "base_price": "5.00"},
                    content_type="application/json",
                )
                self.assertEqual(created.status_code, 403)

        self.login("Admin")
        allowed = self.client.post(
            reverse("api:service-list"),
            {"name": "Legitimate", "base_price": "5.00"},
            content_type="application/json",
        )
        self.assertEqual(allowed.status_code, 201, allowed.content)

    # ------------------------------------------------------------------ branch

    def test_a_non_admin_sees_only_their_own_branch(self):
        self.login("Reception")
        names = {
            row["name"]
            for row in self.client.get(reverse("api:patient-list")).json()["results"]
        }
        self.assertEqual(names, {"Here"})

    def test_an_admin_sees_every_branch(self):
        self.login("Admin")
        names = {
            row["name"]
            for row in self.client.get(reverse("api:patient-list")).json()["results"]
        }
        self.assertEqual(names, {"Here", "There"})

    def test_another_branchs_record_is_a_404_for_a_non_admin(self):
        self.login("Reception")
        response = self.client.get(
            reverse("api:patient-detail", args=[self.far_patient.uuid])
        )
        self.assertEqual(response.status_code, 404)

    def test_the_dashboard_totals_respect_the_callers_branch(self):
        """An aggregate that quietly covers the whole clinic is worse than no
        number at all, because nothing about the screen says it is wrong."""
        with tenant_context(self.tenant):
            for branch, amount in ((self.branch, 100), (self.other, 500)):
                appointment = Appointment.all_objects.create(
                    tenant=self.tenant,
                    patient=self.patient if branch == self.branch else self.far_patient,
                    scheduled_date=timezone.now(), branch=branch,
                )
                Payment.all_objects.create(
                    tenant=self.tenant, appointment=appointment,
                    patient=appointment.patient, receipt_number=f"R{amount}",
                    amount=amount, branch=branch,
                )

        self.login("Reception")
        reception = self.client.get(reverse("api:dashboard")).json()
        self.assertEqual(reception["revenue"]["today"], 100)

        self.login("Admin")
        admin = self.client.get(reverse("api:dashboard")).json()
        self.assertEqual(admin["revenue"]["today"], 600)

    def test_reception_is_not_shown_the_clinics_expenses(self):
        self.login("Reception")
        self.assertNotIn("expenses", self.client.get(reverse("api:dashboard")).json())


class AnonymousTests(TestCase):
    """An unauthenticated call must fail as an API call, not as a web page."""

    def test_anonymous_requests_are_rejected_not_redirected(self):
        for name in ("api:patient-list", "api:dashboard", "api:visit-list"):
            with self.subTest(endpoint=name):
                response = self.client.get(reverse(name))
                self.assertIn(
                    response.status_code, (401, 403),
                    f"{name} answered {response.status_code}",
                )
                # A 302 to the login form is the failure this guards against:
                # the catch-all in project/urls.py redirects every unmatched
                # path, and a client that follows it receives HTML with a 200
                # and reports the app as hanging.
                self.assertNotEqual(response.status_code, 302)

    def test_the_session_endpoint_is_public_and_says_no(self):
        response = self.client.get(reverse("api:session"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["authenticated"])

    def test_the_session_endpoint_sets_the_csrf_cookie(self):
        """Without this the very first write of a fresh browser session fails
        CSRF validation, which presents as a broken login."""
        response = self.client.get(reverse("api:session"))
        self.assertIn("csrftoken", response.cookies)


class PlatformStaffTests(TestCase):
    """SaaS operators have their own audited route; the clinic API is not it."""

    def setUp(self):
        self.operator = User.objects.create_user(
            username="operator", email="ops@platform.local", password="pass12345",
            tenant=None, is_platform_staff=True,
        )

    def test_a_platform_operator_cannot_use_the_clinic_api(self):
        self.client.login(email="ops@platform.local", password="pass12345")
        response = self.client.get(reverse("api:patient-list"))
        self.assertEqual(response.status_code, 403)

    def test_signing_in_gives_the_owner_portal_and_no_clinic(self):
        response = self.client.post(
            reverse("api:login"),
            {"email": "ops@platform.local", "password": "pass12345"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["user"])
        self.assertEqual(response.json()["platform_user"]["email"], "ops@platform.local")
        # Signed in, and still refused by the clinic API.
        self.assertEqual(self.client.get(reverse("api:patient-list")).status_code, 403)


class SuspendedClinicTests(TestCase):
    """A clinic whose subscription has lapsed stops at the door."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Lapsed", slug="lapsed-api", status=Tenant.Status.SUSPENDED
        )
        with tenant_context(self.tenant):
            role, _ = ClinicRole.all_objects.get_or_create(
                tenant=self.tenant, name="Admin"
            )
        User.objects.create_user(
            username="lapsed", email="lapsed@t.local", password="pass12345",
            tenant=self.tenant, role=role,
        )

    def test_sign_in_is_refused_with_a_reason(self):
        """Refused at sign-in rather than as scattered failures later, so the
        clinic is told why instead of discovering it one screen at a time."""
        response = self.client.post(
            reverse("api:login"),
            {"email": "lapsed@t.local", "password": "pass12345"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("اشتراك", response.json()["detail"])
