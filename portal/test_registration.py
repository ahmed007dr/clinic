"""Public self-registration and its review by the front desk."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import ClinicRole
from branches.models import Branch
from medical.models import PatientIntake
from patients.models import Patient
from subscriptions.models import Subscription
from tenants.context import tenant_context
from tenants.models import Tenant

User = get_user_model()
PASSWORD = "pass12345"

FORM = {
    "personal": {"name": "Online Person", "gender": "male", "phone1": "01022223333"},
    "visit": {"case_type": "acute", "reason_for_visit": "Fever for three days"},
    "consent": {"data_processing": True},
}


class SelfRegistrationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            role, _ = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name="Reception")
            self.a = Branch.all_objects.create(tenant=self.tenant, name="Clinic A", code="RA")
            self.b = Branch.all_objects.create(tenant=self.tenant, name="Clinic B", code="RB")
            self.known = Patient.all_objects.create(tenant=self.tenant, name="Known", branch=self.a,
                                                    phone1="01022223333")
        User.objects.create_user(username="desk", email="desk@reg.local", password=PASSWORD,
                                 tenant=self.tenant, role=role, branch=self.a)
        self.public = Client()

    def open_registration(self):
        self.tenant.portal_self_registration = True
        self.tenant.save(update_fields=["portal_self_registration"])

    def url(self, name):
        return reverse(f"api:portal:{name}", kwargs={"slug": self.tenant.slug})

    def submit(self, **personal):
        form = {**FORM, "personal": {**FORM["personal"], "branch": str(self.a.uuid), **personal}}
        return self.public.post(self.url("register"), form, content_type="application/json")

    def pending(self):
        with tenant_context(self.tenant):
            return Patient.all_objects.filter(tenant=self.tenant, needs_review=True).first()

    def test_closed_unless_the_group_opens_it(self):
        self.assertEqual(self.public.get(self.url("register-options")).status_code, 404)
        self.assertEqual(self.submit().status_code, 404)
        self.assertIsNone(self.pending())

    def test_a_submission_is_quarantined_for_review(self):
        self.open_registration()
        options = self.public.get(self.url("register-options")).json()
        self.assertIn("Clinic A", [b["name"] for b in options["branches"]])
        self.assertEqual(self.submit(phone1="01099990000").status_code, 201)
        patient = self.pending()
        self.assertEqual(patient.registration_source, "portal")
        with tenant_context(self.tenant):
            self.assertEqual(PatientIntake.all_objects.get(patient=patient).source, "portal")

    def test_a_pending_submission_waits_on_the_review_list_not_the_patient_list(self):
        self.open_registration()
        self.assertEqual(self.submit(phone1="01099990000").status_code, 201)
        self.client.login(email="desk@reg.local", password=PASSWORD)
        listed = self.client.get(reverse("api:patient-list")).json()["results"]
        waiting = self.client.get(reverse("api:patient-list"), {"needs_review": "1"}).json()["results"]
        self.assertNotIn("Online Person", [p["name"] for p in listed])
        self.assertEqual([p["name"] for p in waiting], ["Online Person"])

    def test_the_answer_never_reveals_an_existing_patient(self):
        self.open_registration()
        known = self.submit()                       # same phone as an existing patient
        unknown = self.submit(phone1="01077776666")
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known.json(), unknown.json())

    def test_pending_submissions_do_not_use_up_the_plan(self):
        self.open_registration()
        with tenant_context(self.tenant):
            plan = Subscription.all_objects.filter(tenant=self.tenant, status="active").first().plan
            plan.max_patients = Patient.all_objects.filter(tenant=self.tenant, needs_review=False).count()
            plan.save(update_fields=["max_patients"])
        self.assertEqual(self.submit(phone1="01055554444").status_code, 201)
        self.client.login(email="desk@reg.local", password=PASSWORD)
        confirm = self.client.post(reverse("api:patient-confirm-registration", args=[self.pending().uuid]))
        self.assertEqual(confirm.status_code, 403)   # counted at confirmation

    def test_the_public_form_cannot_point_at_an_existing_patient(self):
        self.open_registration()
        form = {**FORM, "personal": {**FORM["personal"], "branch": str(self.a.uuid), "phone1": "01012121212"},
                "referral": {"referral_source": "existing_patient", "referred_by_patient": str(self.known.uuid)}}
        self.assertEqual(self.public.post(self.url("register"), form, content_type="application/json").status_code, 201)
        self.assertIsNone(self.pending().referred_by_patient_id)

    def test_it_needs_the_csrf_token(self):
        self.open_registration()
        strict = Client(enforce_csrf_checks=True)
        response = strict.post(self.url("register"), FORM, content_type="application/json")
        self.assertEqual(response.status_code, 403)

    # ------------------------------------------------------------ review

    def test_review_shows_the_likely_duplicate_and_merge_folds_it_in(self):
        self.open_registration()
        self.submit()
        pending = self.pending()
        self.client.login(email="desk@reg.local", password=PASSWORD)
        review = self.client.get(reverse("api:patient-review", args=[pending.uuid])).json()
        self.assertEqual([d["uuid"] for d in review["duplicates"]], [str(self.known.uuid)])

        merged = self.client.post(reverse("api:patient-merge-into", args=[pending.uuid]),
                                  {"target": str(self.known.uuid)}, content_type="application/json")
        self.assertEqual(merged.status_code, 200, merged.content)
        with tenant_context(self.tenant):
            self.assertFalse(Patient.all_objects.filter(pk=pending.pk).exists())
            self.assertTrue(PatientIntake.all_objects.filter(patient=self.known).exists())

    def test_confirm_and_reject(self):
        self.open_registration()
        self.submit(phone1="01033334444")
        self.client.login(email="desk@reg.local", password=PASSWORD)
        pending = self.pending()
        self.assertEqual(self.client.post(reverse("api:patient-confirm-registration", args=[pending.uuid])).status_code, 200)
        pending.refresh_from_db()
        self.assertFalse(pending.needs_review)

        self.submit(phone1="01044445555")
        rejected = self.pending()
        self.assertEqual(self.client.post(reverse("api:patient-reject-registration", args=[rejected.uuid])).status_code, 204)
        with tenant_context(self.tenant):
            self.assertFalse(Patient.all_objects.filter(pk=rejected.pk).exists())

    def test_another_clinics_desk_cannot_review_it(self):
        self.open_registration()
        self.submit(phone1="01066667777", branch=str(self.b.uuid))
        self.client.login(email="desk@reg.local", password=PASSWORD)  # desk of Clinic A
        pending = self.pending()
        self.assertEqual(self.client.post(reverse("api:patient-confirm-registration", args=[pending.uuid])).status_code, 404)
