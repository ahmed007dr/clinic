"""Marking notifications read: POST actions on an otherwise read-only resource."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import ClinicRole
from branches.models import Branch
from notifications.models import Notification
from tenants.context import tenant_context
from tenants.models import Tenant

User = get_user_model()
PASSWORD = "pass12345"


class NotificationReadTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            branch = Branch.all_objects.create(tenant=self.tenant, name="Nt", code="NT")
            role = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name="Reception")[0]
        self.me = User.objects.create_user(
            username="nt-me", email="nt-me@x.local", password=PASSWORD,
            tenant=self.tenant, role=role, branch=branch,
        )
        self.colleague = User.objects.create_user(
            username="nt-co", email="nt-co@x.local", password=PASSWORD,
            tenant=self.tenant, role=role, branch=branch,
        )
        with tenant_context(self.tenant):
            self.mine = Notification.all_objects.create(
                tenant=self.tenant, user=self.me, title="a", message="a"
            )
            self.mine_too = Notification.all_objects.create(
                tenant=self.tenant, user=self.me, title="b", message="b"
            )
            self.theirs = Notification.all_objects.create(
                tenant=self.tenant, user=self.colleague, title="c", message="c"
            )
        self.client.login(email="nt-me@x.local", password=PASSWORD)

    def is_read(self, notification):
        with tenant_context(self.tenant):
            return Notification.all_objects.get(pk=notification.pk).is_read

    def test_a_user_can_mark_their_notification_read(self):
        response = self.client.post(reverse("api:notification-mark-read", args=[self.mine.uuid]))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(self.is_read(self.mine))

    def test_mark_all_read_touches_only_their_own(self):
        response = self.client.post(reverse("api:notification-mark-all-read"))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(self.is_read(self.mine))
        self.assertTrue(self.is_read(self.mine_too))
        self.assertFalse(self.is_read(self.theirs))

    def test_a_colleagues_notification_is_a_404(self):
        response = self.client.post(reverse("api:notification-mark-read", args=[self.theirs.uuid]))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.is_read(self.theirs))

    def test_a_notification_cannot_be_created_through_the_api(self):
        response = self.client.post(
            reverse("api:notification-list"), {"title": "x", "message": "x"},
            content_type="application/json",
        )
        self.assertIn(response.status_code, (403, 405))
        with tenant_context(self.tenant):
            self.assertFalse(Notification.all_objects.filter(title="x").exists())

    def test_editing_and_deleting_stay_blocked(self):
        url = reverse("api:notification-detail", args=[self.mine.uuid])
        self.assertEqual(self.client.patch(url, {"title": "z"}, content_type="application/json").status_code, 405)
        self.assertEqual(self.client.delete(url).status_code, 405)
