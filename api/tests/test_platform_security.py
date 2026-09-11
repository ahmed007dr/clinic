"""Platform sign-in security (phase 0 of the developer portal).

A platform operator reaches every clinic, so: a password alone opens nothing;
the second step is a code from an authenticator app (or a one-time recovery
code); a session not completed that way is ended whatever door it came in by;
support staff read but never change; and every account's last activity is
kept for "online now".
"""

import time
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts import totp
from accounts.middleware import TWO_FACTOR_KEY
from tenants.models import Tenant

User = get_user_model()
PASSWORD = "pass12345"


class PlatformSecurityTests(TestCase):
    def setUp(self):
        # The sign-in rate limit counts per address across tests.
        cache.clear()
        self.operator = User.objects.create_user(
            username="ops", email="ops@sec.local", password=PASSWORD,
            tenant=None, is_platform_staff=True, platform_role="super",
        )
        self.support = User.objects.create_user(
            username="help", email="help@sec.local", password=PASSWORD,
            tenant=None, is_platform_staff=True, platform_role="support",
        )
        self.tenant = Tenant.objects.first()

    def password_step(self, email="ops@sec.local"):
        return self.client.post(
            reverse("api:login"), {"email": email, "password": PASSWORD}, content_type="application/json"
        )

    def code_step(self, code):
        return self.client.post(reverse("api:two-factor"), {"code": code}, content_type="application/json")

    def enrol(self, email="ops@sec.local"):
        started = self.password_step(email).json()
        return started, self.code_step(totp.code_at(started["secret"]))

    def tenants(self):
        return self.client.get(reverse("api:platform-tenants"))

    # --------------------------------------------------------------- sign-in

    def test_a_password_alone_opens_nothing(self):
        started = self.password_step().json()
        self.assertEqual(started["two_factor"], "enroll")
        self.assertTrue(started["secret"])
        self.assertIn("<svg", started["qr_svg"])
        self.assertEqual(self.tenants().status_code, 403)

    def test_enrolment_completes_with_a_code_and_gives_recovery_codes_once(self):
        self.assertEqual(self.code_step("000000").status_code, 400)  # nothing pending yet
        started = self.password_step().json()
        self.assertEqual(self.code_step("123456").status_code, 400)
        done = self.code_step(totp.code_at(started["secret"]))
        self.assertEqual(done.status_code, 200, done.content)
        self.assertEqual(len(done.json()["recovery_codes"]), totp.RECOVERY_CODES)
        self.assertEqual(self.tenants().status_code, 200)

        self.client.logout()
        self.assertEqual(self.password_step().json(), {"two_factor": "verify"})
        again = self.code_step(totp.code_at(started["secret"]))
        self.assertEqual(again.json()["recovery_codes"], [])

    def test_a_recovery_code_works_once(self):
        _, done = self.enrol()
        code = done.json()["recovery_codes"][0]
        self.client.logout()
        self.password_step()
        self.assertEqual(self.code_step(code).status_code, 200)
        self.client.logout()
        self.password_step()
        self.assertEqual(self.code_step(code).status_code, 400)

    def test_the_pending_step_expires(self):
        self.enrol()
        self.client.logout()
        self.password_step()
        session = self.client.session
        session["platform_2fa_pending"]["at"] = int(time.time()) - 3600
        session.save()
        self.operator.refresh_from_db()
        self.assertEqual(self.code_step(totp.code_at(self.operator.totp_secret)).status_code, 400)

    def test_a_session_without_the_second_step_is_ended_whatever_the_door(self):
        # Django's own login (the older sign-in page takes this route too).
        self.assertTrue(self.client.login(email="ops@sec.local", password=PASSWORD))
        self.assertEqual(self.tenants().status_code, 403)
        self.assertNotIn(TWO_FACTOR_KEY, self.client.session)
        self.assertNotIn("_auth_user_id", self.client.session)

    # ------------------------------------------------------------------ roles

    def test_support_reads_but_never_changes(self):
        self.enrol("help@sec.local")
        self.assertEqual(self.tenants().status_code, 200)
        refused = self.client.post(
            reverse("api:platform-tenant-status", args=[self.tenant.uuid]), {"status": "suspended"},
            content_type="application/json",
        )
        self.assertEqual(refused.status_code, 403)
        self.tenant.refresh_from_db()
        self.assertNotEqual(self.tenant.status, "suspended")

    def test_the_session_reports_the_role(self):
        self.enrol("help@sec.local")
        me = self.client.get(reverse("api:session")).json()["platform_user"]
        self.assertEqual(me["role"], "support")

    # --------------------------------------------------------------- activity

    def test_every_request_keeps_last_seen_fresh(self):
        self.assertIsNone(self.operator.last_seen_at)
        self.enrol()
        self.tenants()
        self.operator.refresh_from_db()
        self.assertIsNotNone(self.operator.last_seen_at)

    # --------------------------------------------------------------- recovery

    def test_a_lost_phone_is_reset_from_the_command_line(self):
        self.enrol()
        call_command("reset_platform_2fa", "ops@sec.local", stdout=StringIO())
        self.operator.refresh_from_db()
        self.assertIsNone(self.operator.totp_confirmed_at)
        self.client.logout()
        self.assertEqual(self.password_step().json()["two_factor"], "enroll")
