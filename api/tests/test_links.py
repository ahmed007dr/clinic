"""Social and contact links in the printed footer and the patient portal.

The group owner's rule (2026-09-11): the clinic's links — only those it fills
in — appear in the footer of its prescriptions and intake form, and in the
patient portal. Each doctor can add their own line and links to their own
prescriptions, which show only after the clinic's Admin approves them.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from branches.models import Branch
from employees.models import Employee, EmployeeType
from medical.models import Prescription, PrescriptionItem, Visit
from patients.models import Patient
from tenants.context import tenant_context
from tenants.models import Tenant

User = get_user_model()

FACEBOOK = "https://facebook.com/nile-derma"


class LinkTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        self.tenant.status = "active"
        self.tenant.save(update_fields=["status"])
        with tenant_context(self.tenant):
            self.branch = Branch.all_objects.create(tenant=self.tenant, name="Links", code="LK")
            self.other = Branch.all_objects.create(tenant=self.tenant, name="Elsewhere", code="EW")
            roles = {
                n: ClinicRole.all_objects.get_or_create(tenant=self.tenant, name=n)[0]
                for n in ("Owner", "Admin", "Doctor", "Reception")
            }
            doctor_type, _ = EmployeeType.all_objects.get_or_create(tenant=self.tenant, name="Doctor")
            self.doctor = Employee.all_objects.create(
                tenant=self.tenant, name="Dr Links", branch=self.branch, employee_type=doctor_type,
                national_id="LK-1", salary_value=0,
            )
            patient = Patient.all_objects.create(tenant=self.tenant, name="Rana", branch=self.branch)
            visit = Visit.all_objects.create(
                tenant=self.tenant, patient=patient, doctor=self.doctor, branch=self.branch,
                visit_date=timezone.now(),
            )
            self.prescription = Prescription.all_objects.create(
                tenant=self.tenant, visit=visit, patient=patient, doctor=self.doctor,
            )
            PrescriptionItem.all_objects.create(tenant=self.tenant, prescription=self.prescription, medication="X")
        for key, role, branch in (
            ("admin", "Admin", self.branch), ("far", "Admin", self.other),
            ("desk", "Reception", self.branch), ("doc", "Doctor", self.branch),
        ):
            User.objects.create_user(
                username=key, email=f"{key}@lk.local", password="pass12345", tenant=self.tenant,
                role=roles[role], branch=branch, employee=self.doctor if key == "doc" else None,
            )

    def login(self, key):
        self.client.logout()
        self.assertTrue(self.client.login(email=f"{key}@lk.local", password="pass12345"))

    def set_clinic_links(self, links):
        return self.client.patch(
            reverse("api:print-settings", args=[self.branch.uuid]), {"print_links": links},
            content_type="application/json",
        )

    def printed(self):
        return self.client.get(reverse("medical:prescription_print", args=[self.prescription.uuid]))

    # ------------------------------------------------------------ clinic

    def test_the_clinics_filled_in_links_print_in_the_footer(self):
        self.login("admin")
        response = self.set_clinic_links({"facebook": FACEBOOK, "whatsapp": "+20 100 123 4567", "tiktok": ""})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(set(response.json()["print_links"]), {"facebook", "whatsapp"})

        self.login("desk")
        page = self.printed()
        self.assertContains(page, "facebook.com/nile-derma")
        self.assertContains(page, "https://wa.me/201001234567")
        self.assertNotContains(page, "تيك توك")
        form = self.client.get(reverse("patients:intake_form_print"))
        self.assertContains(form, "facebook.com/nile-derma")

    def test_only_web_addresses_are_accepted(self):
        self.login("admin")
        for bad in ({"facebook": "javascript:alert(1)"}, {"website": "not a link"}, {"whatsapp": "12"}):
            with self.subTest(links=bad):
                self.assertEqual(self.set_clinic_links(bad).status_code, 400)

    def test_the_portal_shows_the_clinics_links_publicly(self):
        self.login("admin")
        self.set_clinic_links({"instagram": "instagram.com/nile"})
        self.client.logout()
        data = self.client.get(reverse("api:portal:links", kwargs={"slug": self.tenant.slug})).json()
        self.assertEqual(
            [(c["name"], [l["kind"] for l in c["links"]]) for c in data["clinics"]],
            [("Links", ["instagram"])],
        )

    # ------------------------------------------------------------ doctor

    def save_profile(self, tagline="استشاري الجلدية", links=None):
        return self.client.put(
            reverse("api:my-doctor-profile"),
            {"tagline": tagline, "links": links if links is not None else {"instagram": "instagram.com/drlinks"}},
            content_type="application/json",
        )

    def test_a_doctors_links_print_only_after_approval(self):
        self.login("doc")
        saved = self.save_profile()
        self.assertEqual(saved.status_code, 200, saved.content)
        self.assertEqual(saved.json()["status"], "pending")
        self.assertNotContains(self.printed(), "instagram.com/drlinks")

        self.login("admin")
        pending = self.client.get(reverse("api:doctor-profiles"), {"status": "pending"}).json()
        self.assertEqual([p["doctor_name"] for p in pending], ["Dr Links"])
        approved = self.client.post(reverse("api:doctor-profile-approve", args=[self.doctor.uuid]))
        self.assertEqual(approved.json()["status"], "approved")

        page = self.printed()
        self.assertContains(page, "instagram.com/drlinks")
        self.assertContains(page, "استشاري الجلدية")

    def test_a_change_waits_while_the_approved_version_keeps_printing(self):
        self.login("doc")
        self.save_profile()
        self.login("admin")
        self.client.post(reverse("api:doctor-profile-approve", args=[self.doctor.uuid]))
        self.login("doc")
        self.save_profile(links={"instagram": "instagram.com/changed"})
        page = self.printed()
        self.assertContains(page, "instagram.com/drlinks")
        self.assertNotContains(page, "instagram.com/changed")

        self.login("admin")
        rejected = self.client.post(
            reverse("api:doctor-profile-reject", args=[self.doctor.uuid]), {"note": "حساب غير رسمي"},
            content_type="application/json",
        )
        self.assertEqual(rejected.json()["status"], "rejected")
        self.login("doc")
        mine = self.client.get(reverse("api:my-doctor-profile")).json()
        self.assertEqual(mine["note"], "حساب غير رسمي")
        self.assertEqual(mine["approved"]["links"]["instagram"], "https://instagram.com/drlinks")

    def test_only_the_clinics_management_approves(self):
        self.login("doc")
        self.save_profile()
        for key, expected in (("desk", 403), ("doc", 403), ("far", 404)):
            with self.subTest(user=key):
                self.login(key)
                response = self.client.post(reverse("api:doctor-profile-approve", args=[self.doctor.uuid]))
                self.assertEqual(response.status_code, expected)

    def test_a_doctor_cannot_publish_an_unsafe_link(self):
        self.login("doc")
        self.assertEqual(self.save_profile(links={"website": "javascript:alert(1)"}).status_code, 400)
