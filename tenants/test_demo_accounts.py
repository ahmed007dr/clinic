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

    def test_the_old_published_password_is_gone(self):
        from tenants.management.commands import seed_demo

        self.assertFalse(hasattr(seed_demo, "DEMO_PASSWORD"))
