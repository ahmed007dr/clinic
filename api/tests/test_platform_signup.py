"""Developer portal, phase 3: asking to open a clinic group, and the
developer's queue that approves (onboards) or rejects it."""

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from audit.models import AuditLog
from platform_admin.models import CommercialTerms, SignupRequest
from subscriptions.entitlements import current_subscription
from tenants.context import tenant_context
from tenants.models import Tenant
from tenants.testing import login_platform

User = get_user_model()
PASSWORD = "pass12345"

FORM = {
    "group_name": "Smile Group", "clinic_name": "Smile Maadi", "owner_name": "Dr Hany",
    "email": "hany@smile.test", "phone": "01012345678", "city": "Cairo", "plan": "professional",
    "cycle": "yearly", "branches": 2, "doctors": 5, "message": "نريد البدء الشهر القادم",
}


class PublicSignupTests(TestCase):
    def setUp(self):
        cache.clear()
        User.objects.create_user(username="root", email="root@ops.local", password=PASSWORD, tenant=None,
                                 is_platform_staff=True, platform_role="super")

    def submit(self, **changes):
        return self.client.post(reverse("api:signup"), {**FORM, **changes}, content_type="application/json")

    def test_the_public_form_lists_only_offered_plans(self):
        codes = {p["code"] for p in self.client.get(reverse("api:signup-options")).json()["plans"]}
        self.assertIn("professional", codes)

    def test_a_request_is_recorded_and_both_sides_are_told(self):
        self.assertEqual(self.submit().status_code, 201)
        signup = SignupRequest.objects.get()
        self.assertEqual((signup.status, signup.plan.code, signup.cycle, signup.doctors), ("pending", "professional",
                                                                                           "yearly", 5))
        self.assertFalse(Tenant.objects.filter(name="Smile Group").exists())
        recipients = [message.to for message in mail.outbox]
        self.assertIn(["hany@smile.test"], recipients)
        self.assertIn(["root@ops.local"], recipients)

    def test_bad_or_repeated_requests_are_refused(self):
        self.assertEqual(self.submit(email="nope").status_code, 400)
        self.assertEqual(self.submit(group_name="").status_code, 400)
        self.assertEqual(self.submit(plan="no-such-plan").status_code, 400)
        cache.clear()  # five an hour from one address
        self.submit()
        self.assertEqual(self.submit().status_code, 400)  # one pending request per email
        self.assertEqual(self.submit(email="root@ops.local").status_code, 400)  # already an account

    def test_one_address_is_limited_to_a_few_requests_an_hour(self):
        for n in range(5):
            self.submit(email=f"x{n}@smile.test")
        self.assertEqual(self.submit(email="x9@smile.test").status_code, 429)

    def test_a_bot_filling_the_hidden_field_is_quietly_dropped(self):
        self.assertEqual(self.submit(website="http://spam.test").status_code, 201)
        self.assertFalse(SignupRequest.objects.exists())


class SignupQueueTests(TestCase):
    def setUp(self):
        cache.clear()
        User.objects.create_user(username="root", email="root@ops.local", password=PASSWORD, tenant=None,
                                 is_platform_staff=True, platform_role="super")
        User.objects.create_user(username="help", email="help@ops.local", password=PASSWORD, tenant=None,
                                 is_platform_staff=True, platform_role="support")
        self.client.post(reverse("api:signup"), FORM, content_type="application/json")
        self.signup = SignupRequest.objects.get()
        login_platform(self.client, "root@ops.local")
        mail.outbox.clear()

    def test_the_queue_counts_by_status(self):
        data = self.client.get(reverse("api:platform-signups"), {"status": "pending"}).json()
        self.assertEqual(data["counts"]["pending"], 1)
        self.assertEqual(data["items"][0]["email"], "hany@smile.test")

    def test_approving_onboards_the_group_on_the_requested_terms(self):
        response = self.client.post(reverse("api:platform-signup-approve", args=[self.signup.pk]),
                                    {"slug": "smile"}, content_type="application/json")
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertTrue(body["admin_password"])
        self.assertTrue(body["emailed"])
        tenant = Tenant.objects.get(slug="smile")
        owner = User.objects.get(email="hany@smile.test")
        self.assertEqual((owner.tenant, owner.role.name), (tenant, "Owner"))
        self.assertTrue(owner.check_password(body["admin_password"]))
        with tenant_context(tenant):
            self.assertEqual(current_subscription(tenant).plan.code, "professional")
        self.assertEqual(CommercialTerms.objects.get(customer=tenant).cycle, "yearly")
        self.signup.refresh_from_db()
        self.assertEqual((self.signup.status, self.signup.tenant), ("approved", tenant))
        self.assertIn(body["admin_password"], mail.outbox[0].body)
        self.assertTrue(AuditLog.objects.filter(tenant=tenant, description__contains="signup approved").exists())
        again = self.client.post(reverse("api:platform-signup-approve", args=[self.signup.pk]),
                                 {"slug": "smile-2"}, content_type="application/json")
        self.assertEqual(again.status_code, 400)

    def test_an_arabic_name_needs_a_latin_slug(self):
        self.signup.group_name = "مجموعة الابتسامة"
        self.signup.save()
        response = self.client.post(reverse("api:platform-signup-approve", args=[self.signup.pk]), {},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("slug", response.json())
        self.signup.refresh_from_db()
        self.assertEqual(self.signup.status, "pending")

    def test_rejecting_needs_a_reason_and_tells_the_applicant(self):
        url = reverse("api:platform-signup-reject", args=[self.signup.pk])
        self.assertEqual(self.client.post(url, {}, content_type="application/json").status_code, 400)
        data = self.client.post(url, {"reason": "المنطقة غير مغطاة"}, content_type="application/json").json()
        self.assertEqual(data["status"], "rejected")
        self.assertIn("المنطقة غير مغطاة", mail.outbox[0].body)

    def test_support_staff_see_the_queue_but_cannot_decide(self):
        self.client.logout()
        login_platform(self.client, "help@ops.local")
        self.assertEqual(self.client.get(reverse("api:platform-signups")).status_code, 200)
        response = self.client.post(reverse("api:platform-signup-approve", args=[self.signup.pk]),
                                    {"slug": "smile"}, content_type="application/json")
        self.assertEqual(response.status_code, 403)
