"""The public clinic page (docs/15, Phase 1): who is shown, and which images.

Two rules under test. The public page shows only what management chose to
publish — a doctor who has been switched on, a logo or cover that is approved —
and nothing else of the clinic. And an image a clinic's Admin uploads reaches the
public only after the group's Owner approves it.
"""

import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from PIL import Image

from api.tests.test_branch_about import AboutBase, patch
from branches.models import Branch
from employees.models import Employee
from tenants.context import tenant_context
from tenants.models import Tenant
from tenants.provisioning import provision_tenant_defaults

MEDIA = tempfile.mkdtemp(prefix="clinic-test-media-")


def picture(kind="PNG", size=(40, 30), name="x.png"):
    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buffer, format=kind)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


@override_settings(MEDIA_ROOT=MEDIA)
class PublicPageBase(AboutBase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def about(self):
        self.client.logout()
        return self.client.get(reverse("api:portal:about", kwargs={"slug": self.tenant.slug})).json()

    def branch_public(self, name):
        return next(b for b in self.about()["branches"] if b["name"] == name)

    def upload(self, url, **files):
        return self.client.post(url, files, format="multipart")

    def branch_url(self, branch):
        return reverse("api:public-media-branch", args=[branch.uuid])


class DoctorVisibilityTests(PublicPageBase):
    def doctor(self, name):
        return Employee.all_objects.get(tenant=self.tenant, name=name)

    def publish(self, name, **extra):
        Employee.all_objects.filter(tenant=self.tenant, name=name).update(show_publicly=True, **extra)

    def test_no_doctor_is_public_until_management_switches_them_on(self):
        for branch in self.about()["branches"]:
            self.assertEqual(branch["doctors"], [], branch["name"])

    def test_a_switched_on_doctor_shows_name_specialties_and_approved_line_only(self):
        self.publish("Dr A", public_profile={"tagline": "Skin and laser", "links": {"facebook": "https://facebook.com/dra"}})
        alpha = self.branch_public("Alpha")
        self.assertEqual(len(alpha["doctors"]), 1)
        doctor = alpha["doctors"][0]
        self.assertEqual(set(doctor), {"name", "specializations", "tagline", "links"})
        self.assertEqual(doctor["name"], "Dr A")
        self.assertEqual(doctor["specializations"], ["Dermatology", "Laser"])
        self.assertEqual(doctor["tagline"], "Skin and laser")
        self.assertEqual(doctor["links"][0]["kind"], "facebook")

    def test_nothing_internal_about_the_doctor_leaks(self):
        self.publish("Dr A")
        body = str(self.about())
        for secret in ("AB-1", "secret.local", "salary", "commission", str(self.doctor("Dr A").uuid)):
            self.assertNotIn(secret, body)

    def test_a_stopped_doctor_is_not_shown_even_when_switched_on(self):
        self.publish("Dr Stopped")
        self.assertNotIn("Dr Stopped", str(self.about()))

    def test_a_visiting_doctor_appears_under_each_clinic_they_work_in(self):
        self.publish("Dr Linked")
        alpha, beta = self.branch_public("Alpha"), self.branch_public("Beta")
        self.assertEqual([d["name"] for d in alpha["doctors"]], ["Dr Linked"])
        self.assertEqual([d["name"] for d in beta["doctors"]], ["Dr Linked"])

    def test_a_specialty_the_clinic_hid_is_hidden_on_its_doctors_too(self):
        self.publish("Dr A")
        self.login("admin-a")
        patch(self.client, reverse("api:about-detail", args=[self.a.uuid]),
              {"hidden_specializations": [str(self.laser.uuid)]})
        self.assertEqual(self.branch_public("Alpha")["doctors"][0]["specializations"], ["Dermatology"])

    def test_a_clinic_left_out_of_about_shows_no_doctors(self):
        self.publish("Dr B")
        self.login("owner")
        patch(self.client, reverse("api:about-detail", args=[self.b.uuid]), {"about_visible": False})
        self.assertNotIn("Dr B", str(self.about()))

    def test_only_management_can_switch_a_doctor_on(self):
        target = self.doctor("Dr A")
        url = reverse("api:employee-detail", args=[target.uuid])
        for who in ("rec", "doc"):
            self.login(who)
            self.assertEqual(patch(self.client, url, {"show_publicly": True}).status_code, 403, who)
        self.login("admin-a")
        self.assertEqual(patch(self.client, url, {"show_publicly": True}).status_code, 200)
        target.refresh_from_db()
        self.assertTrue(target.show_publicly)


class MediaApprovalTests(PublicPageBase):
    def test_an_admins_upload_waits_and_is_not_public(self):
        self.login("admin-a")
        response = self.upload(self.branch_url(self.a), logo=picture(), cover=picture(size=(120, 40)))
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["status"], "pending")
        self.assertTrue(body["pending_logo"] and body["pending_cover"])
        self.assertIsNone(body["logo"])
        alpha = self.branch_public("Alpha")
        self.assertIsNone(alpha["logo"])
        self.assertIsNone(alpha["cover"])
        self.assertNotIn("pending", str(self.about()))

    def test_the_owner_approves_and_it_goes_public(self):
        self.login("admin-a")
        self.upload(self.branch_url(self.a), logo=picture())
        self.login("owner")
        response = self.client.post(reverse("api:public-media-review", args=[self.a.uuid]), {"decision": "approve"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], "")
        alpha = self.branch_public("Alpha")
        self.assertTrue(alpha["logo"].startswith("/media/public/branch/"))
        self.a.refresh_from_db()
        self.assertFalse(self.a.pending_public_logo)

    def test_the_owner_rejects_and_the_admin_sees_why(self):
        self.login("admin-a")
        self.upload(self.branch_url(self.a), cover=picture())
        self.login("owner")
        self.client.post(reverse("api:public-media-review", args=[self.a.uuid]),
                         {"decision": "reject", "note": "Blurry"})
        self.assertIsNone(self.branch_public("Alpha")["cover"])
        self.login("admin-a")
        row = self.client.get(reverse("api:public-media")).json()["branches"][0]
        self.assertEqual((row["status"], row["review_note"], row["pending_cover"]), ("rejected", "Blurry", None))

    def test_an_admin_cannot_approve_their_own_upload(self):
        self.login("admin-a")
        self.upload(self.branch_url(self.a), logo=picture())
        response = self.client.post(reverse("api:public-media-review", args=[self.a.uuid]), {"decision": "approve"})
        self.assertEqual(response.status_code, 403)
        self.assertIsNone(self.branch_public("Alpha")["logo"])

    def test_the_owners_own_upload_is_live_at_once(self):
        self.login("owner")
        self.assertEqual(self.upload(self.branch_url(self.b), logo=picture()).status_code, 201)
        self.assertTrue(self.branch_public("Beta")["logo"])
        self.b.refresh_from_db()
        self.assertEqual(self.b.media_status, "")

    def test_an_admin_reaches_only_their_own_clinic(self):
        self.login("admin-a")
        self.assertEqual(self.upload(self.branch_url(self.b), logo=picture()).status_code, 404)
        self.assertEqual([b["name"] for b in self.client.get(reverse("api:public-media")).json()["branches"]], ["Alpha"])

    def test_reception_and_doctors_are_refused(self):
        for who in ("rec", "doc"):
            self.login(who)
            self.assertEqual(self.client.get(reverse("api:public-media")).status_code, 403, who)
            self.assertEqual(self.upload(self.branch_url(self.a), logo=picture()).status_code, 403, who)

    def test_an_admin_can_take_down_a_live_image_and_withdraw_a_waiting_one(self):
        self.login("owner")
        self.upload(self.branch_url(self.a), logo=picture())
        self.login("admin-a")
        self.upload(self.branch_url(self.a), cover=picture())
        withdraw = self.client.delete(reverse("api:public-media-branch-kind", args=[self.a.uuid, "cover"]) + "?pending=1")
        self.assertEqual(withdraw.status_code, 204)
        down = self.client.delete(reverse("api:public-media-branch-kind", args=[self.a.uuid, "logo"]))
        self.assertEqual(down.status_code, 204)
        self.assertIsNone(self.branch_public("Alpha")["logo"])
        self.a.refresh_from_db()
        self.assertEqual(self.a.media_status, "")

    def test_a_bad_file_is_refused(self):
        self.login("owner")
        url = self.branch_url(self.a)
        fake = SimpleUploadedFile("evil.png", b"<script>alert(1)</script>", content_type="image/png")
        self.assertEqual(self.upload(url, logo=fake).status_code, 400)
        svg = SimpleUploadedFile("x.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>", content_type="image/svg+xml")
        self.assertEqual(self.upload(url, logo=svg).status_code, 400)
        gif = picture(kind="GIF", name="x.gif")
        self.assertEqual(self.upload(url, logo=gif).status_code, 400)
        huge = SimpleUploadedFile("big.png", picture().read() + b"0" * (2 * 1024 * 1024), content_type="image/png")
        self.assertEqual(self.upload(url, logo=huge).status_code, 400)
        self.assertEqual(self.upload(url).status_code, 400)
        self.assertIsNone(self.branch_public("Alpha")["logo"])

    def test_the_stored_name_is_random_and_follows_the_real_format(self):
        self.login("owner")
        disguised = picture(kind="JPEG", name="../../etc/passwd.png")
        self.upload(self.branch_url(self.a), logo=disguised)
        url = self.branch_public("Alpha")["logo"]
        self.assertTrue(url.endswith(".jpg"), url)
        self.assertNotIn("passwd", url)

    def test_a_clinic_of_another_group_cannot_be_reviewed_or_touched(self):
        rival = Tenant.objects.create(name="Rival", slug="rival-media", status=Tenant.Status.ACTIVE)
        provision_tenant_defaults(rival)
        with tenant_context(rival):
            theirs = Branch.all_objects.create(tenant=rival, name="Theirs", code="TH", media_status="pending")
        self.login("owner")
        self.assertEqual(self.client.post(reverse("api:public-media-review", args=[theirs.uuid]),
                                          {"decision": "approve"}).status_code, 404)
        self.assertEqual(self.upload(self.branch_url(theirs), logo=picture()).status_code, 404)


class GroupMediaTests(PublicPageBase):
    def test_the_owner_sets_the_groups_logo_and_cover_live(self):
        self.login("owner")
        response = self.upload(reverse("api:public-media-group"), logo=picture(), cover=picture(size=(300, 100)))
        self.assertEqual(response.status_code, 201, response.content)
        body = self.about()
        self.assertTrue(body["logo"].startswith("/media/public/group/"))
        self.assertTrue(body["cover"])

    def test_only_the_owner_may_set_it(self):
        self.login("admin-a")
        self.assertEqual(self.upload(reverse("api:public-media-group"), logo=picture()).status_code, 403)
        self.assertIsNone(self.about()["logo"])

    def test_the_owner_can_take_it_down(self):
        self.login("owner")
        self.upload(reverse("api:public-media-group"), logo=picture())
        self.assertEqual(self.client.delete(reverse("api:public-media-group-kind", args=["logo"])).status_code, 204)
        self.assertIsNone(self.about()["logo"])

    def test_the_groups_images_are_not_shown_on_another_groups_page(self):
        self.login("owner")
        self.upload(reverse("api:public-media-group"), logo=picture())
        rival = Tenant.objects.create(name="Rival", slug="rival-group", status=Tenant.Status.ACTIVE)
        provision_tenant_defaults(rival)
        self.client.logout()
        theirs = self.client.get(reverse("api:portal:about", kwargs={"slug": rival.slug})).json()
        self.assertIsNone(theirs["logo"])
