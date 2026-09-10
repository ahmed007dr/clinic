"""The command that creates the owner portal's first account."""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.urls import reverse

from platform_admin.permissions import is_platform_staff

User = get_user_model()


class CreatePlatformAdminTests(TestCase):
    def run_command(self, *args):
        out = StringIO()
        call_command("create_platform_admin", *args, stdout=out)
        return out.getvalue()

    def test_it_creates_an_operator_with_no_clinic(self):
        self.run_command("owner@platform.local", "--password", "pass12345")
        user = User.objects.get(email="owner@platform.local")
        self.assertIsNone(user.tenant_id)
        self.assertTrue(is_platform_staff(user))

    def test_the_generated_password_is_printed_once_and_works(self):
        output = self.run_command("gen@platform.local")
        password = next(
            line.split()[-1] for line in output.splitlines() if line.strip().startswith("password")
        )
        response = self.client.post(
            reverse("api:login"),
            {"email": "gen@platform.local", "password": password},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["platform_user"]["email"], "gen@platform.local")

    def test_an_existing_email_is_refused(self):
        self.run_command("dup@platform.local", "--password", "pass12345")
        with self.assertRaises(CommandError):
            self.run_command("dup@platform.local", "--password", "pass12345")
