"""The Admin/Owner's control over the queue ticket and money receipts —
branches/printing.py TICKET_FIELDS, api/views/print_settings.py."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import ClinicRole
from branches.models import Branch
from tenants.context import tenant_context
from tenants.models import Tenant

User = get_user_model()
PASSWORD = "pass12345"


class PrintSettingsTicketTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            self.branch = Branch.all_objects.create(tenant=self.tenant, name="Design Branch", code="DB")
            role = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name="Admin")[0]
        self.admin = User.objects.create_user(
            username="admin-design", email="admin-design@t.local", password=PASSWORD,
            tenant=self.tenant, role=role, branch=self.branch,
        )
        self.client.login(email="admin-design@t.local", password=PASSWORD)

    def url(self):
        return reverse("api:print-settings", args=[self.branch.uuid])

    def patch(self, data):
        return self.client.patch(self.url(), data, content_type="application/json")

    def test_the_settings_screen_gets_what_it_needs_to_render(self):
        data = self.client.get(self.url()).json()
        keys = {row["key"] for row in data["available_ticket_fields"]}
        self.assertEqual(keys, {"branch_contact", "doctor", "checkin_time", "scheduled_time",
                                 "queue_position", "reception_name", "serial_number"})
        self.assertEqual(set(data["effective_ticket_fields"]), keys)  # nothing chosen yet = everything
        self.assertEqual({row["value"] for row in data["paper_widths"]}, {"58mm", "80mm", "a5"})
        self.assertEqual(data["ticket_paper_width"], "80mm")
        self.assertEqual(data["receipt_paper_width"], "80mm")

    def test_choosing_which_ticket_lines_show(self):
        response = self.patch({"ticket_fields": ["doctor", "queue_position"]})
        self.assertEqual(response.status_code, 200, response.content)
        self.branch.refresh_from_db()
        self.assertEqual(self.branch.ticket_fields, ["doctor", "queue_position"])
        data = self.client.get(self.url()).json()
        self.assertEqual(set(data["effective_ticket_fields"]), {"doctor", "queue_position"})

    def test_an_unknown_ticket_field_is_refused(self):
        response = self.patch({"ticket_fields": ["doctor", "not-a-real-field"]})
        self.assertEqual(response.status_code, 400)
        self.assertIn("ticket_fields", response.json())

    def test_paper_width_is_one_of_the_offered_choices(self):
        ok = self.patch({"ticket_paper_width": "58mm", "receipt_paper_width": "a5"})
        self.assertEqual(ok.status_code, 200, ok.content)
        bad = self.patch({"ticket_paper_width": "a4"})
        self.assertEqual(bad.status_code, 400)

    def test_notes_are_saved(self):
        response = self.patch({
            "ticket_note": "برجاء الانتظار حتى يُنادى اسمك",
            "receipt_note": "شكراً لزيارتكم",
        })
        self.assertEqual(response.status_code, 200, response.content)
        self.branch.refresh_from_db()
        self.assertEqual(self.branch.ticket_note, "برجاء الانتظار حتى يُنادى اسمك")
        self.assertEqual(self.branch.receipt_note, "شكراً لزيارتكم")

    def test_a_reception_account_cannot_reach_this_screen(self):
        with tenant_context(self.tenant):
            reception_role = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name="Reception")[0]
        User.objects.create_user(
            username="desk-design", email="desk-design@t.local", password=PASSWORD,
            tenant=self.tenant, role=reception_role, branch=self.branch,
        )
        self.client.logout()
        self.client.login(email="desk-design@t.local", password=PASSWORD)
        self.assertEqual(self.client.get(self.url()).status_code, 403)
