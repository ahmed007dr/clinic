"""Group Owner vs clinic Admin — the boundary, through every door.

A medical group is a Tenant; its clinics are Branches. The Owner sees every
clinic; a clinic Admin runs one. These tests try, from a clinic Admin's chair,
each way that boundary could leak: the API, the old server-rendered screens,
the staff screen, the settings form, and the aggregates.
"""

import importlib
from types import SimpleNamespace

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from appointments.models import Appointment
from billing.models import Expense, Payment
from branches.models import Branch
from patients.models import Patient
from tenants.context import tenant_context
from tenants.models import Tenant

User = get_user_model()
PASSWORD = "pass12345"


class RoleBoundaryTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            self.roles = {
                name: ClinicRole.all_objects.get_or_create(tenant=self.tenant, name=name)[0]
                for name in ("Owner", "Admin", "Doctor", "Reception")
            }
            self.a = Branch.all_objects.create(tenant=self.tenant, name="Clinic A", code="CA")
            self.b = Branch.all_objects.create(tenant=self.tenant, name="Clinic B", code="CB")
            self.pa = Patient.all_objects.create(tenant=self.tenant, name="Patient A", branch=self.a)
            self.pb = Patient.all_objects.create(tenant=self.tenant, name="Patient B", branch=self.b)
        self.owner = self.user("owner", "Owner", self.a)
        self.admin_a = self.user("admin-a", "Admin", self.a)
        self.reception_b = self.user("reception-b", "Reception", self.b)

    def user(self, username, role, branch):
        return User.objects.create_user(
            username=username, email=f"{username}@roles.local", password=PASSWORD,
            tenant=self.tenant, role=self.roles[role], branch=branch,
        )

    def login(self, user):
        self.client.logout()
        self.assertTrue(self.client.login(email=user.email, password=PASSWORD))

    # ------------------------------------------------------------ reach

    def test_the_owner_sees_every_clinic(self):
        self.login(self.owner)
        names = {r["name"] for r in self.client.get(reverse("api:patient-list")).json()["results"]}
        self.assertEqual(names, {"Patient A", "Patient B"})

    def test_a_clinic_admin_sees_only_their_clinic(self):
        self.login(self.admin_a)
        names = {r["name"] for r in self.client.get(reverse("api:patient-list")).json()["results"]}
        self.assertEqual(names, {"Patient A"})
        self.assertEqual(
            self.client.get(reverse("api:patient-detail", args=[self.pb.uuid])).status_code, 404
        )

    def test_the_session_says_who_is_the_owner(self):
        self.login(self.owner)
        perms = self.client.get(reverse("api:session")).json()["user"]["permissions"]
        self.assertTrue(perms["is_owner"] and perms["all_branches"])
        self.login(self.admin_a)
        perms = self.client.get(reverse("api:session")).json()["user"]["permissions"]
        self.assertTrue(perms["is_admin"])
        self.assertFalse(perms["is_owner"] or perms["all_branches"])

    # ---------------------------------------------------- escalation

    def test_a_clinic_admin_cannot_create_an_owner(self):
        self.login(self.admin_a)
        response = self.client.post(reverse("api:staff-list"), {
            "username": "sneaky", "email": "sneaky@roles.local", "password": "long-password",
            "role": str(self.roles["Owner"].uuid), "branch": str(self.a.uuid),
        }, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("role", response.json())
        self.assertFalse(User.objects.filter(email="sneaky@roles.local").exists())

    def test_a_clinic_admin_cannot_staff_another_clinic(self):
        self.login(self.admin_a)
        response = self.client.post(reverse("api:staff-list"), {
            "username": "elsewhere", "email": "elsewhere@roles.local", "password": "long-password",
            "role": str(self.roles["Reception"].uuid), "branch": str(self.b.uuid),
        }, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("branch", response.json())

    def test_a_clinic_admin_neither_sees_nor_edits_the_owner(self):
        self.login(self.admin_a)
        emails = {r["email"] for r in self.client.get(reverse("api:staff-list")).json()["results"]}
        self.assertNotIn(self.owner.email, emails)
        self.assertNotIn(self.reception_b.email, emails)  # another clinic's staff
        response = self.client.patch(reverse("api:staff-detail", args=[self.owner.uuid]),
                                     {"is_active": False}, content_type="application/json")
        self.assertEqual(response.status_code, 404)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active)

    def test_the_owner_may_appoint_another_owner(self):
        self.login(self.owner)
        response = self.client.post(reverse("api:staff-list"), {
            "username": "partner", "email": "partner@roles.local", "password": "long-password",
            "role": str(self.roles["Owner"].uuid), "branch": str(self.b.uuid),
        }, content_type="application/json")
        self.assertEqual(response.status_code, 201, response.content)

    def test_a_clinic_admin_cannot_promote_themselves(self):
        """The old settings form let any Admin change their own role; the staff
        API must not either — not to Owner, and not to another clinic."""
        self.login(self.admin_a)
        for body in ({"role": self.roles["Owner"].pk}, {"branch": str(self.b.uuid)}):
            with self.subTest(body=body):
                self.client.patch(reverse("api:staff-detail", args=[self.admin_a.uuid]), body,
                                  content_type="application/json")
                self.admin_a.refresh_from_db()
                self.assertEqual(self.admin_a.role.name, "Admin")
                self.assertEqual(self.admin_a.branch_id, self.a.pk)

    # ---------------------------------------------------- group screens

    def test_group_structure_is_the_owners(self):
        self.login(self.admin_a)
        self.assertEqual(self.client.post(reverse("api:branch-list"), {"name": "C", "code": "C"},
                                          content_type="application/json").status_code, 403)
        self.assertEqual(self.client.get(reverse("api:subscription")).status_code, 403)
        self.assertEqual(self.client.get(reverse("api:clinic-settings")).status_code, 403)
        self.assertEqual(self.client.get(reverse("audit:audit_list")).status_code, 403)

        self.login(self.owner)
        self.assertEqual(self.client.get(reverse("api:subscription")).status_code, 200)
        self.assertEqual(self.client.get(reverse("audit:audit_list")).status_code, 200)

    # ---------------------------------------------------- aggregates

    def test_the_financial_report_does_not_double_count(self):
        """`annotate(Sum('payment__amount'), Sum('expenses__amount'))` joined two
        reverse relations at once, multiplying every payment by the number of
        expenses in the same clinic."""
        with tenant_context(self.tenant):
            appt = Appointment.all_objects.create(
                tenant=self.tenant, patient=self.pa, branch=self.a, scheduled_date=timezone.now()
            )
            Payment.all_objects.create(tenant=self.tenant, appointment=appt, patient=self.pa,
                                       receipt_number="R1", amount=100, branch=self.a)
            for amount in (10, 20):
                Expense.all_objects.create(tenant=self.tenant, branch=self.a, amount=amount,
                                           date=timezone.now().date())
        self.login(self.owner)
        report = self.client.get(reverse("api:financialreport-list")).json()
        rows = {row["name"]: row for row in report["by_branch"]}
        self.assertEqual(Decimal(str(rows["Clinic A"]["revenue"])), 100)
        self.assertEqual(Decimal(str(rows["Clinic A"]["expenses"])), 30)
        self.assertEqual(Decimal(str(report["revenue"])), 100)
        self.assertEqual(Decimal(str(report["expenses"])), 30)

    def test_the_financial_report_shows_a_clinic_admin_only_their_clinic(self):
        with tenant_context(self.tenant):
            for patient, branch, receipt, amount in ((self.pa, self.a, "RA", 100), (self.pb, self.b, "RB", 700)):
                appt = Appointment.all_objects.create(
                    tenant=self.tenant, patient=patient, branch=branch, scheduled_date=timezone.now()
                )
                Payment.all_objects.create(tenant=self.tenant, appointment=appt, patient=patient,
                                           receipt_number=receipt, amount=amount, branch=branch)
        self.login(self.admin_a)
        report = self.client.get(reverse("api:financialreport-list")).json()
        self.assertEqual(Decimal(str(report["revenue"])), 100)
        self.assertEqual(report["by_branch"], [])
        self.login(self.owner)
        self.assertEqual(Decimal(str(self.client.get(reverse("api:financialreport-list")).json()["revenue"])), 800)


class OwnerMigrationTests(TestCase):
    """accounts.0007: every existing Admin becomes an Owner, so nobody's
    access changes on deploy."""

    def test_existing_admins_are_promoted(self):
        tenant = Tenant.objects.first()
        with tenant_context(tenant):
            admin_role, _ = ClinicRole.all_objects.get_or_create(tenant=tenant, name="Admin")
        user = User.objects.create_user(username="legacy", email="legacy@roles.local",
                                        password=PASSWORD, tenant=tenant, role=admin_role)
        migration = importlib.import_module("accounts.migrations.0007_owner_role")
        state = MigrationExecutor(connection).loader.project_state([("accounts", "0007_owner_role")])
        with tenant_context(tenant):
            migration.promote_admins_to_owner(state.apps, SimpleNamespace(connection=connection))
        user.refresh_from_db()
        self.assertEqual(user.role.name, "Owner")
