"""Every screen renders, and every link in every template points somewhere.

These exist because an audit of the running application found two screens that
returned 500 while the whole test suite was green — the suite tested views and
permissions thoroughly, and never asked whether a template could actually be
rendered end to end.

Both bugs were of a kind unit tests do not catch:

* `employees/specialization_update.html` used `{% url 'specialization_list' %}`
  without its `employees:` namespace. `NoReverseMatch` is raised while rendering,
  so the view is fine, the form is fine, and the page is a 500. This is the same
  mistake that once made every unmatched URL in the project 500 (`redirect('login')`
  instead of `accounts:login`), so it has now happened twice.
* `notification_mark_read` used `.get()` rather than `get_object_or_404`, so a
  notification that did not exist raised `DoesNotExist` and returned a 500 where
  a 404 was meant.
"""

import re
import uuid
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import NoReverseMatch, reverse

from accounts.models import ClinicRole
from branches.models import Branch
from notifications.models import Notification
from tenants.context import tenant_context
from tenants.models import Tenant
from tenants.testing import act_as_tenant

User = get_user_model()

URL_TAG = re.compile(r"""\{%\s*url\s+['"]([^'"]+)['"]""")
SKIP_DIRS = {"venv", "static", "staticfiles", "private", "media"}


class TemplateUrlTagTests(SimpleTestCase):
    """Every `{% url %}` name resolves to something.

    Cheap, needs no database, and covers every template at once — which is what
    makes it worth having over testing screens one at a time. A name that cannot
    resolve is a guaranteed 500 the moment that template is rendered.
    """

    def template_files(self):
        root = Path(settings.BASE_DIR)
        for path in root.rglob("*.html"):
            if path.relative_to(root).parts[0] in SKIP_DIRS:
                continue
            yield path

    def test_every_url_tag_names_a_real_route(self):
        root = Path(settings.BASE_DIR)
        broken, scanned = {}, 0
        for path in self.template_files():
            for name in URL_TAG.findall(path.read_text(encoding="utf-8", errors="ignore")):
                scanned += 1
                try:
                    reverse(name)
                except NoReverseMatch as exc:
                    # Most routes need arguments, and reverse() complains about
                    # that too. Only an unknown *name* is the bug being hunted.
                    if "not a valid view function or pattern name" in str(exc):
                        broken.setdefault(name, set()).add(
                            path.relative_to(root).as_posix()
                        )
                except Exception:
                    pass

        self.assertGreater(scanned, 100, "the scan found almost no url tags — check SKIP_DIRS")
        self.assertEqual(
            broken, {},
            "these template links cannot resolve and will 500 when rendered:\n"
            + "\n".join(
                f"  {name} — {', '.join(sorted(files))}"
                for name, files in sorted(broken.items())
            ),
        )

    def test_url_tags_inside_app_templates_are_namespaced(self):
        """The underlying rule. Every app in this project registers its URLs
        under a namespace, so a bare name in an app template is the bug above
        waiting to happen — even when it happens to resolve today."""
        root = Path(settings.BASE_DIR)
        unnamespaced = {}
        for path in self.template_files():
            relative = path.relative_to(root)
            # Project-level templates may reference the handful of unnamespaced
            # routes (index, dashboard); app templates should not.
            if relative.parts[0] in {"templates"}:
                continue
            for name in URL_TAG.findall(path.read_text(encoding="utf-8", errors="ignore")):
                if ":" not in name and name not in {"index", "dashboard"}:
                    unnamespaced.setdefault(name, set()).add(relative.as_posix())
        self.assertEqual(
            unnamespaced, {},
            "app templates must use namespaced route names:\n"
            + "\n".join(
                f"  {name} — {', '.join(sorted(files))}"
                for name, files in sorted(unnamespaced.items())
            ),
        )


class ScreenRenderTests(TestCase):
    """The screens an ordinary user reaches without any object in hand.

    Renders them for real, per role, so a template error is a failure rather
    than something a user finds. Object-scoped screens are covered by each app's
    own tests; what was missing was anything that rendered a template at all.
    """

    ROLE_EMAILS = {
        "Admin": "screens-admin@t.local",
        "Reception": "screens-reception@t.local",
        "Doctor": "screens-doctor@t.local",
    }

    # Reached without an id. Each is asserted not to raise; a 302 is a
    # legitimate answer (role denied, or an export needing a format parameter).
    LIST_SCREENS = [
        "patients:patient_list", "patients:patient_create",
        "appointments:appointment_list", "appointments:appointment_create",
        "appointments:waiting_list",
        "billing:payment_list", "billing:payment_create",
        "billing:expense_list", "billing:expense_create",
        "billing:expense_category_list", "billing:financial_report",
        "branches:branch_list", "branches:branch_create",
        "services:service_list", "services:service_create",
        "employees:employee_list", "employees:employee_create",
        "employees:employee_type_list", "employees:specialization_list",
        "notifications:notification_list",
        "audit:audit_list",
        "accounts:user_list", "accounts:user_create", "accounts:user_settings",
    ]

    def setUp(self):
        self.tenant = Tenant.objects.first()
        act_as_tenant(self, self.tenant)
        from tenants.provisioning import provision_tenant_defaults

        provision_tenant_defaults(self.tenant)
        self.branch = Branch.all_objects.create(
            tenant=self.tenant, name="Screens", code="SCR"
        )
        for role_name, email in self.ROLE_EMAILS.items():
            User.objects.create_user(
                username=f"screens-{role_name.lower()}", email=email,
                password="pass12345", tenant=self.tenant, branch=self.branch,
                role=ClinicRole.all_objects.get(tenant=self.tenant, name=role_name),
            )

    def test_no_screen_raises_for_any_role(self):
        for role, email in self.ROLE_EMAILS.items():
            self.client.login(email=email, password="pass12345")
            for name in self.LIST_SCREENS:
                with self.subTest(role=role, screen=name):
                    response = self.client.get(reverse(name))
                    self.assertLess(
                        response.status_code, 500,
                        f"{name} returned {response.status_code} for {role}",
                    )

    def test_the_dashboard_renders_for_every_role(self):
        for role, email in self.ROLE_EMAILS.items():
            self.client.login(email=email, password="pass12345")
            with self.subTest(role=role):
                self.assertEqual(self.client.get("/dashboard/").status_code, 200)


class NotificationLookupTests(TestCase):
    """Regression: marking a missing notification read returned 500."""

    def setUp(self):
        self.tenant = Tenant.objects.first()
        act_as_tenant(self, self.tenant)
        from tenants.provisioning import provision_tenant_defaults

        provision_tenant_defaults(self.tenant)
        branch = Branch.all_objects.create(tenant=self.tenant, name="N", code="N")
        self.user = User.objects.create_user(
            username="notify", email="notify@t.local", password="pass12345",
            tenant=self.tenant, branch=branch,
            role=ClinicRole.all_objects.get(tenant=self.tenant, name="Admin"),
        )
        self.client.login(email="notify@t.local", password="pass12345")

    def test_a_missing_notification_is_a_404_not_a_500(self):
        response = self.client.get(
            reverse("notifications:notification_mark_read", args=[uuid.uuid4()])
        )
        self.assertEqual(response.status_code, 404)

    def test_another_users_notification_is_also_a_404(self):
        """Scoped by user already; this pins that the refusal stays a 404 rather
        than becoming a crash, and never reveals that the id exists."""
        other = User.objects.create_user(
            username="other", email="other@t.local", password="pass12345",
            tenant=self.tenant,
        )
        with tenant_context(self.tenant):
            theirs = Notification.all_objects.create(
                tenant=self.tenant, user=other, title="theirs", message="x"
            )
        response = self.client.get(
            reverse("notifications:notification_mark_read", args=[theirs.uuid])
        )
        self.assertEqual(response.status_code, 404)
        theirs.refresh_from_db()
        self.assertFalse(theirs.is_read)

    def test_marking_your_own_notification_works(self):
        with tenant_context(self.tenant):
            mine = Notification.all_objects.create(
                tenant=self.tenant, user=self.user, title="mine", message="x"
            )
        response = self.client.get(
            reverse("notifications:notification_mark_read", args=[mine.uuid])
        )
        self.assertEqual(response.status_code, 302)
        mine.refresh_from_db()
        self.assertTrue(mine.is_read)
