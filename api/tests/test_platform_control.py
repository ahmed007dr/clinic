"""Developer portal, phase 4: full control over groups — editing, accounts,
clinics, services and limits, and time-limited "login as" for support."""

import time
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import ClinicRole
from audit.models import AuditLog
from branches.models import Branch
from notifications.models import Notification
from platform_admin.models import SupportSession
from subscriptions.entitlements import get_limit, has_feature
from subscriptions.models import Plan, Subscription
from tenants.context import tenant_context
from tenants.models import Tenant
from tenants.testing import login_platform

User = get_user_model()
PASSWORD = "pass12345"


class ControlBase(TestCase):
    def setUp(self):
        cache.clear()
        self.tenant = Tenant.objects.create(name="Delta", slug="delta", status="active")
        with tenant_context(self.tenant):
            self.branch = Branch.all_objects.create(tenant=self.tenant, name="Delta Main", code="DM")
            Subscription.all_objects.create(tenant=self.tenant, plan=Plan.objects.get(code="basic"), status="active")
            roles = {n: ClinicRole.all_objects.get_or_create(tenant=self.tenant, name=n)[0]
                     for n in ("Owner", "Reception")}
        self.owner = User.objects.create_user(username="owner", email="owner@delta.test", password=PASSWORD,
                                              tenant=self.tenant, role=roles["Owner"], branch=self.branch)
        self.desk = User.objects.create_user(username="desk", email="desk@delta.test", password=PASSWORD,
                                             tenant=self.tenant, role=roles["Reception"], branch=self.branch)
        User.objects.create_user(username="root", email="root@ops.local", password=PASSWORD, tenant=None,
                                 is_platform_staff=True, platform_role="super")
        User.objects.create_user(username="help", email="help@ops.local", password=PASSWORD, tenant=None,
                                 is_platform_staff=True, platform_role="support")
        login_platform(self.client, "root@ops.local")

    def post(self, name, data=None, *args):
        return self.client.post(reverse(f"api:{name}", args=args), data or {}, content_type="application/json")

    def patch(self, name, data, *args):
        return self.client.patch(reverse(f"api:{name}", args=args), data, content_type="application/json")


class GroupAndAccountTests(ControlBase):
    def test_edit_the_group(self):
        data = self.patch("platform-tenant-edit", {"name": "Delta Care", "slug": "delta-care",
                                                   "portal_self_registration": True}, self.tenant.uuid).json()
        self.assertEqual((data["name"], data["slug"]), ("Delta Care", "delta-care"))
        self.tenant.refresh_from_db()
        self.assertTrue(self.tenant.portal_self_registration)
        self.assertEqual(self.patch("platform-tenant-edit", {"slug": "bad slug"}, self.tenant.uuid).status_code, 400)

    def test_reset_a_password_signs_the_account_out_everywhere(self):
        desk = Client()
        desk.login(email="desk@delta.test", password=PASSWORD)
        self.assertTrue(desk.get(reverse("api:session")).json()["authenticated"])
        data = self.post("platform-account-action", {}, self.desk.uuid, "reset-password").json()
        self.assertEqual(data["ended_sessions"], 1)
        self.assertFalse(desk.get(reverse("api:session")).json()["authenticated"])
        self.desk.refresh_from_db()
        self.assertTrue(self.desk.check_password(data["password"]))

    def test_stop_and_restart_an_account(self):
        self.post("platform-account-action", {}, self.desk.uuid, "deactivate")
        self.desk.refresh_from_db()
        self.assertFalse(self.desk.is_active)
        self.post("platform-account-action", {}, self.desk.uuid, "activate")
        self.desk.refresh_from_db()
        self.assertTrue(self.desk.is_active)
        self.assertTrue(AuditLog.objects.filter(tenant=self.tenant, description__contains="account deactivate").exists())

    def test_platform_operators_are_out_of_reach(self):
        root = User.objects.get(username="root")
        self.assertEqual(self.post("platform-account-action", {}, root.uuid, "deactivate").status_code, 404)

    def test_add_another_owner(self):
        response = self.post("platform-tenant-owners", {"email": "partner@delta.test"}, self.tenant.uuid)
        self.assertEqual(response.status_code, 201, response.content)
        partner = User.objects.get(email="partner@delta.test")
        self.assertEqual((partner.tenant, partner.role.name), (self.tenant, "Owner"))
        self.assertTrue(partner.check_password(response.json()["password"]))

    def test_stop_a_clinic(self):
        data = self.post("platform-tenant-branch-active", {"active": False}, self.tenant.uuid, self.branch.pk).json()
        self.assertFalse(data["is_active"])
        with tenant_context(self.tenant):
            self.assertFalse(Branch.all_objects.get(pk=self.branch.pk).is_active)

    def test_support_staff_change_nothing(self):
        self.client.logout()
        login_platform(self.client, "help@ops.local")
        self.assertEqual(self.post("platform-account-action", {}, self.desk.uuid, "deactivate").status_code, 403)
        self.assertEqual(self.patch("platform-tenant-edit", {"name": "X"}, self.tenant.uuid).status_code, 403)


class EntitlementTests(ControlBase):
    def test_services_can_be_switched_on_and_off_beyond_the_plan(self):
        with tenant_context(self.tenant):
            self.assertFalse(has_feature(self.tenant, "online_payments"))
        data = self.patch("platform-tenant-entitlements", {"features": {"online_payments": True}},
                          self.tenant.uuid).json()
        row = next(f for f in data["features"] if f["key"] == "online_payments")
        self.assertEqual((row["in_plan"], row["override"], row["enabled"]), (False, True, True))
        self.patch("platform-tenant-entitlements", {"features": {"reports": False}}, self.tenant.uuid)
        with tenant_context(self.tenant):
            self.assertTrue(has_feature(self.tenant, "online_payments"))
            self.assertFalse(has_feature(self.tenant, "reports"))
        self.patch("platform-tenant-entitlements", {"features": {"online_payments": None}}, self.tenant.uuid)
        with tenant_context(self.tenant):
            self.assertFalse(has_feature(self.tenant, "online_payments"))

    def test_limits_can_be_raised_or_lifted(self):
        with tenant_context(self.tenant):
            plan_value = get_limit(self.tenant, "max_branches")
        self.patch("platform-tenant-entitlements", {"limits": {"max_branches": 9, "max_patients": "unlimited"}},
                   self.tenant.uuid)
        with tenant_context(self.tenant):
            self.assertEqual(get_limit(self.tenant, "max_branches"), 9)
            self.assertIsNone(get_limit(self.tenant, "max_patients"))
        data = self.patch("platform-tenant-entitlements", {"limits": {"max_branches": None}}, self.tenant.uuid).json()
        with tenant_context(self.tenant):
            self.assertEqual(get_limit(self.tenant, "max_branches"), plan_value)
        row = next(r for r in data["limits"] if r["key"] == "max_patients")
        self.assertTrue(row["overridden"])

    def test_subscription_dates_and_status(self):
        data = self.patch("platform-tenant-entitlements", {"ends_on": "2030-01-31"}, self.tenant.uuid).json()
        self.assertEqual(data["subscription"]["ends_on"], "2030-01-31")
        self.assertEqual(self.patch("platform-tenant-entitlements", {"ends_on": "1999-01-01"},
                                    self.tenant.uuid).status_code, 400)


class SupportLoginTests(ControlBase):
    def start(self, **extra):
        return self.post("platform-tenant-support",
                         {"user": str(self.desk.uuid), "minutes": 30, "reason": "مشكلة في الطباعة", **extra},
                         self.tenant.uuid)

    def test_signing_in_as_an_account_is_announced_and_audited(self):
        response = self.start()
        self.assertEqual(response.status_code, 201, response.content)
        session = self.client.get(reverse("api:session")).json()
        self.assertEqual(session["user"]["username"], "desk")
        self.assertEqual(session["support"]["operator_email"], "root@ops.local")
        with tenant_context(self.tenant):
            note = Notification.objects.get(user=self.owner)
        self.assertIn("root@ops.local", note.message)
        self.assertIn("مشكلة في الطباعة", note.message)
        entry = AuditLog.objects.get(tenant=self.tenant, description__contains="support login")
        self.assertEqual(entry.user.username, "root")

    def test_changes_meanwhile_are_marked_as_support(self):
        self.start()
        response = self.client.post(reverse("api:patient-list"), {"name": "Walk In", "phone1": "01000000077"},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 201, response.content)
        entry = AuditLog.objects.filter(tenant=self.tenant, model_name="patient").latest("pk")
        self.assertTrue(entry.description.startswith("[support: root@ops.local]"), entry.description)
        self.assertEqual(entry.user.username, "desk")

    def test_ending_returns_to_the_portal(self):
        self.start()
        data = self.client.post(reverse("api:support-end")).json()
        self.assertEqual(data["redirect"], "/app/platform")
        self.assertEqual(self.client.get(reverse("api:session")).json()["platform_user"]["email"], "root@ops.local")
        self.assertIsNotNone(SupportSession.objects.get().ended_at)

    def test_the_time_limit_signs_the_browser_out(self):
        self.start(minutes=5)
        with mock.patch("platform_admin.impersonation.time.time", return_value=time.time() + 6 * 60):
            session = self.client.get(reverse("api:session")).json()
        self.assertFalse(session["authenticated"])
        self.assertIsNotNone(SupportSession.objects.get().ended_at)

    def test_a_reason_and_a_sane_duration_are_required(self):
        self.assertEqual(self.start(reason="").status_code, 400)
        self.assertEqual(self.start(minutes=600).status_code, 400)
        other = Tenant.objects.create(name="Other", slug="other-ctl", status="active")
        self.assertEqual(self.post("platform-tenant-support", {"user": str(self.desk.uuid), "reason": "x"},
                                   other.uuid).status_code, 404)

    def test_support_staff_cannot_sign_in_as_anyone(self):
        self.client.logout()
        login_platform(self.client, "help@ops.local")
        self.assertEqual(self.start().status_code, 403)
