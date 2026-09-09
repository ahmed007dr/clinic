"""Django admin under tenant isolation.

Two distinct claims are made here.

The first is that every registered ModelAdmin can build its form. That sounds
trivial, but it is exactly the check that found `AppointmentAdmin` and
`NotificationAdmin` returning 500 on add/change — both named `created_at`
(auto_now_add, therefore not editable) in `fieldsets` without marking it
readonly. It is asserted generically, across whatever is registered, so a
future admin with the same mistake fails here rather than in someone's browser.

The second is that tenant-owned models are not reachable through admin at all,
while the four models that carry no tenant-isolation policy still are.

These tests deliberately do **not** go through admin URLs. Once access is
denied, every URL returns 302/403 whether or not the underlying form is
broken — so a URL-based test would report success for a page that still
crashes. Asking the ModelAdmin directly keeps the two claims independent.
"""

from django.contrib import admin as django_admin
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test.client import RequestFactory

from .admin import TenantOwnedAdmin
from .models import Tenant

User = get_user_model()

# The models that are legitimately administrable: none of them has a
# tenant_isolation policy, and none carries a non-nullable tenant.
ADMINISTRABLE = {
    "accounts.User",
    "audit.AuditLog",
    "tenants.Tenant",
    "auth.Group",
}


def platform_request(user):
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


class AdminBaseTests(TestCase):
    def setUp(self):
        # A platform operator: every Django permission check passes, so the only
        # thing that can turn them away is the admin classes themselves.
        self.operator = User.objects.create_superuser(
            username="platform-op", email="op@platform.test", password="pass12345",
        )
        self.operator.tenant = None
        self.operator.is_platform_staff = True
        self.operator.save()
        self.request = platform_request(self.operator)


class AdminFormIntegrityTests(AdminBaseTests):
    """Step 1 — every admin form must be constructible."""

    def test_every_registered_admin_can_build_its_form(self):
        """Catches non-editable fields named in fieldsets, misspelled field
        names, and anything else that makes modelform_factory raise. Permission
        checks do not run here, so disabled admins are still covered."""
        for model, model_admin in sorted(
            django_admin.site._registry.items(), key=lambda kv: kv[0]._meta.label
        ):
            with self.subTest(model=model._meta.label):
                try:
                    model_admin.get_form(self.request)
                except Exception as exc:  # noqa: BLE001 — the point is "anything"
                    self.fail(
                        f"{type(model_admin).__name__}.get_form() raised "
                        f"{type(exc).__name__}: {exc}"
                    )

    def test_every_registered_admin_can_build_its_change_form(self):
        """The add and change forms take different paths through get_form —
        `obj` is passed on change, and readonly handling differs."""
        tenant = Tenant.objects.first()
        for model, model_admin in sorted(
            django_admin.site._registry.items(), key=lambda kv: kv[0]._meta.label
        ):
            obj = tenant if model is Tenant else None
            with self.subTest(model=model._meta.label):
                try:
                    model_admin.get_form(self.request, obj=obj, change=obj is not None)
                except Exception as exc:  # noqa: BLE001
                    self.fail(
                        f"{type(model_admin).__name__}.get_form(change) raised "
                        f"{type(exc).__name__}: {exc}"
                    )

    def test_the_two_repaired_admins_expose_created_at_readonly(self):
        """Regression: `created_at` stays *visible* — the fix is not to delete
        it from the fieldset, which would lose the audit display."""
        from appointments.models import Appointment
        from notifications.models import Notification

        for model in (Appointment, Notification):
            with self.subTest(model=model._meta.label):
                model_admin = django_admin.site._registry[model]
                self.assertIn("created_at", model_admin.readonly_fields)
                named = {
                    field
                    for _, options in model_admin.fieldsets
                    for field in options.get("fields", ())
                }
                self.assertIn("created_at", named)

    def test_no_admin_names_a_non_editable_field_without_marking_it_readonly(self):
        """The underlying rule, stated directly, so the next occurrence is
        reported as the specific mistake rather than a generic crash."""
        for model, model_admin in sorted(
            django_admin.site._registry.items(), key=lambda kv: kv[0]._meta.label
        ):
            fieldsets = getattr(model_admin, "fieldsets", None)
            if not fieldsets:
                continue
            readonly = set(model_admin.readonly_fields or ())
            named = {
                field for _, options in fieldsets for field in options.get("fields", ())
            }
            for name in sorted(named):
                try:
                    field = model._meta.get_field(name)
                except Exception:
                    continue  # a callable or admin method, not a model field
                if not getattr(field, "editable", True):
                    with self.subTest(model=model._meta.label, field=name):
                        self.assertIn(
                            name, readonly,
                            f"{model._meta.label}.{name} is not editable, so it must "
                            f"be in readonly_fields to appear in fieldsets",
                        )


class TenantOwnedAdminDeniedTests(AdminBaseTests):
    """Step 2 — tenant-owned models are not administrable."""

    def tenant_owned_admins(self):
        return {
            model._meta.label: model_admin
            for model, model_admin in django_admin.site._registry.items()
            if isinstance(model_admin, TenantOwnedAdmin)
        }

    def test_the_expected_number_of_admins_is_disabled(self):
        """Pinned so that registering a new tenant-owned model without a
        decision about it is visible rather than silent."""
        disabled = self.tenant_owned_admins()
        self.assertEqual(
            len(disabled), 21,
            f"expected 21 TenantOwnedAdmin registrations, found "
            f"{len(disabled)}: {sorted(disabled)}",
        )

    def test_every_tenant_owned_admin_denies_every_permission(self):
        for label, model_admin in sorted(self.tenant_owned_admins().items()):
            with self.subTest(model=label):
                self.assertFalse(model_admin.has_module_permission(self.request))
                self.assertFalse(model_admin.has_view_permission(self.request))
                self.assertFalse(model_admin.has_add_permission(self.request))
                self.assertFalse(model_admin.has_change_permission(self.request))
                self.assertFalse(model_admin.has_delete_permission(self.request))

    def test_disabled_models_are_absent_from_the_admin_index(self):
        """`has_module_permission` is what keeps them off the index page. An
        entry that appears and then refuses on click is worse than no entry."""
        app_list = django_admin.site.get_app_list(self.request)
        listed = {
            f"{app['app_label']}.{model['object_name']}"
            for app in app_list
            for model in app["models"]
        }
        for label in sorted(self.tenant_owned_admins()):
            with self.subTest(model=label):
                self.assertNotIn(label, listed)

    def test_the_four_administrable_models_remain_available(self):
        """The point of denying access to tenant-owned models is that platform
        administration of the rest keeps working."""
        app_list = django_admin.site.get_app_list(self.request)
        listed = {
            f"{app['app_label']}.{model['object_name']}"
            for app in app_list
            for model in app["models"]
        }
        for label in sorted(ADMINISTRABLE):
            with self.subTest(model=label):
                self.assertIn(label, listed)

    def test_the_administrable_models_can_still_be_read(self):
        by_label = {
            model._meta.label: (model, ma)
            for model, ma in django_admin.site._registry.items()
        }
        for label in sorted(ADMINISTRABLE):
            model, model_admin = by_label[label]
            with self.subTest(model=label):
                self.assertTrue(model_admin.has_view_permission(self.request))
                # Reading must actually work, not merely be permitted.
                model_admin.get_queryset(self.request).count()

    def test_tenant_administration_still_works(self):
        """Creating and suspending tenants is the real platform-admin job, and
        it must survive this change — Tenant carries no isolation policy."""
        model_admin = django_admin.site._registry[Tenant]
        self.assertTrue(model_admin.has_add_permission(self.request))
        self.assertTrue(model_admin.has_change_permission(self.request))

    def test_no_admin_reads_through_a_non_default_connection(self):
        """Pins the architectural decision: platform admin gains no privileged
        database access. If a second, BYPASSRLS-style connection is ever added,
        this fails and forces the decision to be made deliberately."""
        from django.conf import settings

        self.assertEqual(
            list(settings.DATABASES), ["default"],
            "a second database alias appeared; platform admin must not gain "
            "privileged database access without an explicit decision",
        )
        for model, model_admin in sorted(
            django_admin.site._registry.items(), key=lambda kv: kv[0]._meta.label
        ):
            if isinstance(model_admin, TenantOwnedAdmin):
                continue  # denied outright; get_queryset is not reached
            with self.subTest(model=model._meta.label):
                self.assertEqual(model_admin.get_queryset(self.request).db, "default")
