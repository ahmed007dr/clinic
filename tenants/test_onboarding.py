"""TENANT-008 — onboarding a real second tenant.

This is the step the whole sequence was building toward: a tenant created from
scratch has to be immediately usable *and* see nothing belonging to anyone
else. Everything before this was verified with one tenant, where isolation
cannot really fail.
"""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse

from accounts.models import ClinicRole
from branches.models import Branch
from employees.models import EmployeeType
from patients.models import Patient

from .context import tenant_context
from .models import Tenant
from .provisioning import create_first_branch, create_tenant_admin, provision_tenant_defaults

User = get_user_model()


def onboard(name="Nile Clinic", slug="nile-clinic", email="admin@nile.example", **kwargs):
    out = StringIO()
    call_command("create_tenant", name, slug=slug, admin_email=email, stdout=out, **kwargs)
    return Tenant.objects.get(slug=slug), out.getvalue()


class CreateTenantCommandTests(TestCase):
    def test_provisions_a_complete_usable_tenant(self):
        tenant, _ = onboard()

        with tenant_context(tenant):
            roles = set(ClinicRole.all_objects.filter(tenant=tenant).values_list("name", flat=True))
            self.assertEqual(roles, {"Owner", "Admin", "Reception", "Doctor"})
            self.assertTrue(EmployeeType.all_objects.filter(tenant=tenant, name="Doctor").exists())
            self.assertEqual(Branch.all_objects.filter(tenant=tenant).count(), 1)

        admin = User.objects.get(email="admin@nile.example")
        self.assertEqual(admin.tenant, tenant)
        # accounts_user carries no RLS policy — authentication has to find the
        # user before any tenant is known — but role and branch do, so
        # following those FKs needs the binding.
        with tenant_context(tenant):
            self.assertEqual(admin.role.name, "Owner")
            self.assertEqual(admin.branch.tenant, tenant)

    def test_generated_password_is_shown_and_actually_works(self):
        _, output = onboard()
        password = [
            line.split()[-1] for line in output.splitlines() if line.strip().startswith("password")
        ][0]
        self.assertTrue(self.client.login(email="admin@nile.example", password=password))

    def test_explicit_password_is_not_echoed(self):
        _, output = onboard(admin_password="chosen-by-the-operator")
        self.assertNotIn("chosen-by-the-operator", output)

    def test_duplicate_slug_is_refused(self):
        onboard()
        with self.assertRaises(CommandError):
            onboard(email="someone-else@nile.example")

    def test_duplicate_email_is_refused(self):
        onboard()
        with self.assertRaises(CommandError):
            onboard(name="Third Clinic", slug="third-clinic")

    def test_a_refused_onboarding_leaves_nothing_behind(self):
        """One transaction — a half-built tenant nobody can log into is worse
        than no tenant."""
        before = Tenant.objects.count()
        with self.assertRaises(CommandError):
            onboard(email="not-an-email")
        self.assertEqual(Tenant.objects.count(), before)

    def test_arabic_branch_name_does_not_break_the_report(self):
        """Regression: printing an Arabic branch name crashed on a cp1252
        console, and it crashed *after* the commit but *before* the generated
        password was shown — losing a credential that cannot be recovered."""
        _, output = onboard(branch="المعادي", branch_code="MAADI")
        self.assertIn("password", output)
        with tenant_context(Tenant.objects.get(slug="nile-clinic")):
            branch = Branch.all_objects.get(tenant__slug="nile-clinic")
        self.assertEqual(branch.name, "المعادي")

    def test_credentials_are_printed_before_any_user_supplied_text(self):
        _, output = onboard(branch="المعادي", branch_code="MAADI")
        self.assertLess(output.index("password"), output.index("branch"))

    def test_non_ascii_name_without_a_slug_is_refused_clearly(self):
        """slugify() yields "" for Arabic, which would otherwise create a
        tenant with a blank slug."""
        with self.assertRaises(CommandError):
            call_command("create_tenant", "عيادة النيل", admin_email="a@b.example", stdout=StringIO())


class NewTenantIsolationTests(TestCase):
    """The real proof: onboard a second tenant beside the existing one and
    confirm neither can see the other."""

    def setUp(self):
        self.existing = Tenant.objects.first()
        provision_tenant_defaults(self.existing)
        branch = create_first_branch(self.existing, "Existing Branch", "EX")
        self.existing_admin, self.existing_password = create_tenant_admin(
            self.existing, "admin@existing.example", password="pass12345", branch=branch
        )
        with tenant_context(self.existing):
            self.existing_patient = Patient.all_objects.create(
                tenant=self.existing, name="Existing Patient", branch=branch
            )

        self.new, output = onboard()
        self.new_password = [
            line.split()[-1] for line in output.splitlines() if line.strip().startswith("password")
        ][0]

    def test_a_new_tenant_starts_with_no_patients(self):
        self.client.login(email="admin@nile.example", password=self.new_password)
        response = self.client.get(reverse("patients:patient_list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Existing Patient")

    def test_a_new_tenant_cannot_open_the_other_tenants_patient(self):
        self.client.login(email="admin@nile.example", password=self.new_password)
        response = self.client.get(
            reverse("patients:patient_detail", args=[self.existing_patient.uuid])
        )
        self.assertEqual(response.status_code, 404)

    def test_the_existing_tenant_is_unaffected_by_the_new_one(self):
        with tenant_context(self.new):
            Patient.all_objects.create(
                tenant=self.new, name="Nile Patient",
                branch=Branch.all_objects.get(tenant=self.new),
            )
        self.client.login(email="admin@existing.example", password="pass12345")
        response = self.client.get(reverse("patients:patient_list"))
        self.assertContains(response, "Existing Patient")
        self.assertNotContains(response, "Nile Patient")

    def test_each_tenant_gets_its_own_roles_not_shared_rows(self):
        # Each side is read under its own binding. Read unbound, both sets come
        # back empty and isdisjoint() is trivially true — the assertion would
        # hold even if the two tenants shared every row.
        with tenant_context(self.existing):
            existing_roles = set(
                ClinicRole.all_objects.filter(tenant=self.existing).values_list("id", flat=True)
            )
        with tenant_context(self.new):
            new_roles = set(
                ClinicRole.all_objects.filter(tenant=self.new).values_list("id", flat=True)
            )
        self.assertTrue(existing_roles)
        self.assertTrue(new_roles)
        self.assertTrue(existing_roles.isdisjoint(new_roles))

    def test_both_tenants_can_hold_a_branch_with_the_same_name(self):
        create_first_branch(self.new, "Existing Branch", "EX")
        for tenant in (self.existing, self.new):
            with self.subTest(tenant=tenant.slug), tenant_context(tenant):
                self.assertEqual(
                    Branch.all_objects.filter(tenant=tenant, name="Existing Branch").count(), 1
                )

    def test_serial_numbers_restart_for_the_new_tenant(self):
        """The new clinic's ticket numbers must not disclose the other's volume."""
        with tenant_context(self.existing):
            for i in range(3):
                Patient.all_objects.create(
                    tenant=self.existing, name=f"E{i}",
                    branch=Branch.all_objects.filter(tenant=self.existing).first(),
                )
        with tenant_context(self.new):
            first_for_new = Patient.all_objects.create(
                tenant=self.new, name="First",
                branch=Branch.all_objects.get(tenant=self.new),
            )
        self.assertTrue(first_for_new.serial_number.endswith("-001"))
