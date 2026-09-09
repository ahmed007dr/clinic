"""Plans, subscriptions and entitlements — doc §11, §84.

The theme running through these is that entitlements **fail closed**. A tenant
with no subscription, an unknown feature and an unresolvable limit all deny
rather than allow, because the cost of a wrongly blocked action is an error
message and the cost of a wrongly allowed one is a clinic using capacity nobody
planned or billed for.
"""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from branches.models import Branch
from patients.models import Patient
from tenants.context import tenant_context
from tenants.models import Tenant
from tenants.provisioning import ensure_subscription, provision_tenant_defaults
from tenants.testing import act_as_tenant

from .entitlements import (
    FEATURES,
    FeatureUnavailable,
    LimitReached,
    check_limit,
    current_subscription,
    get_limit,
    has_feature,
    require_feature,
    resolve_features,
    validate_feature_keys,
)
from .models import Plan, Subscription

User = get_user_model()


class PlanCatalogueTests(TestCase):
    """The catalogue is platform-level: shared, not owned by anyone."""

    def test_the_seeded_plans_exist(self):
        codes = set(Plan.objects.values_list("code", flat=True))
        self.assertTrue({"basic", "professional", "enterprise"} <= codes)

    def test_enterprise_is_unlimited_rather_than_a_large_number(self):
        """`None` and 'a million' are different statements, and only one of them
        survives a customer with a million patients."""
        enterprise = Plan.objects.get(code="enterprise")
        for limit in ("max_branches", "max_doctors", "max_staff", "max_patients"):
            with self.subTest(limit=limit):
                self.assertIsNone(getattr(enterprise, limit))

    def test_a_plan_is_not_tenant_owned(self):
        """It carries no tenant foreign key, which is also what keeps it out of
        the row-level security policy set — correctly, since a plan is not
        anybody's private data."""
        self.assertNotIn("tenant", [f.name for f in Plan._meta.get_fields()])

    def test_unknown_feature_keys_are_rejected(self):
        """A typo would otherwise read exactly like a disabled feature, and
        nobody would find it until a customer complained."""
        with self.assertRaises(ValidationError):
            validate_feature_keys({"whatsap": True})

    def test_non_boolean_feature_values_are_rejected(self):
        with self.assertRaises(ValidationError):
            validate_feature_keys({"whatsapp": "yes"})

    def test_a_plan_validates_its_own_features(self):
        plan = Plan(code="broken", name="Broken", features={"nonsense": True})
        with self.assertRaises(ValidationError):
            plan.full_clean()


class EntitlementResolutionTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        act_as_tenant(self, self.tenant)
        self.basic = Plan.objects.get(code="basic")
        self.professional = Plan.objects.get(code="professional")
        Subscription.all_objects.filter(tenant=self.tenant).delete()

    def subscribe(self, plan, **kwargs):
        kwargs.setdefault("status", Subscription.Status.ACTIVE)
        return Subscription.all_objects.create(
            tenant=self.tenant, plan=plan, **kwargs
        )

    def test_a_tenant_with_no_subscription_gets_the_closed_defaults(self):
        self.assertIsNone(current_subscription(self.tenant))
        features = resolve_features(self.tenant)
        self.assertFalse(features["whatsapp"])
        self.assertFalse(features["ai"])

    def test_a_tenant_with_no_subscription_has_a_zero_limit(self):
        """Not unlimited. Treating 'unknown' as 'unrestricted' is how a lapsed
        tenant grows without bound."""
        self.assertEqual(get_limit(self.tenant, "max_branches"), 0)
        with self.assertRaises(LimitReached):
            check_limit(self.tenant, "max_branches", 0)

    def test_the_plan_decides_features(self):
        self.subscribe(self.professional)
        self.assertTrue(has_feature(self.tenant, "whatsapp"))
        self.assertTrue(has_feature(self.tenant, "packages"))
        self.assertFalse(has_feature(self.tenant, "ai"))

    def test_a_tenant_override_beats_the_plan(self):
        """§11 custom contracts: one clinic gets something its tier does not
        include, without inventing a private plan for the negotiation."""
        self.subscribe(self.basic, feature_overrides={"whatsapp": True})
        self.assertFalse(self.basic.features["whatsapp"])
        self.assertTrue(has_feature(self.tenant, "whatsapp"))

    def test_an_override_can_also_take_a_feature_away(self):
        self.subscribe(self.professional, feature_overrides={"packages": False})
        self.assertFalse(has_feature(self.tenant, "packages"))

    def test_only_an_active_subscription_counts(self):
        self.subscribe(self.professional, status=Subscription.Status.CANCELLED)
        self.assertIsNone(current_subscription(self.tenant))
        self.assertFalse(has_feature(self.tenant, "whatsapp"))

    def test_asking_about_an_unknown_feature_raises(self):
        """Returning False would hide a programming error forever."""
        with self.assertRaises(KeyError):
            has_feature(self.tenant, "teleportation")

    def test_require_feature_raises_for_a_missing_one(self):
        self.subscribe(self.basic)
        with self.assertRaises(FeatureUnavailable) as caught:
            require_feature(self.tenant, "ai")
        self.assertEqual(caught.exception.feature, "ai")

    def test_unlimited_never_raises(self):
        self.subscribe(Plan.objects.get(code="enterprise"))
        self.assertIsNone(get_limit(self.tenant, "max_patients"))
        check_limit(self.tenant, "max_patients", 10 ** 6)  # must not raise

    def test_a_limit_blocks_at_the_boundary_not_past_it(self):
        self.subscribe(self.basic)  # max_branches = 1
        check_limit(self.tenant, "max_branches", 0)
        with self.assertRaises(LimitReached) as caught:
            check_limit(self.tenant, "max_branches", 1)
        self.assertEqual(caught.exception.allowed, 1)
        self.assertEqual(caught.exception.current, 1)

    def test_every_registered_feature_resolves(self):
        """Guards against a key added to the registry but never given a default."""
        self.subscribe(self.basic)
        resolved = resolve_features(self.tenant)
        self.assertEqual(set(resolved), set(FEATURES))


class SubscriptionIntegrityTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        act_as_tenant(self, self.tenant)
        self.basic = Plan.objects.get(code="basic")
        Subscription.all_objects.filter(tenant=self.tenant).delete()

    def test_a_tenant_cannot_have_two_active_subscriptions(self):
        """Two actives make 'which plan is this?' ambiguous, and resolution
        would silently pick whichever sorted first."""
        from django.db import IntegrityError, transaction

        Subscription.all_objects.create(
            tenant=self.tenant, plan=self.basic, status=Subscription.Status.ACTIVE
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Subscription.all_objects.create(
                    tenant=self.tenant, plan=self.basic,
                    status=Subscription.Status.ACTIVE,
                )

    def test_history_is_allowed_alongside_one_active(self):
        """A clinic upgrades, lapses and renews; billing needs to know what the
        terms were in March."""
        Subscription.all_objects.create(
            tenant=self.tenant, plan=self.basic, status=Subscription.Status.CANCELLED
        )
        Subscription.all_objects.create(
            tenant=self.tenant, plan=self.basic, status=Subscription.Status.EXPIRED
        )
        Subscription.all_objects.create(
            tenant=self.tenant, plan=self.basic, status=Subscription.Status.ACTIVE
        )
        self.assertEqual(Subscription.all_objects.filter(tenant=self.tenant).count(), 3)

    def test_a_subscription_cannot_end_before_it_starts(self):
        from django.db import IntegrityError, transaction

        today = timezone.now().date()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Subscription.all_objects.create(
                    tenant=self.tenant, plan=self.basic,
                    started_on=today, ends_on=today - timedelta(days=1),
                )

    def test_overrides_are_validated(self):
        subscription = Subscription(
            tenant=self.tenant, plan=self.basic, feature_overrides={"bogus": True}
        )
        with self.assertRaises(ValidationError):
            subscription.full_clean(exclude=["uuid"])


class ProvisioningTests(TestCase):
    def test_existing_tenants_were_grandfathered_by_the_migration(self):
        """Entitlements fail closed, so shipping enforcement without this would
        have blocked every running clinic from adding a branch or a patient."""
        for tenant in Tenant.objects.all():
            with self.subTest(tenant=tenant.slug), tenant_context(tenant):
                subscription = current_subscription(tenant)
                self.assertIsNotNone(subscription)
                self.assertEqual(subscription.plan.code, "enterprise")

    def test_a_new_tenant_starts_on_the_entry_plan_with_a_trial(self):
        tenant = Tenant.objects.create(
            name="Fresh", slug="fresh", status=Tenant.Status.ACTIVE
        )
        provision_tenant_defaults(tenant)
        with tenant_context(tenant):
            subscription = current_subscription(tenant)
            self.assertIsNotNone(subscription, "a new tenant must not start unable to act")
            self.assertEqual(subscription.plan.code, "basic")
            self.assertIsNotNone(subscription.trial_ends_on)

    def test_provisioning_never_replaces_an_existing_subscription(self):
        """A tenant moved onto another plan must not be silently reset by a
        later provisioning run — the post_migrate backstop calls this."""
        tenant = Tenant.objects.first()
        with tenant_context(tenant):
            before = current_subscription(tenant)
            ensure_subscription(tenant)
            after = current_subscription(tenant)
            self.assertEqual(before.pk, after.pk)
            self.assertEqual(after.plan.code, "enterprise")


class LimitEnforcementTests(TestCase):
    """The limits must hold against a POST, not against a hidden button."""

    def setUp(self):
        self.tenant = Tenant.objects.first()
        act_as_tenant(self, self.tenant)
        provision_tenant_defaults(self.tenant)
        role = ClinicRole.all_objects.get(tenant=self.tenant, name="Admin")
        self.branch = Branch.all_objects.create(
            tenant=self.tenant, name="Main", code="MN"
        )
        User.objects.create_user(
            username="admin", email="admin@t.local", password="pass12345",
            tenant=self.tenant, role=role, branch=self.branch,
        )
        self.client.login(email="admin@t.local", password="pass12345")

        # Put the tenant on Basic: one branch, 500 patients.
        Subscription.all_objects.filter(tenant=self.tenant).delete()
        Subscription.all_objects.create(
            tenant=self.tenant, plan=Plan.objects.get(code="basic"),
            status=Subscription.Status.ACTIVE,
        )

    def test_a_branch_beyond_the_plan_limit_is_refused_on_post(self):
        self.assertEqual(Branch.all_objects.filter(tenant=self.tenant).count(), 1)
        response = self.client.post(
            reverse("branches:branch_create"),
            {"name": "Second", "code": "SEC"}, follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Branch.all_objects.filter(tenant=self.tenant).count(), 1)
        self.assertContains(response, "ترقية الباقة")

    def test_raising_the_plan_allows_the_branch(self):
        """The other half: the limit must be the plan's, not a hard-coded one."""
        Subscription.all_objects.filter(tenant=self.tenant).update(
            plan=Plan.objects.get(code="professional")
        )
        self.client.post(
            reverse("branches:branch_create"), {"name": "Second", "code": "SEC"}
        )
        self.assertEqual(Branch.all_objects.filter(tenant=self.tenant).count(), 2)

    def test_the_patient_limit_is_enforced_on_post(self):
        Subscription.all_objects.filter(tenant=self.tenant).update(
            plan=Plan.objects.get(code="basic")
        )
        Plan.objects.filter(code="basic").update(max_patients=1)
        Patient.all_objects.create(
            tenant=self.tenant, name="First", branch=self.branch
        )
        response = self.client.post(
            reverse("patients:patient_create"),
            {"name": "Second", "gender": "male", "marital_status": "single"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Patient.all_objects.filter(tenant=self.tenant).count(), 1)


class SubscriptionIsolationTests(TestCase):
    """A clinic can see what it pays for. It cannot see anyone else's terms."""

    def setUp(self):
        self.a = Tenant.objects.first()
        self.b = Tenant.objects.create(
            name="Rival", slug="rival-subs", status=Tenant.Status.ACTIVE
        )
        provision_tenant_defaults(self.b)

    def test_each_tenant_resolves_its_own_entitlements(self):
        with tenant_context(self.b):
            Subscription.all_objects.filter(tenant=self.b).update(
                plan=Plan.objects.get(code="professional")
            )
        with tenant_context(self.a):
            self.assertEqual(current_subscription(self.a).plan.code, "enterprise")
        with tenant_context(self.b):
            self.assertEqual(current_subscription(self.b).plan.code, "professional")

    def test_a_tenants_subscription_is_invisible_to_another(self):
        from django.db import connection

        with tenant_context(self.a):
            visible = set(
                Subscription.all_objects.values_list("tenant_id", flat=True)
            )
        if connection.vendor == "postgresql":
            # RLS is the guarantee: all_objects bypasses the manager, not the
            # database.
            self.assertEqual(visible, {self.a.id})
        else:
            self.assertIn(self.a.id, visible)
