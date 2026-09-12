"""Developer portal, phase 2: keys and passwords (test and production, per
platform / group / clinic), mailboxes, subscription billing, plans, and online
payments — the platform's for subscriptions, each clinic's own for patients.
"""

import json
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from appointments.models import Appointment
from audit.models import AuditLog
from billing.models import Payment
from branches.models import Branch
from patients.models import Patient
from platform_admin import billing, vault
from platform_admin.gateways import paymob_signature
from platform_admin.mailer import sender_for
from platform_admin.models import (
    ClinicCheckout,
    CommercialTerms,
    Discount,
    IntegrationCredential,
    Mailbox,
    PlatformInvoice,
    PlatformPayment,
)
from portal.models import PortalInvitation
from subscriptions.models import Plan, Subscription
from tenants.context import tenant_context
from tenants.models import Tenant
from tenants.testing import login_platform

User = get_user_model()
PASSWORD = "pass12345"
Kind = IntegrationCredential.Kind
Scope = IntegrationCredential.Scope

PAYMOB = {"api_key": "pk_live_SECRET_1234", "card_integration_id": "11", "iframe_id": "22",
          "hmac_secret": "HMACSECRET9876"}


def make_group(slug, plan="professional"):
    tenant = Tenant.objects.create(name=slug.title(), slug=slug, status="active")
    with tenant_context(tenant):
        branch = Branch.all_objects.create(tenant=tenant, name=f"{slug} main", code=slug[:4].upper())
        Subscription.all_objects.create(tenant=tenant, plan=Plan.objects.get(code=plan), status="active")
    return tenant, branch


def credential(kind, scope, config, customer=None, branch=None, mode="production", enabled=True):
    return IntegrationCredential.objects.create(
        kind=kind, scope=scope, customer=customer, branch=branch, mode=mode, enabled=enabled,
        test_config=vault.seal(config), production_config=vault.seal(config),
    )


def paymob_transaction(reference, amount_cents, success=True, **extra):
    return {
        "amount_cents": amount_cents, "created_at": "2026-09-11T10:00:00", "currency": "EGP",
        "error_occured": False, "has_parent_transaction": False, "id": 555, "integration_id": 11,
        "is_3d_secure": True, "is_auth": False, "is_capture": False, "is_refunded": False,
        "is_standalone_payment": True, "is_voided": False,
        "order": {"id": 9, "merchant_order_id": reference}, "owner": 1, "pending": False,
        "source_data": {"pan": "2346", "sub_type": "MasterCard", "type": "card"}, "success": success, **extra,
    }


class OperatorsMixin:
    def setUp(self):
        cache.clear()
        User.objects.create_user(
            username="root", email="root@ops.local", password=PASSWORD, tenant=None,
            is_platform_staff=True, platform_role="super",
        )
        User.objects.create_user(
            username="help", email="help@ops.local", password=PASSWORD, tenant=None,
            is_platform_staff=True, platform_role="support",
        )
        login_platform(self.client, "root@ops.local")

    def as_support(self):
        self.client.logout()
        login_platform(self.client, "help@ops.local")

    def post(self, name, data, *args, method="post"):
        return getattr(self.client, method)(
            reverse(f"api:{name}", args=args), data, content_type="application/json"
        )


# ====================================================================== vault


class VaultTests(TestCase):
    def test_secrets_are_encrypted_at_rest(self):
        sealed = vault.seal(PAYMOB)
        self.assertNotIn("SECRET", sealed)
        self.assertEqual(vault.unseal(sealed), PAYMOB)

    def test_the_browser_sees_only_whether_a_secret_is_set_and_its_last_four(self):
        shown = vault.masked(Kind.PAYMOB, PAYMOB)
        self.assertEqual(shown["api_key"], {"set": True, "hint": "…1234"})
        self.assertEqual(shown["iframe_id"], "22")
        self.assertNotIn("SECRET", json.dumps(shown))

    def test_a_secret_left_blank_keeps_the_stored_one(self):
        cleaned = vault.clean(Kind.PAYMOB, {**PAYMOB, "api_key": "", "iframe_id": "33"}, PAYMOB)
        self.assertEqual(cleaned["api_key"], PAYMOB["api_key"])
        self.assertEqual(cleaned["iframe_id"], "33")

    def test_the_most_specific_enabled_credential_wins(self):
        tenant, branch = make_group("resolve-a")
        credential(Kind.PAYMOB, Scope.PLATFORM, {**PAYMOB, "iframe_id": "platform"})
        credential(Kind.PAYMOB, Scope.GROUP, {**PAYMOB, "iframe_id": "group"}, customer=tenant)
        clinic = credential(Kind.PAYMOB, Scope.CLINIC, {**PAYMOB, "iframe_id": "clinic"},
                            customer=tenant, branch=branch)
        self.assertEqual(vault.resolve(Kind.PAYMOB, branch=branch)[0]["iframe_id"], "clinic")
        clinic.enabled = False
        clinic.save()
        self.assertEqual(vault.resolve(Kind.PAYMOB, branch=branch)[0]["iframe_id"], "group")
        self.assertEqual(vault.resolve(Kind.PAYMOB)[0]["iframe_id"], "platform")

    def test_a_clinic_collecting_from_patients_never_falls_back_to_the_platform(self):
        _, branch = make_group("resolve-b")
        credential(Kind.PAYMOB, Scope.PLATFORM, PAYMOB)
        self.assertIsNone(vault.resolve(Kind.PAYMOB, branch=branch, include_platform=False))

    def test_the_live_environment_is_the_one_the_mode_names(self):
        row = IntegrationCredential.objects.create(
            kind=Kind.FAWRY, scope=Scope.PLATFORM, mode="test",
            test_config=vault.seal({"merchant_code": "TEST", "security_key": "k"}),
            production_config=vault.seal({"merchant_code": "LIVE", "security_key": "k"}),
        )
        self.assertEqual(vault.resolve(Kind.FAWRY)[0]["merchant_code"], "TEST")
        row.mode = "production"
        row.save()
        self.assertEqual(vault.resolve(Kind.FAWRY)[0]["merchant_code"], "LIVE")

    def test_a_clinics_mail_goes_out_through_its_own_server(self):
        tenant, branch = make_group("mail-a")
        credential(Kind.SMTP, Scope.CLINIC, {
            "host": "mail.clinic.test", "port": "465", "username": "c@clinic.test", "password": "pw",
            "from_email": "c@clinic.test", "use_ssl": True, "use_tls": False,
        }, customer=tenant, branch=branch)
        connection, sender = sender_for(branch=branch)
        self.assertEqual((connection.host, sender), ("mail.clinic.test", "c@clinic.test"))


# ====================================================================== integrations API


class IntegrationApiTests(OperatorsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.tenant, self.branch = make_group("keys-a")

    def add_group_paymob(self, **extra):
        return self.post("platform-integrations", {
            "kind": "paymob", "scope": "group", "customer": str(self.tenant.uuid),
            "mode": "test", "test": PAYMOB, "production": {**PAYMOB, "api_key": "pk_prod_OTHER_5678"}, **extra,
        })

    def test_keys_go_in_encrypted_and_come_back_masked(self):
        response = self.add_group_paymob()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertNotIn("SECRET", response.content.decode())
        self.assertNotIn("OTHER", response.content.decode())
        body = response.json()
        self.assertEqual(body["test"]["api_key"], {"set": True, "hint": "…1234"})
        self.assertEqual(body["production"]["api_key"]["hint"], "…5678")
        row = IntegrationCredential.objects.get(pk=body["id"])
        self.assertNotIn("SECRET", row.test_config + row.production_config)
        listing = self.client.get(reverse("api:platform-integrations")).content.decode()
        self.assertNotIn("SECRET", listing)
        self.assertIn("/api/pay/paymob/callback/", listing)

    def test_each_scope_gets_its_own_keys_and_saving_again_replaces_them(self):
        first = self.add_group_paymob().json()
        again = self.add_group_paymob(test={**PAYMOB, "api_key": "", "iframe_id": "99"}).json()
        self.assertEqual(first["id"], again["id"])
        self.assertEqual(again["test"]["iframe_id"], "99")
        self.assertEqual(again["test"]["api_key"]["hint"], "…1234")
        clinic = self.post("platform-integrations", {
            "kind": "paymob", "scope": "clinic", "customer": str(self.tenant.uuid), "branch": self.branch.pk,
            "test": PAYMOB,
        })
        self.assertEqual(clinic.status_code, 201, clinic.content)
        self.assertEqual(IntegrationCredential.objects.filter(kind="paymob").count(), 2)

    def test_production_cannot_go_live_with_missing_keys(self):
        response = self.post("platform-integrations", {
            "kind": "paymob", "scope": "group", "customer": str(self.tenant.uuid),
            "mode": "production", "test": PAYMOB, "production": {"api_key": "x"},
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("ناقصة", response.json()["detail"])

    def test_an_integration_is_only_set_where_it_belongs(self):
        response = self.post("platform-integrations", {
            "kind": "cpanel", "scope": "group", "customer": str(self.tenant.uuid), "test": {},
        })
        self.assertEqual(response.status_code, 400)

    def test_switching_environment_and_turning_off(self):
        pk = self.add_group_paymob().json()["id"]
        response = self.post("platform-integration", {"mode": "production"}, pk, method="patch")
        self.assertEqual(response.json()["mode"], "production")
        response = self.post("platform-integration", {"enabled": False}, pk, method="patch")
        self.assertFalse(response.json()["enabled"])
        self.assertIsNone(vault.resolve(Kind.PAYMOB, customer=self.tenant))

    def test_changes_are_audited_without_the_values(self):
        self.add_group_paymob()
        entry = AuditLog.objects.filter(tenant=self.tenant, description__contains="integration").get()
        self.assertIn("paymob", entry.description)
        self.assertNotIn("SECRET", entry.description)

    def test_support_staff_can_look_and_test_but_not_change(self):
        pk = self.add_group_paymob().json()["id"]
        self.as_support()
        self.assertEqual(self.client.get(reverse("api:platform-integrations")).status_code, 200)
        self.assertEqual(self.add_group_paymob().status_code, 403)
        self.assertEqual(self.post("platform-integration", {"enabled": False}, pk, method="patch").status_code, 403)
        with mock.patch("platform_admin.checks._request", return_value={"token": "t"}):
            result = self.post("platform-integration-test", {"mode": "test"}, pk)
        self.assertTrue(result.json()["ok"])

    def test_the_connection_check_reports_a_bad_key(self):
        pk = self.add_group_paymob().json()["id"]
        with mock.patch("platform_admin.checks._request", return_value={}):
            result = self.post("platform-integration-test", {"mode": "production"}, pk).json()
        self.assertFalse(result["ok"])

    def test_clinic_staff_cannot_reach_any_of_it(self):
        with tenant_context(self.tenant):
            role = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name="Owner")[0]
        User.objects.create_user(username="own", email="own@k.local", password=PASSWORD, tenant=self.tenant,
                                 role=role, branch=self.branch)
        self.client.logout()
        self.client.login(email="own@k.local", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("api:platform-integrations")).status_code, 403)


# ====================================================================== mailboxes


class MailboxTests(OperatorsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.tenant, self.branch = make_group("mbox-a")
        credential(Kind.CPANEL, Scope.PLATFORM, {
            "host": "https://server:2083", "username": "acct", "api_token": "TOKEN", "domain": "clinics.test",
        })

    def test_a_mailbox_for_a_clinic_becomes_its_sender(self):
        with mock.patch("platform_admin.mailboxes._call") as call:
            response = self.post("platform-mailboxes", {
                "customer": str(self.tenant.uuid), "branch": self.branch.pk, "local_part": "Nile.Main",
            })
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["address"], "nile.main@clinics.test")
        self.assertTrue(body["password"])
        self.assertEqual(call.call_args.args[1], "add_pop")
        connection, sender = sender_for(branch=self.branch)
        self.assertEqual((connection.host, sender), ("mail.clinics.test", "nile.main@clinics.test"))
        listed = self.client.get(reverse("api:platform-mailboxes")).json()
        self.assertNotIn("password", listed["items"][0])

    def test_bad_names_and_duplicates_are_refused(self):
        with mock.patch("platform_admin.mailboxes._call"):
            self.assertEqual(self.post("platform-mailboxes", {
                "customer": str(self.tenant.uuid), "local_part": "عربي"}).status_code, 400)
            self.post("platform-mailboxes", {"customer": str(self.tenant.uuid), "local_part": "owner"})
            again = self.post("platform-mailboxes", {"customer": str(self.tenant.uuid), "local_part": "owner"})
        self.assertEqual(again.status_code, 400)
        self.assertEqual(Mailbox.objects.count(), 1)


# ====================================================================== billing


class BillingMathTests(TestCase):
    def setUp(self):
        self.tenant, _ = make_group("bill-a", plan="basic")  # 500 a month

    def test_the_plan_price_by_cycle_and_a_negotiated_price(self):
        self.assertEqual(billing.period_price(self.tenant)[0], Decimal("500.00"))
        terms = billing.terms_for(self.tenant)
        terms.cycle = CommercialTerms.Cycle.YEARLY
        terms.save()
        self.assertEqual(billing.period_price(self.tenant)[0], Decimal("6000.00"))
        terms.custom_price = Decimal("5000")
        terms.save()
        self.assertEqual(billing.period_price(self.tenant)[0], Decimal("5000.00"))

    def test_discounts_are_time_limited_percent_first_then_fixed(self):
        today = date(2026, 9, 1)
        Discount.objects.create(customer=self.tenant, percent=Decimal("10"), starts_on=today,
                                ends_on=today + timedelta(days=60))
        Discount.objects.create(customer=self.tenant, amount=Decimal("50"), starts_on=today,
                                ends_on=today + timedelta(days=60))
        self.assertEqual(billing.discount_on(self.tenant, Decimal("500"), today), Decimal("100.00"))
        self.assertEqual(billing.discount_on(self.tenant, Decimal("500"), today + timedelta(days=90)), 0)
        self.assertEqual(billing.discount_on(self.tenant, Decimal("30"), today), Decimal("30.00"))

    def test_issuing_numbers_invoices_and_moves_the_next_date(self):
        first = billing.issue_invoice(self.tenant, period_start=date(2026, 1, 31))
        self.assertEqual((first.period_end, first.total), (date(2026, 2, 27), Decimal("500.00")))
        self.assertEqual(billing.terms_for(self.tenant).next_invoice_on, date(2026, 2, 28))
        second = billing.issue_invoice(self.tenant)
        self.assertEqual(second.number, "INV-202602-0001")
        self.assertTrue(first.number.startswith("INV-202601-"))

    def test_payments_settle_invoices_and_the_balance(self):
        invoice = billing.issue_invoice(self.tenant, period_start=date(2026, 9, 1))
        billing.record_payment(self.tenant, "200", "cash", invoice=invoice)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "partial")
        self.assertEqual(billing.account(self.tenant)["balance"], "300.00")
        billing.record_payment(self.tenant, "300", "transfer", invoice=invoice, reference="TRX-1")
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "paid")
        self.assertEqual(billing.account(self.tenant)["balance"], "0.00")

    def test_marking_late_keeps_the_subscription_serving(self):
        billing.mark_late(self.tenant, "لم يسدد سبتمبر")
        with tenant_context(self.tenant):
            from subscriptions.entitlements import current_subscription

            self.assertIsNotNone(current_subscription(self.tenant))
        self.assertEqual(billing.account(self.tenant)["late"]["note"], "لم يسدد سبتمبر")

    def test_the_daily_command_issues_what_is_due(self):
        terms = billing.terms_for(self.tenant)
        terms.next_invoice_on = timezone.now().date()
        terms.save()
        other, _ = make_group("bill-b")
        stopped = billing.terms_for(other)
        stopped.next_invoice_on = timezone.now().date()
        stopped.save()
        other.status = "suspended"
        other.save()
        call_command("issue_platform_invoices", stdout=StringIO(), stderr=StringIO())
        self.assertEqual(PlatformInvoice.objects.filter(customer=self.tenant).count(), 1)
        self.assertEqual(PlatformInvoice.objects.filter(customer=other).count(), 0)


class BillingApiTests(OperatorsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.tenant, _ = make_group("bill-api", plan="basic")
        self.uuid = str(self.tenant.uuid)

    def test_terms_discount_invoice_payment_and_balance(self):
        data = self.post("platform-tenant-billing", {"cycle": "monthly", "custom_price": "400"}, self.uuid,
                         method="patch").json()
        self.assertEqual(data["period_price"], "400.00")
        today = timezone.now().date()
        data = self.post("platform-tenant-discounts", {
            "percent": "25", "starts_on": str(today), "ends_on": str(today + timedelta(days=30)), "reason": "افتتاح",
        }, self.uuid).json()
        self.assertTrue(data["discounts"][0]["active"])
        data = self.post("platform-tenant-invoices", {"period_start": str(today)}, self.uuid).json()
        invoice = data["invoices"][0]
        self.assertEqual((invoice["base_amount"], invoice["discount_amount"], invoice["total"]),
                         ("400.00", "100.00", "300.00"))
        refused = self.post("platform-tenant-payments", {"method": "transfer", "amount": "300",
                                                         "invoice": invoice["id"]}, self.uuid)
        self.assertEqual(refused.status_code, 400)  # a transfer needs its reference
        data = self.post("platform-tenant-payments", {"method": "transfer", "amount": "300",
                                                      "invoice": invoice["id"], "reference": "TRX-9"}, self.uuid).json()
        self.assertEqual(data["invoices"][0]["status"], "paid")
        self.assertEqual(data["account"]["balance"], "0.00")
        balances = self.client.get(reverse("api:platform-billing")).json()
        row = next(r for r in balances["items"] if r["uuid"] == self.uuid)
        self.assertEqual((row["invoiced"], row["paid"]), ("300.00", "300.00"))

    def test_a_paid_invoice_cannot_be_voided_an_open_one_can_with_a_reason(self):
        invoice = billing.issue_invoice(self.tenant)
        self.assertEqual(self.post("platform-invoice-void", {}, invoice.pk).status_code, 400)
        data = self.post("platform-invoice-void", {"reason": "خطأ"}, invoice.pk).json()
        self.assertEqual(data["invoices"][0]["status"], "void")
        self.assertEqual(data["account"]["balance"], "0.00")
        paid = billing.issue_invoice(self.tenant)
        billing.record_payment(self.tenant, paid.total, "cash", invoice=paid)
        self.assertEqual(self.post("platform-invoice-void", {"reason": "x"}, paid.pk).status_code, 400)

    def test_late_is_recorded_by_hand_and_cleared(self):
        data = self.post("platform-tenant-late", {"note": "متأخر شهرين"}, self.uuid).json()
        self.assertEqual(data["account"]["late"]["note"], "متأخر شهرين")
        data = self.client.delete(reverse("api:platform-tenant-late", args=[self.uuid])).json()
        self.assertIsNone(data["account"]["late"])

    def test_a_discount_needs_a_value_and_a_sane_period(self):
        today = str(timezone.now().date())
        self.assertEqual(self.post("platform-tenant-discounts", {"starts_on": today, "ends_on": today},
                                   self.uuid).status_code, 400)
        self.assertEqual(self.post("platform-tenant-discounts", {"percent": "150", "starts_on": today,
                                                                 "ends_on": today}, self.uuid).status_code, 400)
        self.assertEqual(self.post("platform-tenant-discounts", {"amount": "10", "starts_on": today,
                                                                 "ends_on": "2020-01-01"}, self.uuid).status_code, 400)

    def test_support_staff_read_balances_but_record_nothing(self):
        self.as_support()
        self.assertEqual(self.client.get(reverse("api:platform-tenant-billing", args=[self.uuid])).status_code, 200)
        self.assertEqual(self.post("platform-tenant-payments", {"method": "cash", "amount": "5"},
                                   self.uuid).status_code, 403)


class PlanApiTests(OperatorsMixin, TestCase):
    def test_add_and_change_a_plan(self):
        response = self.post("platform-plans-manage", {
            "code": "clinic-plus", "name": "Clinic Plus", "price": "900", "billing_period": "monthly",
            "limits": {"max_branches": 3, "max_doctors": ""}, "features": {"online_payments": True},
        })
        self.assertEqual(response.status_code, 201, response.content)
        plan = response.json()
        self.assertEqual((plan["limits"]["max_branches"], plan["limits"]["max_doctors"]), (3, None))
        changed = self.post("platform-plan", {"price": "950", "is_public": False}, plan["id"], method="patch").json()
        self.assertEqual((changed["price"], changed["is_public"]), ("950.00", False))
        listing = self.client.get(reverse("api:platform-plans-manage")).json()
        self.assertIn("clinic-plus", {p["code"] for p in listing["items"]})

    def test_unknown_features_and_negative_prices_are_refused(self):
        self.assertEqual(self.post("platform-plans-manage", {"code": "x", "name": "X", "features": {"teleport": 1}})
                         .status_code, 400)
        self.assertEqual(self.post("platform-plans-manage", {"code": "y", "name": "Y", "price": "-1"})
                         .status_code, 400)


# ====================================================================== online payments


class SubscriptionOnlinePaymentTests(TestCase):
    """The group owner pays a platform invoice with the platform's Paymob."""

    def setUp(self):
        cache.clear()
        self.tenant, self.branch = make_group("pay-own", plan="basic")
        with tenant_context(self.tenant):
            role = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name="Owner")[0]
        User.objects.create_user(username="boss", email="boss@pay.local", password=PASSWORD,
                                 tenant=self.tenant, role=role, branch=self.branch)
        self.client.login(email="boss@pay.local", password=PASSWORD)
        credential(Kind.PAYMOB, Scope.PLATFORM, PAYMOB)
        self.invoice = billing.issue_invoice(self.tenant)

    def start(self):
        replies = [{"token": "auth"}, {"id": 9}, {"token": "paykey"}]
        with mock.patch("platform_admin.gateways._request", side_effect=replies):
            return self.client.post(reverse("api:subscription-invoice-pay", args=[self.invoice.pk]),
                                    {"method": "paymob"}, content_type="application/json")

    def callback(self, transaction, signature=None):
        signature = signature or paymob_signature(transaction, PAYMOB["hmac_secret"])
        return self.client.post(
            reverse("api:gateway-callback", args=["paymob"]) + f"?hmac={signature}",
            {"type": "TRANSACTION", "obj": transaction}, content_type="application/json",
        )

    def test_the_owner_sees_their_invoices_and_the_ways_to_pay(self):
        data = self.client.get(reverse("api:subscription-invoices")).json()
        self.assertEqual([i["number"] for i in data["invoices"]], [self.invoice.number])
        self.assertEqual([m["kind"] for m in data["methods"]], ["paymob"])

    def test_a_signed_callback_settles_the_invoice_once(self):
        response = self.start()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("paymob.com/api/acceptance/iframes/22?payment_token=paykey", response.json()["redirect_url"])
        reference = response.json()["reference"]
        transaction = paymob_transaction(reference, 50000)
        self.assertEqual(self.callback(transaction).status_code, 200)
        self.assertEqual(self.callback(transaction).status_code, 200)  # repeated: no change
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "paid")
        self.assertEqual(PlatformPayment.objects.filter(status="confirmed").count(), 1)

    def test_a_forged_or_short_callback_is_rejected(self):
        reference = self.start().json()["reference"]
        self.assertEqual(self.callback(paymob_transaction(reference, 50000), signature="0" * 128).status_code, 400)
        self.assertEqual(self.callback(paymob_transaction(reference, 100)).status_code, 400)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "open")

    def test_another_groups_invoice_cannot_be_paid_from_here(self):
        other, _ = make_group("pay-other", plan="basic")
        foreign = billing.issue_invoice(other)
        response = self.client.post(reverse("api:subscription-invoice-pay", args=[foreign.pk]),
                                    {"method": "paymob"}, content_type="application/json")
        self.assertEqual(response.status_code, 404)


class ClinicOnlinePaymentTests(TestCase):
    """A patient pays their clinic with the clinic's own keys."""

    def setUp(self):
        cache.clear()
        self.tenant, self.branch = make_group("pay-clinic")
        with tenant_context(self.tenant):
            self.patient = Patient.all_objects.create(tenant=self.tenant, name="Mona", branch=self.branch,
                                                      phone1="01000000009")
            self.appointment = Appointment.all_objects.create(
                tenant=self.tenant, patient=self.patient, branch=self.branch, status="waiting",
                scheduled_date=timezone.now(), price=Decimal("300"),
            )
            _, token = PortalInvitation.issue(self.patient)
        response = self.client.post(
            reverse("api:portal:accept-invite", kwargs={"slug": self.tenant.slug}),
            {"token": token, "password": PASSWORD}, content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)

    def url(self, name, **kwargs):
        return reverse(f"api:portal:{name}", kwargs={"slug": self.tenant.slug, **kwargs})

    def pay(self):
        replies = [{"token": "auth"}, {"id": 9}, {"token": "paykey"}]
        with mock.patch("platform_admin.gateways._request", side_effect=replies):
            return self.client.post(self.url("appointment-pay", uuid=self.appointment.uuid),
                                    {"method": "paymob"}, content_type="application/json")

    def settle(self, reference, cents=30000):
        transaction = paymob_transaction(reference, cents)
        return self.client.post(
            reverse("api:gateway-callback", args=["paymob"])
            + f"?hmac={paymob_signature(transaction, PAYMOB['hmac_secret'])}",
            {"obj": transaction}, content_type="application/json",
        )

    def test_without_the_clinics_own_keys_there_is_no_online_payment(self):
        credential(Kind.PAYMOB, Scope.PLATFORM, PAYMOB)  # the platform's must not be used
        self.assertEqual(self.client.get(self.url("pay-options")).json()["methods"], [])
        self.assertFalse(self.client.get(self.url("appointments")).json()[0]["can_pay_online"])
        self.assertEqual(self.pay().status_code, 400)

    def test_a_confirmed_payment_lands_in_the_clinics_books(self):
        credential(Kind.PAYMOB, Scope.CLINIC, PAYMOB, customer=self.tenant, branch=self.branch)
        row = self.client.get(self.url("appointments")).json()[0]
        self.assertEqual((row["due"], row["can_pay_online"]), ("300.00", True))
        reference = self.pay().json()["reference"]
        self.assertEqual(self.settle(reference).status_code, 200)
        checkout = ClinicCheckout.objects.get(reference=reference)
        self.assertEqual(checkout.status, "confirmed")
        with tenant_context(self.tenant):
            payment = Payment.objects.get(uuid=checkout.payment_uuid)
            self.assertEqual((payment.amount, payment.method.name), (Decimal("300.00"), "دفع إلكتروني"))
        self.assertEqual(self.client.get(self.url("appointments")).json()[0]["due"], "0.00")
        self.assertEqual(self.settle(reference).status_code, 200)  # repeated: still one payment
        with tenant_context(self.tenant):
            self.assertEqual(Payment.objects.filter(appointment=self.appointment).count(), 1)

    def test_a_test_environment_payment_stays_out_of_the_books(self):
        credential(Kind.PAYMOB, Scope.GROUP, PAYMOB, customer=self.tenant, mode="test")
        reference = self.pay().json()["reference"]
        self.settle(reference)
        self.assertEqual(ClinicCheckout.objects.get(reference=reference).status, "confirmed")
        with tenant_context(self.tenant):
            self.assertFalse(Payment.objects.filter(appointment=self.appointment).exists())

    def test_a_plan_without_online_payments_offers_none(self):
        with tenant_context(self.tenant):
            Subscription.all_objects.filter(tenant=self.tenant).update(plan=Plan.objects.get(code="basic"))
        credential(Kind.PAYMOB, Scope.CLINIC, PAYMOB, customer=self.tenant, branch=self.branch)
        self.assertEqual(self.client.get(self.url("pay-options")).json()["methods"], [])
