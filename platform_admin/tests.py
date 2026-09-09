"""Platform administration and Tier 1 "act as tenant".

The agreed constraints are the spec for these tests: platform access is
read-only over clinical data, tenant-scoped, explicitly selected, and audited;
ordinary application connections stay subject to row-level security; and
cross-tenant creation, editing and deletion do not become a general capability.
Each of those is asserted rather than assumed.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import ClinicRole
from audit.models import AuditLog
from branches.models import Branch
from patients.models import Patient
from subscriptions.entitlements import current_subscription
from subscriptions.models import Plan, Subscription
from tenants.context import get_current_tenant, tenant_context
from tenants.models import Tenant
from tenants.provisioning import provision_tenant_defaults

from .permissions import is_platform_staff

User = get_user_model()


class PlatformBase(TestCase):
    def setUp(self):
        self.a = Tenant.objects.first()
        provision_tenant_defaults(self.a)
        self.b = Tenant.objects.create(
            name="Rival Clinic", slug="rival-platform", status=Tenant.Status.ACTIVE
        )
        provision_tenant_defaults(self.b)

        with tenant_context(self.a):
            self.branch_a = Branch.all_objects.create(
                tenant=self.a, name="A Main", code="AM"
            )
            self.patient_a = Patient.all_objects.create(
                tenant=self.a, name="A Patient", branch=self.branch_a
            )
            role_a = ClinicRole.all_objects.get(tenant=self.a, name="Admin")
        with tenant_context(self.b):
            self.branch_b = Branch.all_objects.create(
                tenant=self.b, name="B Main", code="BM"
            )
            Patient.all_objects.create(
                tenant=self.b, name="B Patient", branch=self.branch_b
            )

        self.operator = User.objects.create_user(
            username="operator", email="ops@platform.test", password="pass12345",
            tenant=None, is_platform_staff=True,
        )
        # An ordinary clinic administrator: org-wide inside their own tenant,
        # which is the strongest tenant-side role there is.
        self.tenant_admin = User.objects.create_user(
            username="clinicadmin", email="admin@a.test", password="pass12345",
            tenant=self.a, role=role_a, branch=self.branch_a,
        )

    def as_operator(self):
        self.client.login(email="ops@platform.test", password="pass12345")

    def as_tenant_admin(self):
        self.client.login(email="admin@a.test", password="pass12345")


class PlatformAccessTests(PlatformBase):
    def test_the_flag_requires_having_no_tenant(self):
        """A user who belongs to a clinic must never hold platform powers, even
        if the flag is set by mistake."""
        self.assertTrue(is_platform_staff(self.operator))
        self.tenant_admin.is_platform_staff = True
        self.tenant_admin.save()
        self.assertFalse(is_platform_staff(self.tenant_admin))

    def test_superuser_alone_is_not_enough(self):
        """`is_superuser` is a Django-admin concept. Conflating the two is how a
        tenant administrator eventually acquires cross-tenant reach because
        somebody ticked a box on the wrong screen."""
        self.tenant_admin.is_superuser = True
        self.tenant_admin.save()
        self.assertFalse(is_platform_staff(self.tenant_admin))

    def test_an_inactive_operator_is_refused(self):
        self.operator.is_active = False
        self.operator.save()
        self.assertFalse(is_platform_staff(self.operator))

    def test_a_tenant_administrator_cannot_reach_the_platform_area(self):
        self.as_tenant_admin()
        for url in (
            reverse("platform_admin:tenant_list"),
            reverse("platform_admin:tenant_detail", args=[self.b.uuid]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_an_anonymous_visitor_cannot_reach_it(self):
        response = self.client.get(reverse("platform_admin:tenant_list"))
        self.assertNotEqual(response.status_code, 200)

    def test_a_tenant_administrator_cannot_change_another_tenants_status(self):
        self.as_tenant_admin()
        response = self.client.post(
            reverse("platform_admin:tenant_set_status", args=[self.b.uuid]),
            {"status": Tenant.Status.SUSPENDED},
        )
        self.assertEqual(response.status_code, 403)
        self.b.refresh_from_db()
        self.assertEqual(self.b.status, Tenant.Status.ACTIVE)


class ActAsTenantTests(PlatformBase):
    """Tier 1: one tenant at a time, on the normal connection, read-only."""

    def test_the_listing_shows_every_clinic_with_its_own_counts(self):
        self.as_operator()
        response = self.client.get(reverse("platform_admin:tenant_list"))
        self.assertEqual(response.status_code, 200)
        rows = {row["tenant"].slug: row for row in response.context["rows"]}
        self.assertIn(self.a.slug, rows)
        self.assertIn(self.b.slug, rows)
        # Counts are gathered per tenant, so each row reflects that clinic only.
        self.assertEqual(rows[self.a.slug]["patients"], 1)
        self.assertEqual(rows[self.b.slug]["patients"], 1)

    def test_the_detail_page_reads_the_selected_tenants_data(self):
        self.as_operator()
        response = self.client.get(
            reverse("platform_admin:tenant_detail", args=[self.a.uuid])
        )
        self.assertEqual(response.status_code, 200)
        limits = {row["label"]: row for row in response.context["limits"]}
        self.assertEqual(limits["Patients"]["used"], 1)
        self.assertEqual(limits["Branches"]["used"], 1)

    def test_the_context_does_not_leak_out_of_the_request(self):
        """The views enter tenant_context for a read and leave it. If the
        binding survived, the next request on this worker would inherit it."""
        self.as_operator()
        self.client.get(reverse("platform_admin:tenant_detail", args=[self.a.uuid]))
        self.assertIsNone(get_current_tenant())

    def test_no_second_database_connection_is_used(self):
        """Pins the architectural decision: Tier 1 runs on the ordinary
        connection. If a privileged alias is ever added, this fails and forces
        the decision to be taken deliberately."""
        self.assertEqual(list(settings.DATABASES), ["default"])

    def test_row_level_security_still_applies_to_the_operator(self):
        """Platform staff carry no tenant, so outside an explicit selection they
        see nothing — the fail-closed default is unchanged by this feature."""
        self.assertIsNone(self.operator.tenant)
        self.assertEqual(Patient.objects.count(), 0)


class PlatformAuditTests(PlatformBase):
    def latest_platform_entry(self):
        """Filtered rather than "the most recent row".

        A write also fires the ordinary change-tracking signal, so two entries
        land: the signal's "Update Tenant", and this module's record of who did
        it and why. Both are wanted — one describes the data change, the other
        the platform action — so the test has to name which it means.
        """
        return (
            AuditLog.objects.filter(description__contains="[platform]")
            .order_by("-created_at")
            .first()
        )

    def test_opening_a_clinics_record_is_recorded(self):
        """Reads matter here: the sensitive act is a platform operator looking
        at a clinic's record at all, and the change-tracking signals only fire
        on writes."""
        self.as_operator()
        before = AuditLog.objects.count()
        self.client.get(reverse("platform_admin:tenant_detail", args=[self.a.uuid]))

        self.assertEqual(AuditLog.objects.count(), before + 1)
        entry = self.latest_platform_entry()
        self.assertEqual(entry.user, self.operator)
        self.assertIn("[platform]", entry.description)
        self.assertIn("inspect", entry.description)

    def test_the_entry_is_filed_against_the_inspected_clinic(self):
        """So the fact that the platform looked appears in that clinic's own
        trail, which is where a customer would go looking for it."""
        self.as_operator()
        self.client.get(reverse("platform_admin:tenant_detail", args=[self.a.uuid]))
        self.assertEqual(self.latest_platform_entry().tenant, self.a)

    def test_a_status_change_records_both_values(self):
        """'Who suspended this clinic and when' is the first question anyone
        asks afterwards, and the previous value is half the answer."""
        self.as_operator()
        self.client.post(
            reverse("platform_admin:tenant_set_status", args=[self.b.uuid]),
            {"status": Tenant.Status.SUSPENDED},
        )
        entry = self.latest_platform_entry()
        self.assertIn("active", entry.description)
        self.assertIn("suspended", entry.description)


class TenantLifecycleTests(PlatformBase):
    """§10: approve, suspend, activate."""

    def test_an_operator_can_suspend_and_reactivate_a_clinic(self):
        self.as_operator()
        url = reverse("platform_admin:tenant_set_status", args=[self.b.uuid])

        self.client.post(url, {"status": Tenant.Status.SUSPENDED})
        self.b.refresh_from_db()
        self.assertEqual(self.b.status, Tenant.Status.SUSPENDED)

        self.client.post(url, {"status": Tenant.Status.ACTIVE})
        self.b.refresh_from_db()
        self.assertEqual(self.b.status, Tenant.Status.ACTIVE)

    def test_status_changes_are_post_only(self):
        """A GET would let a crawler or a prefetched link suspend a clinic."""
        self.as_operator()
        response = self.client.get(
            reverse("platform_admin:tenant_set_status", args=[self.b.uuid])
        )
        self.assertEqual(response.status_code, 405)
        self.b.refresh_from_db()
        self.assertEqual(self.b.status, Tenant.Status.ACTIVE)

    def test_an_invalid_status_is_rejected(self):
        self.as_operator()
        self.client.post(
            reverse("platform_admin:tenant_set_status", args=[self.b.uuid]),
            {"status": "deleted-everything"},
        )
        self.b.refresh_from_db()
        self.assertEqual(self.b.status, Tenant.Status.ACTIVE)


class PlanManagementTests(PlatformBase):
    """§10: manage subscriptions — the one tenant-owned write, kept narrow."""

    def test_an_operator_can_move_a_clinic_between_plans(self):
        self.as_operator()
        professional = Plan.objects.get(code="professional")
        self.client.post(
            reverse("platform_admin:tenant_change_plan", args=[self.b.uuid]),
            {"plan": professional.pk},
        )
        with tenant_context(self.b):
            self.assertEqual(current_subscription(self.b).plan.code, "professional")

    def test_both_the_data_change_and_the_platform_action_are_recorded(self):
        """The signal records that a Subscription row changed; this module
        records which operator moved which clinic between which plans. Losing
        either would leave a question unanswerable."""
        self.as_operator()
        self.client.post(
            reverse("platform_admin:tenant_change_plan", args=[self.b.uuid]),
            {"plan": Plan.objects.get(code="professional").pk},
        )
        self.assertTrue(
            # ContentType.model is lowercased, which is what the signal stores.
            AuditLog.objects.filter(model_name="subscription", action="update").exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(description__contains="[platform] plan change").exists()
        )

    def test_the_change_is_audited(self):
        self.as_operator()
        self.client.post(
            reverse("platform_admin:tenant_change_plan", args=[self.b.uuid]),
            {"plan": Plan.objects.get(code="enterprise").pk},
        )
        entry = (
            AuditLog.objects.filter(description__contains="[platform]")
            .order_by("-created_at").first()
        )
        self.assertIn("plan change", entry.description)
        self.assertIn("enterprise", entry.description)

    def test_plan_changes_are_post_only(self):
        self.as_operator()
        response = self.client.get(
            reverse("platform_admin:tenant_change_plan", args=[self.b.uuid])
        )
        self.assertEqual(response.status_code, 405)

    def test_it_touches_only_the_subscription(self):
        """Bounded on purpose: this is the commercial relationship, not a
        patient record. Clinical data stays read-only from the platform area."""
        self.as_operator()
        with tenant_context(self.b):
            patients_before = Patient.objects.count()
        self.client.post(
            reverse("platform_admin:tenant_change_plan", args=[self.b.uuid]),
            {"plan": Plan.objects.get(code="basic").pk},
        )
        with tenant_context(self.b):
            self.assertEqual(Patient.objects.count(), patients_before)
            self.assertEqual(
                Subscription.all_objects.filter(
                    tenant=self.b, status=Subscription.Status.ACTIVE
                ).count(),
                1,
                "a plan change must move the existing subscription, not add one",
            )


class NoClinicalWriteTests(PlatformBase):
    """The constraint that cross-tenant creation, editing and deletion must not
    become a general platform capability — asserted as the absence of routes."""

    def test_the_platform_area_exposes_no_clinical_write_routes(self):
        from django.urls import NoReverseMatch

        for name in (
            "patient_create", "patient_update", "patient_delete",
            "visit_create", "prescription_create", "attachment_upload",
        ):
            with self.subTest(route=name):
                with self.assertRaises(NoReverseMatch):
                    reverse(f"platform_admin:{name}")

    def test_the_only_write_routes_are_status_and_plan(self):
        """If a third write appears here, this test is where the decision has to
        be made rather than assumed."""
        from platform_admin.urls import urlpatterns

        names = {pattern.name for pattern in urlpatterns}
        self.assertEqual(
            names, {"tenant_list", "tenant_detail", "tenant_set_status", "tenant_change_plan"}
        )
