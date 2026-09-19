"""The owner's email settings and the email log.

Settings: the Owner sets a default for the group and may override one clinic;
the clinic's own wins, then the group's; secrets never come back; nobody but
the Owner reaches it, and never another group's clinic.

Log: everything sent for a clinic is recorded, filterable, scoped to the
viewer — and a message carrying a credential is stored without it.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import ClinicRole
from branches.models import Branch
from notifications.maillog import deliver
from notifications.models import EmailLog
from platform_admin import vault
from platform_admin.mailer import sender_for
from platform_admin.models import IntegrationCredential
from tenants.context import tenant_context
from tenants.models import Tenant
from tenants.testing import login_platform

User = get_user_model()
PASSWORD = "pass12345"
Kind = IntegrationCredential.Kind
Scope = IntegrationCredential.Scope

SMTP = {"host": "mail.group.example", "port": 465, "username": "group@group.example",
        "password": "GROUP-SECRET-1234", "from_email": "group@group.example", "use_ssl": True}
CLINIC_SMTP = {**SMTP, "host": "mail.clinic.example", "username": "b@group.example",
               "password": "CLINIC-SECRET-5678", "from_email": "b@group.example"}


@override_settings(DEBUG=True)  # the public-address check is exempt in development
class OwnerEmailSettingsTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            roles = {n: ClinicRole.all_objects.get_or_create(tenant=self.tenant, name=n)[0]
                     for n in ("Owner", "Admin")}
            self.a = Branch.all_objects.create(tenant=self.tenant, name="Clinic A", code="EA")
            self.b = Branch.all_objects.create(tenant=self.tenant, name="Clinic B", code="EB")
        self.other = Tenant.objects.create(name="Other", slug="other-mail", status="active")
        with tenant_context(self.other):
            self.theirs = Branch.all_objects.create(tenant=self.other, name="Theirs", code="TH")
        User.objects.create_user(username="owner", email="owner@mail.local", password=PASSWORD,
                                 tenant=self.tenant, role=roles["Owner"], branch=self.a)
        User.objects.create_user(username="admin", email="admin@mail.local", password=PASSWORD,
                                 tenant=self.tenant, role=roles["Admin"], branch=self.a)
        self.client.login(email="owner@mail.local", password=PASSWORD)

    def put(self, target, data):
        return self.client.put(reverse("api:owner-email-target", args=[target]), data, content_type="application/json")

    def test_owner_sets_a_group_default_and_secrets_stay_hidden(self):
        response = self.put("group", SMTP)
        self.assertEqual(response.status_code, 201, response.content)
        listing = self.client.get(reverse("api:owner-email")).json()
        self.assertEqual(listing["group"]["values"]["host"], "mail.group.example")
        self.assertTrue(listing["group"]["values"]["password"]["set"])
        self.assertNotIn("GROUP-SECRET-1234", str(listing))
        self.assertNotIn("GROUP-SECRET-1234", response.content.decode())

    def test_group_default_reaches_every_clinic_and_a_clinic_override_wins(self):
        self.put("group", SMTP)
        self.assertEqual(sender_for(branch=self.a)[1], "group@group.example")
        self.assertEqual(sender_for(branch=self.b)[1], "group@group.example")

        self.assertEqual(self.put(str(self.b.pk), CLINIC_SMTP).status_code, 201)
        self.assertEqual(sender_for(branch=self.b)[1], "b@group.example")
        self.assertEqual(sender_for(branch=self.a)[1], "group@group.example")

        rows = {b["name"]: b["source"] for b in self.client.get(reverse("api:owner-email")).json()["branches"]}
        self.assertEqual(rows, {**rows, "Clinic A": "group", "Clinic B": "clinic"})

    def test_removing_a_clinics_settings_falls_back_to_the_group(self):
        self.put("group", SMTP)
        self.put(str(self.b.pk), CLINIC_SMTP)
        self.assertEqual(self.client.delete(reverse("api:owner-email-target", args=[str(self.b.pk)])).status_code, 204)
        self.assertEqual(sender_for(branch=self.b)[1], "group@group.example")

    def test_a_blank_password_keeps_the_saved_one(self):
        self.put("group", SMTP)
        self.put("group", {**SMTP, "password": "", "host": "mail.new.example"})
        credential = IntegrationCredential.objects.get(kind=Kind.SMTP, scope=Scope.GROUP, customer=self.tenant)
        live = vault.config_of(credential)
        self.assertEqual(live["password"], "GROUP-SECRET-1234")
        self.assertEqual(live["host"], "mail.new.example")

    def test_a_disabled_setting_is_not_used(self):
        self.put("group", {**SMTP, "enabled": False})
        self.assertFalse(IntegrationCredential.objects.get(kind=Kind.SMTP, customer=self.tenant).enabled)
        self.assertNotEqual(sender_for(branch=self.a)[1], "group@group.example")

    def test_incomplete_or_contradictory_settings_are_refused(self):
        self.assertEqual(self.put("group", {**SMTP, "host": ""}).status_code, 400)
        self.assertEqual(self.put("group", {**SMTP, "use_tls": True, "use_ssl": True}).status_code, 400)
        self.assertEqual(self.put("group", {**SMTP, "from_email": "not-an-address"}).status_code, 400)
        self.assertEqual(self.put("group", {**SMTP, "port": "99999"}).status_code, 400)

    @override_settings(DEBUG=False)
    def test_a_private_or_local_mail_server_is_refused_in_production(self):
        for host in ("127.0.0.1", "10.0.0.5", "169.254.169.254"):
            response = self.put("group", {**SMTP, "host": host})
            self.assertEqual(response.status_code, 400, host)

    def test_only_the_owner_reaches_it(self):
        self.client.logout()
        self.client.login(email="admin@mail.local", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("api:owner-email")).status_code, 403)
        self.assertEqual(self.put("group", SMTP).status_code, 403)

    def test_another_groups_clinic_is_not_reachable(self):
        self.assertEqual(self.put(str(self.theirs.pk), SMTP).status_code, 404)
        self.assertFalse(IntegrationCredential.objects.filter(kind=Kind.SMTP).exists())

    def test_the_connection_test_reports_success_and_failure(self):
        url = reverse("api:owner-email-test", args=["group"])
        with mock.patch("platform_admin.checks.get_connection") as connect:
            ok = self.client.post(url, SMTP, content_type="application/json").json()
        self.assertTrue(ok["ok"])
        connect.assert_called_once()
        with mock.patch("platform_admin.checks.get_connection", side_effect=OSError("boom PASSWORD")):
            bad = self.client.post(url, SMTP, content_type="application/json").json()
        self.assertFalse(bad["ok"])
        self.assertNotIn("PASSWORD", bad["detail"])

    def test_changes_are_audited_without_values(self):
        from audit.models import AuditLog

        self.put("group", SMTP)
        entry = AuditLog.objects.filter(model_name="IntegrationCredential").latest("id")
        self.assertIn("[owner]", entry.description)
        self.assertNotIn("SECRET", entry.description)

    def apply(self):
        return self.client.post(reverse("api:owner-email-apply-default"))

    def test_every_clinic_ends_up_on_the_group_default(self):
        self.put("group", SMTP)
        self.put(str(self.a.pk), CLINIC_SMTP)
        self.put(str(self.b.pk), CLINIC_SMTP)
        response = self.apply()
        self.assertEqual(response.json(), {"cleared": 2})
        self.assertEqual(sender_for(branch=self.a)[1], "group@group.example")
        self.assertEqual(sender_for(branch=self.b)[1], "group@group.example")
        self.assertEqual(IntegrationCredential.objects.filter(scope=Scope.CLINIC).count(), 0)

    def test_it_is_refused_when_the_default_cannot_send(self):
        self.put(str(self.a.pk), CLINIC_SMTP)
        self.assertEqual(self.apply().status_code, 400)
        self.assertEqual(IntegrationCredential.objects.filter(scope=Scope.CLINIC).count(), 1)

    def test_another_groups_settings_are_untouched(self):
        self.put("group", SMTP)
        theirs = IntegrationCredential.objects.create(
            kind=Kind.SMTP, scope=Scope.CLINIC, customer=self.other, branch=self.theirs,
            mode="production", production_config=vault.seal(CLINIC_SMTP),
        )
        self.apply()
        self.assertTrue(IntegrationCredential.objects.filter(pk=theirs.pk).exists())

    def test_an_admin_cannot_do_it(self):
        self.put("group", SMTP)
        self.client.logout()
        self.client.login(email="admin@mail.local", password=PASSWORD)
        self.assertEqual(self.apply().status_code, 403)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class EmailLogTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            roles = {n: ClinicRole.all_objects.get_or_create(tenant=self.tenant, name=n)[0]
                     for n in ("Owner", "Admin", "Doctor")}
            self.a = Branch.all_objects.create(tenant=self.tenant, name="Clinic A", code="LA")
            self.b = Branch.all_objects.create(tenant=self.tenant, name="Clinic B", code="LB")
        self.other = Tenant.objects.create(name="Other", slug="other-log", status="active")
        for name, role, branch in (("owner", "Owner", self.a), ("admin_a", "Admin", self.a),
                                   ("doctor", "Doctor", self.a)):
            User.objects.create_user(username=name, email=f"{name}@log.local", password=PASSWORD,
                                     tenant=self.tenant, role=roles[role], branch=branch)
        connection = mail.get_connection()
        self.send = lambda **kw: deliver(connection=connection, sender="clinic@x.example", tenant=self.tenant,
                                         **{"kind": "daily_report", "to": "boss@x.example",
                                            "subject": "s", "body": "b", **kw})
        # Re-sending resolves the mail server itself; stand a real (locmem) one in.
        from django.core.cache import cache

        cache.clear()
        patcher = mock.patch("api.views.email_log.sender_for",
                             side_effect=lambda **kw: (mail.get_connection(), "clinic@x.example"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def rows(self, **params):
        return self.client.get(reverse("api:email-log"), params).json()

    def test_a_sent_message_is_logged_and_really_sent(self):
        self.assertTrue(self.send(branch=self.a, subject="Daily A", body="<p>hi</p>", html=True,
                                  template="reports/daily_report.html"))
        self.assertEqual(len(mail.outbox), 1)
        entry = EmailLog.all_objects.get()
        self.assertEqual((entry.kind, entry.to_address, entry.status), ("daily_report", "boss@x.example", "sent"))
        self.assertEqual(entry.template, "reports/daily_report.html")

    def test_a_failure_is_logged_and_never_raised(self):
        connection = mock.Mock()
        connection.send_messages.side_effect = OSError("smtp down, password=hunter2")
        self.assertFalse(deliver(kind="daily_report", tenant=self.tenant, to="a@x.example", subject="s",
                                 body="b", connection=connection, sender="c@x.example"))
        entry = EmailLog.all_objects.get()
        self.assertEqual((entry.status, entry.error), ("failed", "OSError"))
        self.assertNotIn("hunter2", entry.error)

    def test_nothing_is_logged_when_no_mail_server_exists(self):
        self.assertFalse(deliver(kind="daily_report", tenant=self.tenant, to="a@x.example", subject="s",
                                 body="b", connection=None, sender=None))
        self.assertEqual(EmailLog.all_objects.count(), 0)

    def test_one_row_per_recipient_so_the_address_filter_finds_it(self):
        self.send(to=["one@x.example", "two@x.example"], branch=self.a)
        self.client.login(email="owner@log.local", password=PASSWORD)
        self.assertEqual(self.rows(q="two@")["count"], 1)

    def test_owner_sees_the_group_and_an_admin_only_their_clinic(self):
        self.send(branch=self.a, subject="A mail")
        self.send(branch=self.b, subject="B mail")
        self.client.login(email="owner@log.local", password=PASSWORD)
        self.assertEqual(self.rows()["count"], 2)
        self.client.logout()
        self.client.login(email="admin_a@log.local", password=PASSWORD)
        subjects = [r["subject"] for r in self.rows()["results"]]
        self.assertEqual(subjects, ["A mail"])

    def test_filters_and_counts_per_kind(self):
        self.send(branch=self.a, kind="daily_report", to="x@x.example")
        self.send(branch=self.a, kind="personal_report", to="y@x.example")
        self.send(branch=self.a, kind="personal_report", to="z@x.example")
        self.client.login(email="owner@log.local", password=PASSWORD)
        data = self.rows(kind="personal_report")
        self.assertEqual(data["count"], 2)
        counts = {k["kind"]: k["count"] for k in data["by_kind"]}
        self.assertEqual((counts["daily_report"], counts["personal_report"]), (1, 2))
        self.assertEqual(self.rows(q="y@x")["count"], 1)
        self.assertEqual(self.rows(status="failed")["count"], 0)

    def test_detail_shows_the_body_and_template_but_the_list_does_not(self):
        self.send(branch=self.a, body="<p>Revenue 100</p>", html=True, template="reports/daily_report.html")
        self.client.login(email="owner@log.local", password=PASSWORD)
        row = self.rows()["results"][0]
        self.assertNotIn("body", row)
        detail = self.client.get(reverse("api:email-log-detail", args=[row["id"]])).json()
        self.assertEqual(detail["body"], "<p>Revenue 100</p>")
        self.assertTrue(detail["is_html"])
        self.assertEqual(detail["template"], "reports/daily_report.html")

    def test_an_admin_cannot_open_another_clinics_message(self):
        self.send(branch=self.b)
        entry = EmailLog.all_objects.get()
        self.client.login(email="admin_a@log.local", password=PASSWORD)
        response = self.client.get(reverse("api:email-log-detail", args=[str(entry.uuid)]))
        self.assertEqual(response.status_code, 404)

    def test_a_doctor_cannot_read_the_log(self):
        self.client.login(email="doctor@log.local", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("api:email-log")).status_code, 403)

    def test_another_groups_log_never_appears(self):
        deliver(kind="daily_report", tenant=self.other, to="secret@other.example", subject="Other secret",
                body="b", connection=mail.get_connection(), sender="x@y.example")
        self.client.login(email="owner@log.local", password=PASSWORD)
        self.assertNotIn("Other secret", str(self.rows()))

    def test_credentials_are_never_stored(self):
        from portal import mail as portal_mail
        from patients.models import Patient

        with tenant_context(self.tenant):
            patient = Patient.all_objects.create(tenant=self.tenant, name="P", branch=self.a, email="p@x.example")
        with mock.patch("platform_admin.mailer.sender_for", return_value=(mail.get_connection(), "c@x.example")):
            portal_mail.send_invitation(self.tenant, patient, "https://x.example/app/portal/invite/SECRETTOKEN", 72)
            portal_mail.send_login_codes(self.tenant, "p@x.example", [(patient, "482913")])
        stored = " ".join(EmailLog.all_objects.values_list("body", flat=True))
        self.assertNotIn("SECRETTOKEN", stored)
        self.assertNotIn("482913", stored)
        # ...while the recipient did get them.
        sent = " ".join(m.body for m in mail.outbox)
        self.assertIn("SECRETTOKEN", sent)
        self.assertIn("482913", sent)

    def test_platform_support_can_read_a_groups_log_and_it_is_audited(self):
        from audit.models import AuditLog

        self.send(branch=self.a, subject="For support")
        User.objects.create_user(username="help", email="help@ops.local", password=PASSWORD, tenant=None,
                                 is_platform_staff=True, platform_role="support")
        login_platform(self.client, "help@ops.local")
        response = self.client.get(reverse("api:platform-email-log", args=[str(self.tenant.uuid)]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["subject"], "For support")
        self.assertTrue(AuditLog.objects.filter(tenant=self.tenant, description__contains="email log").exists())

    def first(self):
        return EmailLog.all_objects.filter(resent_from__isnull=True).latest("id")

    def resend(self, entry):
        return self.client.post(reverse("api:email-log-resend", args=[str(entry.uuid)]))

    def test_a_report_can_be_sent_again_unchanged_and_again(self):
        self.send(branch=self.a, subject="Daily A", body="<p>Revenue 100</p>", html=True,
                  template="reports/daily_report.html")
        entry = self.first()
        self.client.login(email="admin_a@log.local", password=PASSWORD)
        outbox_before = len(mail.outbox)

        response = self.resend(entry)
        self.assertEqual(response.status_code, 200, response.content)
        sent = mail.outbox[outbox_before]
        self.assertEqual((sent.subject, sent.body, sent.to), ("Daily A", "<p>Revenue 100</p>", ["boss@x.example"]))
        self.assertEqual(sent.content_subtype, "html")

        from django.core.cache import cache
        cache.clear()  # skip the cooldown
        self.assertEqual(self.resend(entry).status_code, 200)

        history = self.client.get(reverse("api:email-log-detail", args=[str(entry.uuid)])).json()["history"]
        self.assertEqual([h["is_resend"] for h in history], [False, True, True])
        self.assertEqual(EmailLog.all_objects.filter(resent_from=entry).count(), 2)

    def test_the_history_is_the_same_from_a_resend_and_from_the_original(self):
        self.send(branch=self.a)
        entry = self.first()
        self.client.login(email="admin_a@log.local", password=PASSWORD)
        self.resend(entry)
        again = EmailLog.all_objects.get(resent_from=entry)
        history = self.client.get(reverse("api:email-log-detail", args=[str(again.uuid)])).json()["history"]
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["id"], str(entry.uuid))

    def test_a_second_click_within_the_cooldown_is_refused(self):
        self.send(branch=self.a)
        self.client.login(email="admin_a@log.local", password=PASSWORD)
        entry = self.first()
        self.assertEqual(self.resend(entry).status_code, 200)
        self.assertEqual(self.resend(entry).status_code, 429)

    def test_a_failed_message_can_be_sent_again(self):
        broken = mock.Mock()
        broken.send_messages.side_effect = OSError("down")
        deliver(kind="daily_report", tenant=self.tenant, branch=self.a, to="boss@x.example", subject="s",
                body="b", connection=broken, sender="c@x.example")
        entry = self.first()
        self.assertEqual(entry.status, "failed")
        self.client.login(email="admin_a@log.local", password=PASSWORD)
        self.assertEqual(self.resend(entry).status_code, 200)
        self.assertEqual(EmailLog.all_objects.get(resent_from=entry).status, "sent")

    def test_credential_messages_cannot_be_resent(self):
        self.send(branch=self.a, kind="portal_invitation", body="[masked]")
        entry = self.first()
        self.client.login(email="admin_a@log.local", password=PASSWORD)
        response = self.resend(entry)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.client.get(reverse("api:email-log-detail", args=[str(entry.uuid)])).json()["resendable"])

    def test_an_admin_cannot_resend_another_clinics_message(self):
        self.send(branch=self.b)
        self.client.login(email="admin_a@log.local", password=PASSWORD)
        self.assertEqual(self.resend(self.first()).status_code, 404)

    def test_the_owner_can_resend_any_clinics_message(self):
        self.send(branch=self.b)
        self.client.login(email="owner@log.local", password=PASSWORD)
        self.assertEqual(self.resend(self.first()).status_code, 200)

    def test_a_doctor_cannot_resend(self):
        self.send(branch=self.a)
        self.client.login(email="doctor@log.local", password=PASSWORD)
        self.assertEqual(self.resend(self.first()).status_code, 403)

    def test_nothing_is_sent_when_no_mail_server_exists(self):
        self.send(branch=self.a)
        self.client.login(email="admin_a@log.local", password=PASSWORD)
        with mock.patch("api.views.email_log.sender_for", return_value=(None, None)):
            self.assertEqual(self.resend(self.first()).status_code, 503)

    def test_resending_is_audited(self):
        from audit.models import AuditLog

        self.send(branch=self.a)
        self.client.login(email="admin_a@log.local", password=PASSWORD)
        self.resend(self.first())
        self.assertTrue(AuditLog.objects.filter(description__startswith="email re-sent").exists())

    def test_the_owner_can_filter_by_clinic(self):
        self.send(branch=self.a, subject="A")
        self.send(branch=self.b, subject="B")
        self.client.login(email="owner@log.local", password=PASSWORD)
        self.assertEqual([r["subject"] for r in self.rows(branch=self.b.pk)["results"]], ["B"])
        self.assertEqual(self.client.get(reverse("api:email-log"), {"branch": "x"}).status_code, 400)
