"""The security settings a deployment gets by default.

These cannot be checked with `override_settings`: the whole point is what the
*defaults* evaluate to, and they are computed from DEBUG when settings are
imported. Overriding the result would test the override.

So the tests below run `manage.py check --deploy` in a subprocess with a
production-shaped environment and read what Django itself reports. That is
slower than an assertion, and it is the only version of this test that proves
anything — it exercises the real import path with real values.

Real environment variables win over `.env` here, because django-environ's
`read_env` uses `os.environ.setdefault`. That is what makes the subprocess
approach work at all, and it is worth knowing: a stray exported variable
silently overrides the file during local development too.
"""

import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

BASE_DIR = Path(__file__).resolve().parent.parent

# W004 (HSTS) is deliberately absent from this list. HSTS is opt-in per
# deployment because browsers cache it for max-age and it cannot be quickly
# undone — see the comment in project/settings.py. Django reporting W004 is an
# accurate statement about the deployment, not a defect to silence.
EXPECTED_ABSENT = {
    "security.W008",  # SECURE_SSL_REDIRECT
    "security.W012",  # SESSION_COOKIE_SECURE
    "security.W016",  # CSRF_COOKIE_SECURE
    "security.W018",  # DEBUG in deployment
    "security.W020",  # ALLOWED_HOSTS empty
}

PRODUCTION_ENV = {
    "DJANGO_DEBUG": "False",
    "DJANGO_ALLOWED_HOSTS": "clinic.example.com",
    "DJANGO_CSRF_TRUSTED_ORIGINS": "https://clinic.example.com",
    # Required with no default; values are irrelevant to these checks.
    "DJANGO_SECRET_KEY": "test-only-not-a-real-key-0123456789abcdef",
    "EMAIL_HOST": "mail.example.com",
    "EMAIL_HOST_USER": "no-reply@example.com",
    "EMAIL_HOST_PASSWORD": "unused-in-check",
    "DATABASE_URL": "sqlite:///deploy-check-not-used.sqlite3",
}


def run_check(extra_env=None):
    env = {**os.environ, **PRODUCTION_ENV, **(extra_env or {})}
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, "manage.py", "check", "--deploy"],
        cwd=BASE_DIR, env=env, capture_output=True, text=True,
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


class DeploymentSecurityDefaultTests(SimpleTestCase):
    def test_a_production_environment_raises_no_cookie_or_redirect_warnings(self):
        """With DEBUG off and hosts set, the secure defaults must apply without
        anyone having configured them."""
        _, output = run_check()
        for code in sorted(EXPECTED_ABSENT):
            with self.subTest(check=code):
                self.assertNotIn(
                    code, output,
                    f"{code} still reported with a production environment:\n{output}",
                )

    def test_hsts_stays_opt_in(self):
        """Pins the one deliberate omission, so nobody 'fixes' it by defaulting
        HSTS on. If that decision is revisited, this test is where it is
        recorded and must be changed on purpose."""
        _, output = run_check()
        self.assertIn(
            "security.W004", output,
            "HSTS appears to be on by default; it is meant to be enabled per "
            "deployment once HTTPS is confirmed on every subdomain",
        )

    def test_hsts_can_be_switched_on_by_environment(self):
        _, output = run_check({"DJANGO_SECURE_HSTS_SECONDS": "3600"})
        self.assertNotIn("security.W004", output)

    def test_debug_keeps_the_flags_off_for_local_http(self):
        """The other half of the default: a developer on http://localhost must
        not have their session cookie refused by their own browser."""
        _, output = run_check({"DJANGO_DEBUG": "True"})
        # With DEBUG on, Django reports W018 and the cookie warnings again —
        # which is the correct posture for a local HTTP session.
        self.assertIn("security.W018", output)
        self.assertIn("security.W012", output)

    def test_the_proxy_ssl_header_is_not_trusted_unless_asked(self):
        """Trusting X-Forwarded-Proto by default would let a client assert its
        own connection was secure."""
        from django.conf import settings

        self.assertIsNone(getattr(settings, "SECURE_PROXY_SSL_HEADER", None))

    def test_the_proxy_ssl_header_can_be_enabled(self):
        _, output = run_check({"DJANGO_TRUST_PROXY_SSL_HEADER": "True"})
        # It must not introduce new problems; the check output is what matters.
        for code in sorted(EXPECTED_ABSENT):
            with self.subTest(check=code):
                self.assertNotIn(code, output)
