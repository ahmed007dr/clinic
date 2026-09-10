"""The patient portal's isolation boundary — docs/12 §3.

"The patient must only ever access their own data, even if they know another
patient's UUID." Every test here is a way of trying not to.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from appointments.models import Appointment
from branches.models import Branch
from medical.models import LabResult, Prescription, PrescriptionItem, Visit
from patients.models import Patient
from tenants.context import tenant_context
from tenants.models import Tenant

from .models import PortalInvitation

User = get_user_model()
PASSWORD = "portal-pass-1"


class PortalBase(TestCase):
    def setUp(self):
        cache.clear()  # the login throttle is cache-backed and outlives a test
        self.a = Tenant.objects.first()
        self.b = Tenant.objects.create(name="Other", slug="other-portal", status=Tenant.Status.ACTIVE)
        with tenant_context(self.a):
            self.branch = Branch.all_objects.create(tenant=self.a, name="Main", code="MN")
            self.alice = Patient.all_objects.create(
                tenant=self.a, name="Alice", branch=self.branch, phone1="010 0000 0001"
            )
            self.bob = Patient.all_objects.create(
                tenant=self.a, name="Bob", branch=self.branch, phone1="01000000002"
            )
            alice_visit = Visit.all_objects.create(
                tenant=self.a, patient=self.alice, branch=self.branch, diagnosis="Alice dx"
            )
            bob_visit = Visit.all_objects.create(
                tenant=self.a, patient=self.bob, branch=self.branch, diagnosis="Bob dx"
            )
            self.alice_rx = Prescription.all_objects.create(tenant=self.a, patient=self.alice, visit=alice_visit)
            PrescriptionItem.all_objects.create(tenant=self.a, prescription=self.alice_rx, medication="Alice med")
            self.bob_rx = Prescription.all_objects.create(tenant=self.a, patient=self.bob, visit=bob_visit)
            PrescriptionItem.all_objects.create(tenant=self.a, prescription=self.bob_rx, medication="Bob med")
            self.released = LabResult.all_objects.create(
                tenant=self.a, patient=self.alice, branch=self.branch,
                test_name="Released", released_to_patient=True,
            )
            self.hidden = LabResult.all_objects.create(
                tenant=self.a, patient=self.alice, branch=self.branch, test_name="Hidden"
            )
            LabResult.all_objects.create(
                tenant=self.a, patient=self.bob, branch=self.branch,
                test_name="Bob released", released_to_patient=True,
            )
        with tenant_context(self.b):
            b_branch = Branch.all_objects.create(tenant=self.b, name="B", code="B")
            # Same phone as Alice, at another clinic.
            self.carol = Patient.all_objects.create(
                tenant=self.b, name="Carol", branch=b_branch, phone1="01000000001"
            )

    def url(self, name, tenant=None, **kwargs):
        return reverse(f"api:portal:{name}", kwargs={"slug": (tenant or self.a).slug, **kwargs})

    def invite(self, patient, tenant=None):
        with tenant_context(tenant or self.a):
            _, token = PortalInvitation.issue(patient)
        return token

    def enrol(self, patient, tenant=None, client=None):
        client = client or self.client
        response = client.post(
            self.url("accept-invite", tenant),
            {"token": self.invite(patient, tenant), "password": PASSWORD},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        return client

    def login(self, phone, password=PASSWORD, tenant=None):
        return self.client.post(
            self.url("login", tenant), {"phone": phone, "password": password},
            content_type="application/json",
        )


class EnrolmentTests(PortalBase):
    def test_an_invitation_enrols_the_patient_once(self):
        token = self.invite(self.alice)
        first = self.client.post(self.url("accept-invite"), {"token": token, "password": PASSWORD},
                                 content_type="application/json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(self.client.get(self.url("me")).json()["name"], "Alice")
        again = self.client.post(self.url("accept-invite"), {"token": token, "password": "another-pass"},
                                 content_type="application/json")
        self.assertEqual(again.status_code, 400)

    def test_an_expired_invitation_is_refused(self):
        token = self.invite(self.alice)
        with tenant_context(self.a):
            PortalInvitation.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        response = self.client.post(self.url("accept-invite"), {"token": token, "password": PASSWORD},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_login_by_phone_ignores_formatting(self):
        self.enrol(self.alice)
        self.client.post(self.url("logout"))
        self.assertEqual(self.login("01000000001").status_code, 200)

    def test_an_unknown_phone_and_a_wrong_password_look_the_same(self):
        self.enrol(self.alice)
        self.client.post(self.url("logout"))
        unknown = self.login("01999999999")
        wrong = self.login("01000000001", "not-the-password")
        self.assertEqual(unknown.status_code, wrong.status_code)
        self.assertEqual(unknown.json(), wrong.json())

    def test_repeated_failures_lock_the_account(self):
        self.enrol(self.alice)
        self.client.post(self.url("logout"))
        for _ in range(5):
            self.login("01000000001", "wrong-password")
        self.assertEqual(self.login("01000000001").status_code, 429)


class IsolationTests(PortalBase):
    def setUp(self):
        super().setUp()
        self.enrol(self.alice)

    def test_a_patient_lists_only_their_own_prescriptions(self):
        uuids = {row["uuid"] for row in self.client.get(self.url("prescriptions")).json()}
        self.assertEqual(uuids, {str(self.alice_rx.uuid)})

    def test_another_patients_uuid_is_indistinguishable_from_a_missing_one(self):
        import uuid as uuid_module

        foreign = self.client.get(self.url("prescription", uuid=self.bob_rx.uuid))
        missing = self.client.get(self.url("prescription", uuid=uuid_module.uuid4()))
        self.assertEqual(foreign.status_code, 404)
        self.assertEqual(foreign.status_code, missing.status_code)
        self.assertEqual(foreign.json(), missing.json())
        self.assertNotIn("Bob", foreign.content.decode())

    def test_unreleased_results_are_invisible(self):
        names = {row["test_name"] for row in self.client.get(self.url("lab-results")).json()}
        self.assertEqual(names, {"Released"})

    def test_the_diagnosis_is_hidden_until_the_clinic_shares_it(self):
        visits = self.client.get(self.url("visits")).json()
        self.assertEqual({v["diagnosis"] for v in visits}, {None})
        self.a.portal_show_diagnosis = True
        self.a.save(update_fields=["portal_show_diagnosis"])
        visits = self.client.get(self.url("visits")).json()
        self.assertEqual({v["diagnosis"] for v in visits}, {"Alice dx"})

    def test_a_portal_session_is_not_a_staff_session(self):
        self.assertIn(self.client.get(reverse("api:patient-list")).status_code, (401, 403))

    def test_a_session_from_one_clinic_is_refused_by_another(self):
        """The test client sends the cookie to every path, so this is the
        server's own check and not the browser's cookie scoping."""
        self.assertEqual(self.client.get(self.url("me", self.b)).status_code, 401)

    def test_changing_the_phone_ends_the_session(self):
        with tenant_context(self.a):
            self.alice.phone1 = "01111111111"
            self.alice.save()
        self.assertEqual(self.client.get(self.url("me")).status_code, 401)

    def test_logging_out_ends_the_session(self):
        cookie = self.client.cookies["portal_session"].value
        self.client.post(self.url("logout"))
        self.client.cookies["portal_session"] = cookie  # replaying the old token
        self.assertEqual(self.client.get(self.url("me")).status_code, 401)

    def test_a_suspended_clinic_closes_its_portal(self):
        self.a.status = Tenant.Status.SUSPENDED
        self.a.save(update_fields=["status"])
        self.assertEqual(self.client.get(self.url("me")).status_code, 403)


class StaffSessionTests(PortalBase):
    def test_a_staff_session_means_nothing_to_the_portal(self):
        with tenant_context(self.a):
            role, _ = ClinicRole.all_objects.get_or_create(tenant=self.a, name="Admin")
        User.objects.create_user(username="adm", email="adm-p@t.local", password="pass12345",
                                 tenant=self.a, role=role, branch=self.branch)
        self.client.login(email="adm-p@t.local", password="pass12345")
        self.assertEqual(self.client.get(self.url("me")).status_code, 401)

    def test_portal_writes_require_the_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(self.url("login"), {"phone": "1", "password": "x"},
                               content_type="application/json")
        self.assertEqual(response.status_code, 403)


class RequestTests(PortalBase):
    def setUp(self):
        super().setUp()
        self.enrol(self.alice)

    def test_a_request_reaches_reception_as_requested(self):
        when = (timezone.now() + timedelta(days=2)).replace(microsecond=0).isoformat()
        response = self.client.post(self.url("appointments"), {"scheduled_date": when, "notes": "pain"},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 201, response.content)
        with tenant_context(self.a):
            self.assertTrue(
                Appointment.all_objects.filter(patient=self.alice, status="requested").exists()
            )

    def test_the_audit_trail_names_the_patient_not_a_staff_user(self):
        """Regression: a portal write reached the audit signal with the patient
        principal as `request.user` (DRF copies it onto the Django request), and
        `AuditLog.user` — a staff foreign key — rejected it with a 500."""
        from audit.models import AuditLog

        when = (timezone.now() + timedelta(days=2)).replace(microsecond=0).isoformat()
        self.client.post(self.url("appointments"), {"scheduled_date": when},
                         content_type="application/json")
        with tenant_context(self.a):
            entry = AuditLog._default_manager.filter(
                model_name="appointment", action="create"
            ).order_by("-created_at").first()
        self.assertIsNotNone(entry)
        self.assertIsNone(entry.user_id)
        self.assertIn(f"[portal] patient {self.alice.serial_number}", entry.description)

    def test_a_request_for_the_past_is_refused(self):
        when = (timezone.now() - timedelta(days=1)).isoformat()
        response = self.client.post(self.url("appointments"), {"scheduled_date": when},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)


class StaffSideTests(PortalBase):
    def setUp(self):
        super().setUp()
        with tenant_context(self.a):
            roles = {n: ClinicRole.all_objects.get_or_create(tenant=self.a, name=n)[0]
                     for n in ("Reception", "Doctor", "Admin")}
        for name, role in roles.items():
            User.objects.create_user(username=name.lower(), email=f"{name.lower()}-ps@t.local",
                                     password="pass12345", tenant=self.a, role=role, branch=self.branch)
        self.staff = Client()

    def as_staff(self, role):
        self.staff.login(email=f"{role}-ps@t.local", password="pass12345")

    def test_reception_invites_and_the_link_works(self):
        self.as_staff("reception")
        response = self.staff.post(reverse("api:patient-portal-invite", args=[self.alice.uuid]))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response["Cache-Control"], "no-store")
        token = response.json()["url"].split("#", 1)[1]
        accepted = self.client.post(self.url("accept-invite"), {"token": token, "password": PASSWORD},
                                    content_type="application/json")
        self.assertEqual(accepted.status_code, 200)

    def test_an_invite_needs_a_phone(self):
        with tenant_context(self.a):
            self.bob.phone1 = ""
            self.bob.save()
        self.as_staff("reception")
        response = self.staff.post(reverse("api:patient-portal-invite", args=[self.bob.uuid]))
        self.assertEqual(response.status_code, 400)

    def test_only_clinicians_release_results(self):
        self.as_staff("reception")
        refused = self.staff.post(reverse("api:labresult-release", args=[self.hidden.uuid]),
                                  {"released": True}, content_type="application/json")
        self.assertEqual(refused.status_code, 403)

        self.as_staff("doctor")
        released = self.staff.post(reverse("api:labresult-release", args=[self.hidden.uuid]),
                                   {"released": True}, content_type="application/json")
        self.assertEqual(released.status_code, 200, released.content)

        self.enrol(self.alice)
        names = {row["test_name"] for row in self.client.get(self.url("lab-results")).json()}
        self.assertEqual(names, {"Released", "Hidden"})

    def test_only_an_admin_changes_the_diagnosis_setting(self):
        self.as_staff("doctor")
        self.assertEqual(self.staff.patch(reverse("api:clinic-settings"), {"portal_show_diagnosis": True},
                                          content_type="application/json").status_code, 403)
        self.as_staff("admin")
        response = self.staff.patch(reverse("api:clinic-settings"), {"portal_show_diagnosis": True},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.a.refresh_from_db()
        self.assertTrue(self.a.portal_show_diagnosis)
