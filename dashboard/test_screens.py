"""What is still server-rendered keeps working, and every link in it points somewhere.

Django serves only what the React app links to for the browser to print or
download — receipts, the queue ticket, the shift report, the prescription, the
intake form, the exports — and the audit log page. Everything else was React
and the API, and the old screens are gone.

These exist because an audit once found screens that returned 500 while the
whole suite was green: `{% url %}` names without their namespace raise
`NoReverseMatch` only when the template renders, so the view, the form and the
permissions all pass and the page is a 500.
"""

import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import NoReverseMatch, reverse

from accounts.models import ClinicRole
from branches.models import Branch
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

        # Few templates link anywhere now (they are print pages), so there is no
        # minimum to assert: the guard is that none of the tags left is broken.
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


class ServerRenderedPagesTests(TestCase):
    """The audit log renders for the Owner and for nobody else; the print and
    export pages send a signed-out visitor to the React sign-in, not to a page
    of an interface that no longer exists."""

    def setUp(self):
        self.tenant = Tenant.objects.first()
        act_as_tenant(self, self.tenant)
        from tenants.provisioning import provision_tenant_defaults

        provision_tenant_defaults(self.tenant)
        self.branch = Branch.all_objects.create(tenant=self.tenant, name="Screens", code="SCR")
        for role_name in ("Owner", "Admin", "Reception", "Doctor"):
            User.objects.create_user(
                username=f"screens-{role_name.lower()}", email=f"screens-{role_name.lower()}@t.local",
                password="pass12345", tenant=self.tenant, branch=self.branch,
                role=ClinicRole.all_objects.get(tenant=self.tenant, name=role_name),
            )

    def login(self, role):
        self.client.logout()
        self.assertTrue(self.client.login(email=f"screens-{role.lower()}@t.local", password="pass12345"))

    def test_the_audit_log_renders_for_the_owner_only(self):
        self.login("Owner")
        response = self.client.get(reverse("audit:audit_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "سجل التغييرات")
        self.assertContains(response, 'href="/app/"')
        for role in ("Admin", "Reception", "Doctor"):
            self.login(role)
            self.assertNotEqual(self.client.get(reverse("audit:audit_list")).status_code, 200, role)

    def test_a_signed_out_visitor_is_sent_to_the_react_sign_in(self):
        for url in (reverse("audit:audit_list"), reverse("patients:patient_list_export"),
                    reverse("billing:payment_list_export"), "/patients/print/intake/"):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith("/app/login"), response["Location"])
