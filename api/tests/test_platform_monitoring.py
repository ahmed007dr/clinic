"""Developer portal, phase 1: who is online, last seen, and the people of
every group and clinic — for operators only, and only counts and accounts."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from branches.models import Branch
from employees.models import Employee, EmployeeType
from tenants.context import tenant_context
from tenants.models import Tenant
from tenants.testing import login_platform

User = get_user_model()


class MonitoringTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Nile Group", slug="nile-mon", status="active")
        with tenant_context(self.tenant):
            self.main = Branch.all_objects.create(tenant=self.tenant, name="Main", code="MN")
            self.east = Branch.all_objects.create(tenant=self.tenant, name="East", code="ES")
            roles = {
                n: ClinicRole.all_objects.get_or_create(tenant=self.tenant, name=n)[0]
                for n in ("Owner", "Doctor", "Reception")
            }
            doctor = EmployeeType.all_objects.create(tenant=self.tenant, name="Doctor")
            nurse = EmployeeType.all_objects.create(tenant=self.tenant, name="Nurse")
            for name, kind, branch, nid in (
                ("Dr A", doctor, self.main, "M1"), ("Dr B", doctor, self.east, "M2"),
                ("Nurse C", nurse, self.main, "M3"),
            ):
                Employee.all_objects.create(
                    tenant=self.tenant, name=name, employee_type=kind, branch=branch,
                    national_id=nid, salary_value=0,
                )
        now = timezone.now()
        for username, role, branch, seen in (
            ("owner", "Owner", self.main, now),
            ("desk", "Reception", self.main, now - timedelta(hours=3)),
            ("doc", "Doctor", self.east, now - timedelta(minutes=1)),
        ):
            User.objects.create_user(
                username=username, email=f"{username}@mon.local", password="pass12345",
                tenant=self.tenant, role=roles[role], branch=branch, last_seen_at=seen,
            )
        User.objects.create_user(
            username="ops", email="ops@mon.local", password="pass12345",
            tenant=None, is_platform_staff=True, platform_role="support",
        )
        login_platform(self.client, "ops@mon.local")

    def test_the_overview_counts_people_and_activity_per_group(self):
        data = self.client.get(reverse("api:platform-overview")).json()
        row = next(g for g in data["groups"] if g["slug"] == "nile-mon")
        self.assertEqual((row["branches"], row["doctors"], row["employees"]), (2, 2, 3))
        self.assertEqual((row["accounts"], row["online"]), (3, 2))
        self.assertEqual(row["owners"], [{"name": "owner", "email": "owner@mon.local"}])
        self.assertFalse(row["inactive"])
        self.assertGreaterEqual(data["totals"]["online"], 2)

    def test_each_clinic_of_a_group_has_its_own_counts(self):
        data = self.client.get(reverse("api:platform-tenant-people", args=[self.tenant.uuid])).json()
        branches = {b["name"]: b for b in data["branches"]}
        self.assertEqual((branches["Main"]["doctors"], branches["Main"]["employees"]), (1, 2))
        self.assertEqual((branches["East"]["doctors"], branches["East"]["online"]), (1, 1))
        desk = next(a for a in data["accounts"] if a["username"] == "desk")
        self.assertFalse(desk["online"])
        self.assertIsNotNone(desk["last_seen_at"])

    def test_online_now_lists_active_accounts_across_groups(self):
        names = {row["username"] for row in self.client.get(reverse("api:platform-online")).json()}
        self.assertTrue({"owner", "doc"} <= names)
        self.assertNotIn("desk", names)

    def test_a_group_nobody_used_for_a_week_is_flagged(self):
        User.objects.filter(tenant=self.tenant).update(last_seen_at=timezone.now() - timedelta(days=30))
        data = self.client.get(reverse("api:platform-overview")).json()
        self.assertTrue(next(g for g in data["groups"] if g["slug"] == "nile-mon")["inactive"])

    def test_clinic_users_are_refused(self):
        self.client.logout()
        self.client.login(email="owner@mon.local", password="pass12345")
        self.assertEqual(self.client.get(reverse("api:platform-overview")).status_code, 403)
