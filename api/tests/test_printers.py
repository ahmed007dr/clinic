"""The printer inventory: who registers hardware, and branch scoping —
same rules as any other reference list (PaymentMethod, ExpenseCategory)."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import ClinicRole
from branches.models import Branch, Printer
from tenants.context import tenant_context
from tenants.models import Tenant

User = get_user_model()
PASSWORD = "pass12345"


class PrinterTestsBase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            self.branch_a = Branch.all_objects.create(tenant=self.tenant, name="Printers A", code="PA")
            self.branch_b = Branch.all_objects.create(tenant=self.tenant, name="Printers B", code="PB")
            roles = {
                n: ClinicRole.all_objects.get_or_create(tenant=self.tenant, name=n)[0]
                for n in ("Owner", "Admin", "Reception")
            }
        self.owner = User.objects.create_user(
            username="owner-pr", email="owner-pr@t.local", password=PASSWORD,
            tenant=self.tenant, role=roles["Owner"], branch=self.branch_a,
        )
        self.admin_a = User.objects.create_user(
            username="admin-pr-a", email="admin-pr-a@t.local", password=PASSWORD,
            tenant=self.tenant, role=roles["Admin"], branch=self.branch_a,
        )
        self.desk_a = User.objects.create_user(
            username="desk-pr-a", email="desk-pr-a@t.local", password=PASSWORD,
            tenant=self.tenant, role=roles["Reception"], branch=self.branch_a,
        )
        self.admin_b = User.objects.create_user(
            username="admin-pr-b", email="admin-pr-b@t.local", password=PASSWORD,
            tenant=self.tenant, role=roles["Admin"], branch=self.branch_b,
        )

    def login(self, user):
        self.client.logout()
        self.assertTrue(self.client.login(email=user.email, password=PASSWORD))

    def create(self, **overrides):
        body = {
            "branch": str(self.branch_a.uuid), "name": "طابعة الاستقبال", "purpose": "ticket",
            "ip_address": "192.168.1.50", "mac_address": "00:1A:2B:3C:4D:5E",
        }
        body.update(overrides)
        return self.client.post(reverse("api:printer-list"), body, content_type="application/json")


class PrinterPermissionTests(PrinterTestsBase):
    def test_an_admin_can_register_a_printer(self):
        self.login(self.admin_a)
        response = self.create()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["mac_address"], "00:1A:2B:3C:4D:5E")

    def test_reception_can_list_but_not_register(self):
        self.login(self.admin_a)
        self.create()
        self.login(self.desk_a)
        self.assertEqual(self.client.get(reverse("api:printer-list")).status_code, 200)
        self.assertEqual(self.create(name="أخرى").status_code, 403)

    def test_a_bad_mac_address_is_refused(self):
        self.login(self.admin_a)
        response = self.create(mac_address="not-a-mac")
        self.assertEqual(response.status_code, 400)
        self.assertIn("mac_address", response.json())


class PrinterScopeTests(PrinterTestsBase):
    def test_an_admin_only_sees_their_own_branchs_printers(self):
        self.login(self.admin_a)
        self.create()
        self.login(self.admin_b)
        self.assertEqual(self.create(branch=str(self.branch_b.uuid), name="طابعة ب").status_code, 201)
        rows = self.client.get(reverse("api:printer-list")).json()["results"]
        self.assertEqual({row["name"] for row in rows}, {"طابعة ب"})

    def test_the_owner_sees_every_branchs_printers(self):
        self.login(self.admin_a)
        self.create()
        self.login(self.admin_b)
        self.create(branch=str(self.branch_b.uuid), name="طابعة ب")
        self.login(self.owner)
        rows = self.client.get(reverse("api:printer-list")).json()["results"]
        self.assertEqual({row["name"] for row in rows}, {"طابعة الاستقبال", "طابعة ب"})


class PrinterDefaultTests(PrinterTestsBase):
    def test_only_one_default_per_branch_and_purpose(self):
        self.login(self.admin_a)
        self.create(is_default=True)
        second = self.create(name="ثانية", is_default=True)
        self.assertEqual(second.status_code, 400)
        self.assertIn("is_default", second.json())
        # A different purpose is a different slot.
        self.assertEqual(self.create(name="إيصالات", purpose="payment", is_default=True).status_code, 201)

    def test_a_different_branch_is_a_different_slot(self):
        self.login(self.owner)  # the one account that legitimately writes to both
        self.assertEqual(self.create(is_default=True).status_code, 201)
        self.assertEqual(
            self.create(branch=str(self.branch_b.uuid), name="طابعة ب", is_default=True).status_code, 201,
        )

    def test_moving_the_default_flag_off_first_frees_it_up(self):
        self.login(self.admin_a)
        first = self.create(is_default=True).json()
        self.client.patch(
            reverse("api:printer-detail", args=[first["uuid"]]), {"is_default": False},
            content_type="application/json",
        )
        second = self.create(name="ثانية", is_default=True)
        self.assertEqual(second.status_code, 201)
