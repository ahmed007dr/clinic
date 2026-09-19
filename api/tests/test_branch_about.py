"""The "About the clinic" tab: what management edits, and what the public sees.

The group's Owner edits every branch's address, phone, map link, working hours
and description; a branch's Admin only their own. The portal — signed in or not —
shows the running branches with those, and the specialties of each branch's
doctors, which nobody types in.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import ClinicRole
from branches.models import Branch
from employees.models import Employee, EmployeeType, Specialization
from tenants.context import tenant_context
from tenants.models import Tenant
from tenants.provisioning import provision_tenant_defaults
from tenants.testing import act_as_tenant

User = get_user_model()


def patch(client, url, body):
    return client.patch(url, body, content_type="application/json")


class AboutBase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        act_as_tenant(self, self.tenant)
        provision_tenant_defaults(self.tenant)
        self.a = Branch.all_objects.create(tenant=self.tenant, name="Alpha", code="AL", address="1 Nile St", phone="0100")
        self.b = Branch.all_objects.create(tenant=self.tenant, name="Beta", code="BE")
        self.stopped = Branch.all_objects.create(tenant=self.tenant, name="Gamma", code="GA", is_active=False)

        def role(name):
            return ClinicRole.all_objects.get(tenant=self.tenant, name=name)

        def make(username, role_name, branch):
            return User.objects.create_user(
                username=username, email=f"{username}@ab.local", password="pass12345",
                tenant=self.tenant, role=role(role_name), branch=branch,
            )

        self.owner = make("owner", "Owner", self.a)
        self.admin_a = make("admin-a", "Admin", self.a)
        self.reception = make("rec", "Reception", self.a)
        self.doctor_user = make("doc", "Doctor", self.a)

        doctor_type = EmployeeType.all_objects.get(tenant=self.tenant, name="Doctor")
        self.derma = Specialization.all_objects.create(tenant=self.tenant, name="Dermatology", description="Skin")
        self.laser = Specialization.all_objects.create(tenant=self.tenant, name="Laser")
        self.cosmetic = Specialization.all_objects.create(tenant=self.tenant, name="Cosmetic")
        self.hidden = Specialization.all_objects.create(tenant=self.tenant, name="Hidden")

        def doctor(name, nid, branch, specs, extra=(), active=True):
            employee = Employee.all_objects.create(
                tenant=self.tenant, name=name, branch=branch, employee_type=doctor_type,
                national_id=nid, salary_value=0, email=f"{nid}@secret.local",
            )
            employee.specializations.set(specs)
            employee.extra_branches.set(extra)
            User.objects.create_user(
                username=f"u-{nid}", email=f"u-{nid}@ab.local", password="pass12345", tenant=self.tenant,
                role=role("Doctor"), branch=branch, employee=employee, is_active=active,
            )
            return employee

        doctor("Dr A", "AB-1", self.a, [self.derma, self.laser])
        doctor("Dr B", "AB-2", self.b, [self.laser])
        doctor("Dr Linked", "AB-3", self.a, [self.cosmetic], extra=[self.b])
        doctor("Dr Stopped", "AB-4", self.a, [self.hidden], active=False)

    def login(self, username):
        self.client.logout()
        self.assertTrue(self.client.login(email=f"{username}@ab.local", password="pass12345"))

    def rows(self):
        return {row["name"]: row for row in self.client.get(reverse("api:about-list")).json()["results"]}


class ManagementTests(AboutBase):
    def test_the_owner_sees_every_branch_and_an_admin_only_their_own(self):
        self.login("owner")
        self.assertEqual(set(self.rows()), {"Alpha", "Beta", "Gamma"})
        self.login("admin-a")
        self.assertEqual(set(self.rows()), {"Alpha"})

    def test_reception_and_doctors_cannot_reach_it(self):
        for who in ("rec", "doc"):
            self.login(who)
            self.assertEqual(self.client.get(reverse("api:about-list")).status_code, 403, who)
            self.assertEqual(patch(self.client, reverse("api:about-detail", args=[self.a.uuid]),
                                   {"about_text": "x"}).status_code, 403, who)

    def test_the_owner_edits_any_branch(self):
        self.login("owner")
        response = patch(self.client, reverse("api:about-detail", args=[self.b.uuid]), {
            "address": "9 Palm Rd", "phone": "0122", "map_url": "https://maps.example/b",
            "working_hours": "Sat–Thu 9–5", "about_text": "Our second clinic.",
        })
        self.assertEqual(response.status_code, 200, response.content)
        self.b.refresh_from_db()
        self.assertEqual((self.b.address, self.b.working_hours, self.b.about_text),
                         ("9 Palm Rd", "Sat–Thu 9–5", "Our second clinic."))

    def test_an_admin_edits_their_own_branch_and_not_another(self):
        self.login("admin-a")
        own = patch(self.client, reverse("api:about-detail", args=[self.a.uuid]), {"about_text": "Mine"})
        self.assertEqual(own.status_code, 200, own.content)
        other = patch(self.client, reverse("api:about-detail", args=[self.b.uuid]), {"about_text": "Theirs"})
        self.assertEqual(other.status_code, 404)
        self.b.refresh_from_db()
        self.assertEqual(self.b.about_text, "")

    def test_it_changes_only_what_the_public_is_told_never_the_clinic_itself(self):
        self.login("admin-a")
        patch(self.client, reverse("api:about-detail", args=[self.a.uuid]),
              {"name": "Renamed", "code": "ZZ", "is_active": False, "email": "x@y.z"})
        self.a.refresh_from_db()
        self.assertEqual((self.a.name, self.a.code, self.a.is_active), ("Alpha", "AL", True))

    def test_a_map_link_must_be_a_web_address(self):
        self.login("owner")
        for bad in ("javascript:alert(1)", "ftp://x.example/m", "not a link"):
            with self.subTest(bad=bad):
                response = patch(self.client, reverse("api:about-detail", args=[self.a.uuid]), {"map_url": bad})
                self.assertEqual(response.status_code, 400)
                self.assertIn("map_url", response.json())
        ok = patch(self.client, reverse("api:about-detail", args=[self.a.uuid]), {"map_url": "https://goo.gl/maps/x"})
        self.assertEqual(ok.status_code, 200)

    def test_the_specialties_are_worked_out_and_read_only(self):
        self.login("owner")
        rows = self.rows()
        self.assertEqual([s["name"] for s in rows["Alpha"]["specializations"]], ["Cosmetic", "Dermatology", "Laser"])
        patch(self.client, reverse("api:about-detail", args=[self.a.uuid]), {"specializations": [{"name": "Fake"}]})
        self.assertNotIn("Fake", [s["name"] for s in self.rows()["Alpha"]["specializations"]])


class PublicTests(AboutBase):
    def about(self):
        self.client.logout()
        return self.client.get(reverse("api:portal:about", kwargs={"slug": self.tenant.slug}))

    def test_anyone_can_read_it_without_signing_in(self):
        response = self.about()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["clinic"], self.tenant.name)

    def test_only_running_branches_are_shown(self):
        names = [b["name"] for b in self.about().json()["branches"]]
        self.assertEqual(names, ["Alpha", "Beta"])

    def test_it_shows_what_management_wrote(self):
        self.login("admin-a")
        patch(self.client, reverse("api:about-detail", args=[self.a.uuid]), {
            "working_hours": "9–5", "about_text": "Welcome", "map_url": "https://maps.example/a",
        })
        alpha = next(b for b in self.about().json()["branches"] if b["name"] == "Alpha")
        self.assertEqual((alpha["address"], alpha["phone"]), ("1 Nile St", "0100"))
        self.assertEqual((alpha["working_hours"], alpha["about_text"], alpha["map_url"]),
                         ("9–5", "Welcome", "https://maps.example/a"))

    def test_specialties_come_from_the_branchs_active_doctors_including_linked_ones(self):
        branches = {b["name"]: b for b in self.about().json()["branches"]}
        self.assertEqual([s["name"] for s in branches["Alpha"]["specializations"]],
                         ["Cosmetic", "Dermatology", "Laser"])
        # Beta has its own doctor (Laser) and the one the Owner linked (Cosmetic).
        self.assertEqual([s["name"] for s in branches["Beta"]["specializations"]], ["Cosmetic", "Laser"])
        # A stopped doctor's specialty is not offered anywhere.
        everything = str(self.about().json())
        self.assertNotIn("Hidden", everything)
        self.assertEqual(
            next(s for s in branches["Alpha"]["specializations"] if s["name"] == "Dermatology")["description"], "Skin"
        )

    def test_no_doctor_names_or_addresses_leak(self):
        body = str(self.about().json())
        for secret in ("Dr A", "Dr B", "Dr Linked", "secret.local", "salary"):
            self.assertNotIn(secret, body)

    def test_another_clinics_branches_are_never_shown(self):
        rival = Tenant.objects.create(name="Rival", slug="rival-about", status=Tenant.Status.ACTIVE)
        provision_tenant_defaults(rival)
        with tenant_context(rival):
            Branch.all_objects.create(tenant=rival, name="Rival Branch", code="RB", address="Elsewhere")
        self.assertNotIn("Rival Branch", str(self.about().json()))
        theirs = self.client.get(reverse("api:portal:about", kwargs={"slug": rival.slug})).json()
        self.assertEqual([b["name"] for b in theirs["branches"]], ["Rival Branch"])


class HidingTests(AboutBase):
    """Management can leave a whole branch, or chosen specialties of it, out of the
    portal's "About" tab — without stopping the branch or the doctors."""

    def public(self):
        self.client.logout()
        return {b["name"]: b for b in self.client.get(
            reverse("api:portal:about", kwargs={"slug": self.tenant.slug})).json()["branches"]}

    def names(self, branch):
        return [s["name"] for s in branch["specializations"]]

    def test_every_branch_and_specialty_is_shown_until_management_hides_it(self):
        self.login("owner")
        row = self.rows()["Alpha"]
        self.assertTrue(row["about_visible"])
        self.assertEqual(row["hidden_specializations"], [])
        self.assertFalse(any(s["hidden"] for s in row["specializations"]))

    def test_a_hidden_branch_leaves_the_portal_but_stays_in_management(self):
        self.login("owner")
        patch(self.client, reverse("api:about-detail", args=[self.b.uuid]), {"about_visible": False})
        self.assertEqual(set(self.public()), {"Alpha"})
        self.login("owner")
        self.assertFalse(self.rows()["Beta"]["about_visible"])
        # The branch itself is untouched: still running, still bookable.
        self.b.refresh_from_db()
        self.assertTrue(self.b.is_active)

    def test_showing_it_again_brings_it_back(self):
        self.login("owner")
        url = reverse("api:about-detail", args=[self.b.uuid])
        patch(self.client, url, {"about_visible": False})
        patch(self.client, url, {"about_visible": True})
        self.assertEqual(set(self.public()), {"Alpha", "Beta"})

    def test_an_admin_hides_their_own_branch_and_not_another(self):
        self.login("admin-a")
        self.assertEqual(patch(self.client, reverse("api:about-detail", args=[self.a.uuid]),
                               {"about_visible": False}).status_code, 200)
        self.assertEqual(patch(self.client, reverse("api:about-detail", args=[self.b.uuid]),
                               {"about_visible": False}).status_code, 404)
        self.assertEqual(set(self.public()), {"Beta"})

    def test_hiding_a_specialty_affects_that_branch_only(self):
        self.login("owner")
        response = patch(self.client, reverse("api:about-detail", args=[self.a.uuid]),
                         {"hidden_specializations": [str(self.laser.uuid)]})
        self.assertEqual(response.status_code, 200, response.content)
        public = self.public()
        self.assertNotIn("Laser", self.names(public["Alpha"]))
        self.assertIn("Laser", self.names(public["Beta"]))
        # Management still sees it — marked hidden — so it can be shown again.
        self.login("owner")
        alpha = self.rows()["Alpha"]
        laser = next(s for s in alpha["specializations"] if s["name"] == "Laser")
        self.assertTrue(laser["hidden"])
        self.assertEqual(alpha["hidden_specializations"], [str(self.laser.uuid)])

    def test_unhiding_a_specialty_and_hiding_several_at_once(self):
        self.login("owner")
        url = reverse("api:about-detail", args=[self.a.uuid])
        patch(self.client, url, {"hidden_specializations": [str(self.laser.uuid), str(self.derma.uuid)]})
        self.assertEqual(self.names(self.public()["Alpha"]), ["Cosmetic"])
        self.login("owner")
        patch(self.client, url, {"hidden_specializations": []})
        self.assertEqual(self.names(self.public()["Alpha"]), ["Cosmetic", "Dermatology", "Laser"])

    def test_an_admin_hides_specialties_of_their_own_branch_only(self):
        self.login("admin-a")
        self.assertEqual(patch(self.client, reverse("api:about-detail", args=[self.a.uuid]),
                               {"hidden_specializations": [str(self.derma.uuid)]}).status_code, 200)
        self.assertEqual(patch(self.client, reverse("api:about-detail", args=[self.b.uuid]),
                               {"hidden_specializations": [str(self.laser.uuid)]}).status_code, 404)
        self.assertNotIn("Dermatology", self.names(self.public()["Alpha"]))
        self.assertIn("Laser", self.names(self.public()["Beta"]))

    def test_another_clinics_specialty_cannot_be_named(self):
        rival = Tenant.objects.create(name="Rv", slug="rv-hide", status=Tenant.Status.ACTIVE)
        provision_tenant_defaults(rival)
        with tenant_context(rival):
            foreign = Specialization.all_objects.create(tenant=rival, name="Foreign")
        self.login("owner")
        response = patch(self.client, reverse("api:about-detail", args=[self.a.uuid]),
                         {"hidden_specializations": [str(foreign.uuid)]})
        self.assertEqual(response.status_code, 400)
        self.assertIn("hidden_specializations", response.json())

    def test_a_hidden_specialty_still_serves_bookings(self):
        """Hiding is about what is displayed: the doctor's specialty is untouched,
        so a booking form still offers it."""
        self.login("owner")
        patch(self.client, reverse("api:about-detail", args=[self.a.uuid]),
              {"hidden_specializations": [str(self.laser.uuid)]})
        listed = {s["name"] for s in self.client.get(reverse("api:specialization-list")).json()["results"]}
        self.assertIn("Laser", listed)
