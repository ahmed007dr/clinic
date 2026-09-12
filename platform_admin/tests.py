"""Platform administration: who counts as a platform operator, and the old
server-rendered area's retirement.

The operator's screens are the React developer portal (`/app/platform`,
api/platform*.py, tested in api/tests/test_platform*.py). The older Django
pages under `/platform/` duplicated a subset of it and now redirect there.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.models import ClinicRole
from branches.models import Branch
from tenants.context import tenant_context
from tenants.models import Tenant
from tenants.provisioning import provision_tenant_defaults

from .permissions import is_platform_staff

User = get_user_model()


class PlatformBase(TestCase):
    def setUp(self):
        self.a = Tenant.objects.first()
        provision_tenant_defaults(self.a)
        with tenant_context(self.a):
            self.branch_a = Branch.all_objects.create(tenant=self.a, name="A Main", code="AM")
            role_a = ClinicRole.all_objects.get(tenant=self.a, name="Admin")
        self.operator = User.objects.create_user(
            username="operator", email="ops@platform.test", password="pass12345",
            tenant=None, is_platform_staff=True, platform_role="super",
        )
        self.tenant_admin = User.objects.create_user(
            username="clinicadmin", email="admin@a.test", password="pass12345",
            tenant=self.a, role=role_a, branch=self.branch_a,
        )


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


class RetiredPagesTests(TestCase):
    def test_the_old_platform_pages_redirect_to_the_developer_portal(self):
        for path in ("/platform/", "/platform/tenant/00000000-0000-0000-0000-000000000000/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 301)
            self.assertEqual(response["Location"], "/app/platform")
