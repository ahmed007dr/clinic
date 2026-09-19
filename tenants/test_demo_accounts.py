"""The demo logins: a random password per seed, and a way to switch them off."""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from accounts.models import ClinicRole
from branches.models import Branch
from tenants.context import tenant_context
from tenants.management.commands.seed_demo import Command as SeedDemo
from tenants.models import Tenant

User = get_user_model()


class DisableDemoAccountsTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            role, _ = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name="Reception")

        def make(email, **extra):
            defaults = {"tenant": self.tenant, "role": role}
            defaults.update(extra)
            return User.objects.create_user(
                username=email.split("@")[0] + str(User.objects.count()),
                email=email, password="pass12345", **defaults,
            )

        self.demo = [
            make("admin@dr-ahmed.local"),
            make("clinicadmin@dr-ahmed.local"),
            make("reception@nile-clinic.local"),
            make("doctor@nile-clinic.local"),
        ]
        # Everything below must survive the command untouched.
        self.real = make("reception@clinic-real.com")
        self.other_local = make("nurse@dr-ahmed.local")
        self.operator = make("admin@ops.local", tenant=None, role=None, is_platform_staff=True)

    def active(self, user):
        user.refresh_from_db()
        return user.is_active

    def test_dry_run_lists_the_demo_accounts_and_changes_nothing(self):
        out = StringIO()
        call_command("disable_demo_accounts", "--dry-run", stdout=out)
        for user in self.demo:
            self.assertIn(user.email, out.getvalue())
            self.assertTrue(self.active(user))

    def test_it_deactivates_exactly_the_seeded_logins(self):
        call_command("disable_demo_accounts", stdout=StringIO())
        for user in self.demo:
            self.assertFalse(self.active(user), user.email)
        for user in (self.real, self.other_local, self.operator):
            self.assertTrue(self.active(user), user.email)

    def test_a_deactivated_demo_account_cannot_sign_in(self):
        call_command("disable_demo_accounts", stdout=StringIO())
        self.assertFalse(
            self.client.login(email="admin@dr-ahmed.local", password="pass12345")
        )

    def test_running_it_twice_is_harmless(self):
        call_command("disable_demo_accounts", stdout=StringIO())
        out = StringIO()
        call_command("disable_demo_accounts", stdout=out)
        self.assertIn("No active demo accounts", out.getvalue())


class SeedDemoPasswordTests(TestCase):
    """The seeder used to give every account one password printed in the
    repository's own docs. It now uses the password chosen for the run, and
    never resets an account that already exists."""

    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            self.role, _ = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name="Doctor")
            self.branch = Branch.all_objects.create(tenant=self.tenant, name="S", code="SD")
        self.command = SeedDemo()
        self.command.password = "run-password-1"
        self.command.created_accounts = []

    def test_a_new_account_gets_the_runs_password(self):
        user = self.command._user(self.tenant, "doctor@seed.local", "doctor", self.role, self.branch)
        self.assertTrue(user.check_password("run-password-1"))
        self.assertEqual(self.command.created_accounts, ["doctor@seed.local"])

    def test_an_existing_account_keeps_its_password(self):
        self.command._user(self.tenant, "doctor@seed.local", "doctor", self.role, self.branch)
        self.command.password = "run-password-2"
        self.command.created_accounts = []
        user = self.command._user(self.tenant, "doctor@seed.local", "doctor", self.role, self.branch)
        self.assertTrue(user.check_password("run-password-1"))
        self.assertEqual(self.command.created_accounts, [])

    def test_reset_passwords_sets_the_fixed_password_on_existing_accounts(self):
        self.command._user(self.tenant, "doctor@seed.local", "doctor", self.role, self.branch)
        self.command.password = "showcase-password"
        self.command.reset_passwords = True
        user = self.command._user(self.tenant, "doctor@seed.local", "doctor", self.role, self.branch)
        self.assertTrue(user.check_password("showcase-password"))

    def test_reset_passwords_refuses_a_random_password(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("seed_demo", "--reset-passwords", stdout=StringIO())

    def test_the_old_published_password_is_gone(self):
        from tenants.management.commands import seed_demo

        self.assertFalse(hasattr(seed_demo, "DEMO_PASSWORD"))


class DemoPortalPatientsTests(TestCase):
    """The demo dataset includes patients who can sign in to the portal, and
    `disable_demo_accounts` switches those off with the staff logins."""

    PASSWORD = "Demo-Portal-Pass-1"

    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", "--password", cls.PASSWORD, stdout=StringIO())

    def portal_login(self, slug, phone, password=None):
        from django.urls import reverse

        return self.client.post(
            reverse("api:portal:login", kwargs={"slug": slug}),
            {"phone": phone, "password": password or self.PASSWORD},
            content_type="application/json",
        )

    def test_both_clinics_have_two_portal_patients_who_can_sign_in(self):
        for slug in ("dr-ahmed", "nile-clinic"):
            for phone in ("01099000001", "01099000002"):
                self.assertEqual(self.portal_login(slug, phone).status_code, 200, (slug, phone))

    def test_the_first_patient_has_something_in_every_tab(self):
        from django.urls import reverse

        self.portal_login("dr-ahmed", "01099000001")
        get = lambda name: self.client.get(reverse(f"api:portal:{name}", kwargs={"slug": "dr-ahmed"})).json()
        appointments = get("appointments")
        waiting = [a for a in appointments if a["status"] == "waiting"]
        self.assertEqual(len(waiting), 1)
        self.assertTrue(waiting[0]["ticket_number"])
        self.assertEqual(waiting[0]["queue_position"], waiting[0]["ahead_count"] + 1)
        self.assertGreater(float(waiting[0]["due"]), 0)  # part paid
        self.assertTrue(any(a["status"] == "requested" for a in appointments))
        self.assertTrue(get("prescriptions"))
        self.assertTrue(get("payments"))
        self.assertTrue(get("treatment-plans"))
        self.assertTrue(get("allergies"))
        # One lab result released, one held back.
        self.assertEqual(len(get("lab-results")), 1)

    def test_the_second_patient_is_new_with_an_empty_portal(self):
        from django.urls import reverse

        self.portal_login("dr-ahmed", "01099000002")
        for name in ("appointments", "prescriptions", "payments"):
            self.assertEqual(
                self.client.get(reverse(f"api:portal:{name}", kwargs={"slug": "dr-ahmed"})).json(), []
            )

    def test_disable_demo_accounts_switches_the_portal_logins_off_too(self):
        out = StringIO()
        call_command("disable_demo_accounts", "--dry-run", stdout=out)
        self.assertIn("portal dr-ahmed: 01099000001", out.getvalue())
        self.assertEqual(self.portal_login("dr-ahmed", "01099000001").status_code, 200)

        call_command("disable_demo_accounts", stdout=StringIO())
        for slug in ("dr-ahmed", "nile-clinic"):
            self.assertEqual(self.portal_login(slug, "01099000001").status_code, 400)
        again = StringIO()
        call_command("disable_demo_accounts", stdout=again)
        self.assertIn("No active demo accounts", again.getvalue())

    def test_a_real_patient_is_never_switched_off(self):
        from patients.models import Patient
        from portal.models import PatientAccount

        tenant = Tenant.objects.get(slug="dr-ahmed")
        with tenant_context(tenant):
            real = Patient.objects.create(
                tenant=tenant, name="Real", phone1="01111111111", email="real@clinic.com"
            )
            PatientAccount.objects.create(tenant=tenant, patient=real)
        call_command("disable_demo_accounts", stdout=StringIO())
        with tenant_context(tenant):
            self.assertTrue(PatientAccount.objects.get(patient=real).is_active)


class DemoWebsiteCustomerTests(TestCase):
    """The third demo patient is the website customer: her portal shows the
    public booking journey in every state (tenants/management/commands/_demo_portal.py)."""

    PASSWORD = "Demo-Portal-Pass-3"

    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", "--password", cls.PASSWORD, stdout=StringIO())

    def test_she_signs_in_and_sees_requests_a_confirmed_booking_quantity_and_online_payment(self):
        from django.urls import reverse

        signed = self.client.post(
            reverse("api:portal:login", kwargs={"slug": "dr-ahmed"}),
            {"phone": "01099000003", "password": self.PASSWORD}, content_type="application/json")
        self.assertEqual(signed.status_code, 200)
        bookings = self.client.get(reverse("api:portal:appointments", kwargs={"slug": "dr-ahmed"})).json()
        by_status = {b["status"] for b in bookings}
        self.assertTrue({"requested", "waiting", "cancelled"} <= by_status, by_status)
        self.assertTrue(all(b["source"] == "portal" for b in bookings))
        self.assertTrue(any(b["quantity"] for b in bookings))
        self.assertTrue(any(b["payment_status"] == "paid" for b in bookings))
        self.assertTrue(any(b["reschedule_requested_for"] for b in bookings))

    def test_disabling_the_demo_accounts_switches_her_login_off_too(self):
        out = StringIO()
        call_command("disable_demo_accounts", "--dry-run", stdout=out)
        self.assertIn("portal dr-ahmed: 01099000003", out.getvalue())
