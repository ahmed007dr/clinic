"""Creating a portal account, and the profile (docs/15, Phase 2).

The rule under test: a new account reaches an *existing* patient's file only
through a code sent to the e-mail **on that file** — a phone number and a name
are not proof. And nothing the endpoints answer tells a stranger whether a
patient exists.
"""

from django.core import mail
from django.core.cache import cache
from django.test import Client

from branches.models import Branch
from notifications.models import EmailLog
from patients.intake import RegistrationError, merge_registration
from patients.models import Patient
from tenants.context import tenant_context

from .models import CODE_MAX_ATTEMPTS, PatientAccount, PortalVerification
from .tests import PASSWORD, PortalBase

NEW_PASSWORD = "Str0ng-new-pass-9"


def code_in(message):
    return next(line for line in message.body.splitlines() if line.strip().isdigit()).strip()


class SignupBase(PortalBase):
    def setUp(self):
        super().setUp()
        self.a.portal_self_registration = True
        self.a.save()
        self.b.portal_self_registration = True
        self.b.save()
        with tenant_context(self.a):
            self.alice.email = "alice@file.example"
            self.alice.save()
        mail.outbox.clear()

    def form(self, **overrides):
        body = {
            "name": "Alice", "phone": "01000000001", "email": "typed@example.com",
            "password": NEW_PASSWORD, "gender": "female", "branch": str(self.branch.uuid),
            "consent": True,
        }
        body.update(overrides)
        return body

    def start(self, client=None, tenant=None, **overrides):
        return (client or self.client).post(
            self.url("account-start", tenant), self.form(**overrides), content_type="application/json"
        )

    def verify(self, ticket, code, client=None, tenant=None):
        return (client or self.client).post(
            self.url("account-verify", tenant), {"ticket": ticket, "code": code},
            content_type="application/json",
        )

    def start_and_verify(self, **overrides):
        ticket = self.start(**overrides).json()["ticket"]
        return self.verify(ticket, code_in(mail.outbox[-1]))

    def patients(self):
        with tenant_context(self.a):
            return Patient.objects.count()


class OpenSwitchTests(SignupBase):
    def test_closed_unless_the_group_turns_it_on(self):
        self.a.portal_self_registration = False
        self.a.save()
        self.assertEqual(self.start().status_code, 404)
        self.assertEqual(self.verify("x", "123456").status_code, 404)
        self.assertEqual(len(mail.outbox), 0)

    def test_the_form_is_validated(self):
        for bad in (
            {"consent": False}, {"password": "short"}, {"password": "01000000001"},
            {"phone": "12"}, {"email": "not-an-email"}, {"gender": "x"}, {"branch": "not-a-uuid"},
            {"birth_date": "2999-01-01"},
        ):
            with self.subTest(bad=bad):
                self.assertEqual(self.start(**bad).status_code, 400)
        self.assertEqual(len(mail.outbox), 0)

    def test_the_clinic_must_be_one_of_this_groups_running_clinics(self):
        with tenant_context(self.b):
            theirs = Branch.all_objects.create(tenant=self.b, name="B2", code="B2")
        self.assertEqual(self.start(branch=str(theirs.uuid)).status_code, 400)
        self.branch.is_active = False
        self.branch.save()
        self.assertEqual(self.start(name="Zed", phone="01555555555").status_code, 400)


class NewPersonTests(SignupBase):
    def test_a_new_person_confirms_the_typed_address_and_lands_in_quarantine(self):
        response = self.start(name="Nadia Farid", phone="01222222222", email="nadia@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([m.to for m in mail.outbox], [["nadia@example.com"]])
        before = self.patients()
        done = self.verify(response.json()["ticket"], code_in(mail.outbox[-1]))
        self.assertEqual(done.status_code, 200, done.content)
        self.assertEqual(done.json()["name"], "Nadia Farid")
        with tenant_context(self.a):
            patient = Patient.objects.get(name="Nadia Farid")
            self.assertEqual(self.patients(), before + 1)
            self.assertTrue(patient.needs_review)
            self.assertEqual(patient.registration_source, Patient.RegistrationSource.PORTAL)
            self.assertEqual((patient.email, patient.phone1, patient.branch), ("nadia@example.com", "01222222222", self.branch))
            self.assertIsNotNone(patient.consent_data_processing_at)
            self.assertTrue(patient.portal_account.check_password(NEW_PASSWORD))
        # They are signed in.
        self.assertEqual(self.client.get(self.url("me")).status_code, 200)

    def test_the_code_works_once_and_guesses_are_limited(self):
        ticket = self.start(name="Nadia Farid", phone="01222222222").json()["ticket"]
        code = code_in(mail.outbox[-1])
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(CODE_MAX_ATTEMPTS):
            self.assertEqual(self.verify(ticket, wrong).status_code, 400)
        # Voided by the guesses: even the right code no longer works.
        self.assertEqual(self.verify(ticket, code).status_code, 400)

        ticket = self.start(name="Nadia Farid", phone="01222222222").json()["ticket"]
        code = code_in(mail.outbox[-1])
        self.assertEqual(self.verify(ticket, code).status_code, 200)
        self.assertEqual(self.verify(ticket, code, client=Client()).status_code, 400)

    def test_a_wrong_ticket_or_no_ticket_is_refused_the_same_way(self):
        self.start()
        code = code_in(mail.outbox[-1])
        first = self.verify("not-a-ticket", code)
        second = self.verify("", code)
        self.assertEqual((first.status_code, first.json()), (second.status_code, second.json()))

    def test_the_code_is_never_kept_in_the_email_log(self):
        self.start(name="Nadia Farid", phone="01222222222")
        code = code_in(mail.outbox[-1])
        with tenant_context(self.a):
            rows = list(EmailLog.objects.filter(kind="portal_signup_code"))
        self.assertEqual(len(rows), 1)
        self.assertNotIn(code, rows[0].body)
        self.assertNotIn(code, rows[0].subject)

    def test_one_address_cannot_be_flooded_with_codes(self):
        for _ in range(8):
            response = self.start(name="Nadia Farid", phone="01222222222", email="flood@example.com")
            self.assertEqual(response.status_code, 200)
            self.assertIn("ticket", response.json())
        self.assertEqual(len(mail.outbox), 5)


class LinkingTests(SignupBase):
    """The security rule: the code goes to the address on the patient's file."""

    def test_an_existing_patient_is_reached_only_through_the_address_on_their_file(self):
        before = self.patients()
        response = self.start(email="attacker@example.com")
        self.assertEqual(response.status_code, 200)
        # Nothing went to the address just typed.
        self.assertEqual([m.to for m in mail.outbox], [["alice@file.example"]])
        done = self.verify(response.json()["ticket"], code_in(mail.outbox[-1]))
        self.assertEqual(done.status_code, 200, done.content)
        self.assertEqual(self.patients(), before)  # linked, not duplicated
        with tenant_context(self.a):
            self.assertTrue(PatientAccount.objects.get(patient=self.alice).check_password(NEW_PASSWORD))
            # The file's own e-mail is untouched by what was typed.
            self.alice.refresh_from_db()
            self.assertEqual(self.alice.email, "alice@file.example")
            self.assertFalse(self.alice.needs_review)

    def test_the_attacker_who_only_knows_the_number_gets_nothing(self):
        response = self.start(email="attacker@example.com")
        # They never see the code, so they cannot finish; guesses do not work.
        for guess in ("123456", "654321", "000000"):
            self.assertEqual(self.verify(response.json()["ticket"], guess).status_code, 400)
        with tenant_context(self.a):
            self.assertFalse(PatientAccount.objects.filter(patient=self.alice).exists())

    def test_a_phone_number_alone_is_not_enough_a_different_name_starts_a_new_quarantined_file(self):
        before = self.patients()
        response = self.start(name="Someone Else", email="else@example.com")
        self.assertEqual([m.to for m in mail.outbox], [["else@example.com"]])
        self.verify(response.json()["ticket"], code_in(mail.outbox[-1]))
        with tenant_context(self.a):
            self.assertEqual(self.patients(), before + 1)
            self.assertFalse(PatientAccount.objects.filter(patient=self.alice).exists())
            self.assertTrue(Patient.objects.get(name="Someone Else").needs_review)

    def test_a_patient_with_no_email_on_file_cannot_be_verified_so_is_not_linked(self):
        with tenant_context(self.a):
            self.alice.email = ""
            self.alice.save()
        response = self.start(email="typed@example.com")
        self.assertEqual([m.to for m in mail.outbox], [["typed@example.com"]])
        self.verify(response.json()["ticket"], code_in(mail.outbox[-1]))
        with tenant_context(self.a):
            self.assertFalse(PatientAccount.objects.filter(patient=self.alice).exists())
            duplicate = Patient.objects.get(email="typed@example.com")
            self.assertTrue(duplicate.needs_review)

    def test_a_shared_number_and_name_is_ambiguous_so_is_not_linked(self):
        with tenant_context(self.a):
            Patient.all_objects.create(
                tenant=self.a, name="Alice", branch=self.branch, phone1="01000000001", email="twin@file.example"
            )
        self.start()
        self.assertEqual([m.to for m in mail.outbox], [["typed@example.com"]])

    def test_a_patient_still_waiting_for_review_is_never_a_target(self):
        with tenant_context(self.a):
            self.alice.needs_review = True
            self.alice.save()
        self.start()
        self.assertEqual([m.to for m in mail.outbox], [["typed@example.com"]])

    def test_the_answer_is_the_same_whether_or_not_a_patient_exists(self):
        known = self.start(email="one@example.com")
        unknown = self.start(name="Nobody Here", phone="01999999999", email="two@example.com")
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(set(known.json()), set(unknown.json()))
        self.assertEqual(known.json()["detail"], unknown.json()["detail"])

    def test_linking_signs_out_a_session_the_old_password_held(self):
        old = Client()
        self.enrol(self.alice, client=old)
        self.assertEqual(old.get(self.url("me")).status_code, 200)
        response = self.start()
        self.verify(response.json()["ticket"], code_in(mail.outbox[-1]))
        self.assertEqual(old.get(self.url("me")).status_code, 401)
        # The new password works; the old one does not.
        fresh = Client()
        self.assertEqual(
            fresh.post(self.url("login"), {"phone": "01000000001", "password": PASSWORD},
                       content_type="application/json").status_code, 400)
        self.assertEqual(
            fresh.post(self.url("login"), {"phone": "01000000001", "password": NEW_PASSWORD},
                       content_type="application/json").status_code, 200)


class GroupIsolationTests(SignupBase):
    def test_a_ticket_from_one_group_is_not_found_in_another(self):
        ticket = self.start().json()["ticket"]
        code = code_in(mail.outbox[-1])
        other = self.verify(ticket, code, tenant=self.b)
        self.assertEqual(other.status_code, 400)
        # ...and it still works where it belongs (the wrong-group try did not spend it).
        self.assertEqual(self.verify(ticket, code).status_code, 200)

    def test_a_signup_never_touches_another_groups_patient(self):
        # Carol, at the other group, has the same phone as Alice.
        self.start(name="Carol", email="carol.typed@example.com")
        self.assertEqual([m.to for m in mail.outbox], [["carol.typed@example.com"]])


class MergeTests(SignupBase):
    def test_merging_a_signup_into_the_file_it_duplicates_keeps_the_account(self):
        self.alice.refresh_from_db()
        with tenant_context(self.a):
            self.alice.email = ""
            self.alice.save()
        response = self.start(email="typed@example.com")
        self.verify(response.json()["ticket"], code_in(mail.outbox[-1]))
        with tenant_context(self.a):
            newcomer = Patient.objects.get(email="typed@example.com")
            merge_registration(newcomer, self.alice)
            account = PatientAccount.objects.get(patient=self.alice)
            self.assertTrue(account.check_password(NEW_PASSWORD))
            self.assertFalse(Patient.objects.filter(pk=newcomer.pk).exists())

    def test_only_a_pending_signup_can_be_merged_away(self):
        with tenant_context(self.a):
            with self.assertRaises(RegistrationError):
                merge_registration(self.bob, self.alice)


class ProfileTests(SignupBase):
    def setUp(self):
        super().setUp()
        self.enrol(self.alice)
        mail.outbox.clear()

    def patch(self, body, client=None):
        return (client or self.client).patch(self.url("profile"), body, content_type="application/json")

    def test_it_needs_a_portal_sign_in(self):
        self.assertEqual(Client().get(self.url("profile")).status_code, 401)
        self.assertEqual(Client().patch(self.url("profile"), {}, content_type="application/json").status_code, 401)

    def test_a_patient_reads_and_edits_their_contact_details(self):
        self.assertEqual(self.client.get(self.url("profile")).json()["name"], "Alice")
        response = self.patch({
            "address": "5 Nile St", "governorate": "Cairo", "area": "Maadi", "whatsapp": "0100 111 2222",
            "emergency_contact_name": "Sam", "emergency_contact_phone": "01000000009",
            "emergency_contact_relation": "Brother", "contact_by_email": True, "contact_by_sms": True,
        })
        self.assertEqual(response.status_code, 200, response.content)
        with tenant_context(self.a):
            self.alice.refresh_from_db()
            self.assertEqual((self.alice.address, self.alice.governorate, self.alice.whatsapp),
                             ("5 Nile St", "Cairo", "01001112222"))
            self.assertTrue(self.alice.contact_by_email and self.alice.contact_by_sms)

    def test_identity_and_clinic_fields_cannot_be_changed_from_here(self):
        response = self.patch({
            "name": "Mallory", "phone1": "01777777777", "email": "evil@example.com",
            "branch": "1", "needs_review": True, "national_id": "999", "notes": "x",
        })
        self.assertEqual(response.status_code, 200)
        with tenant_context(self.a):
            self.alice.refresh_from_db()
            self.assertEqual((self.alice.name, self.alice.phone1, self.alice.email), ("Alice", "010 0000 0001", "alice@file.example"))
            self.assertIsNone(self.alice.national_id)

    def test_a_bad_number_is_refused(self):
        self.assertEqual(self.patch({"whatsapp": "12"}).status_code, 400)

    def test_the_profile_is_only_the_signed_in_patients_own(self):
        other = Client()
        self.enrol(self.bob, client=other)
        self.assertEqual(other.get(self.url("profile")).json()["name"], "Bob")
        self.patch({"address": "Alice street"})
        self.assertNotEqual(other.get(self.url("profile")).json()["address"], "Alice street")


class EmailChangeFlowTests(SignupBase):
    def setUp(self):
        super().setUp()
        self.enrol(self.alice)
        mail.outbox.clear()

    def change(self, email, client=None):
        return (client or self.client).post(self.url("email-change"), {"email": email}, content_type="application/json")

    def confirm(self, ticket, code, client=None):
        return (client or self.client).post(
            self.url("email-change-verify"), {"ticket": ticket, "code": code}, content_type="application/json"
        )

    def test_the_new_address_is_proved_before_it_replaces_the_old(self):
        response = self.change("New@Example.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([m.to for m in mail.outbox], [["new@example.com"]])
        with tenant_context(self.a):
            self.alice.refresh_from_db()
            self.assertEqual(self.alice.email, "alice@file.example")  # not yet
        done = self.confirm(response.json()["ticket"], code_in(mail.outbox[-1]))
        self.assertEqual(done.status_code, 200, done.content)
        with tenant_context(self.a):
            self.alice.refresh_from_db()
            self.assertEqual(self.alice.email, "new@example.com")

    def test_a_wrong_code_changes_nothing(self):
        ticket = self.change("new@example.com").json()["ticket"]
        code = code_in(mail.outbox[-1])
        wrong = "000000" if code != "000000" else "111111"
        self.assertEqual(self.confirm(ticket, wrong).status_code, 400)
        with tenant_context(self.a):
            self.alice.refresh_from_db()
            self.assertEqual(self.alice.email, "alice@file.example")

    def test_another_patients_ticket_is_not_found(self):
        ticket = self.change("new@example.com").json()["ticket"]
        code = code_in(mail.outbox[-1])
        bob = Client()
        self.enrol(self.bob, client=bob)
        self.assertEqual(self.confirm(ticket, code, client=bob).status_code, 400)
        with tenant_context(self.a):
            self.bob.refresh_from_db()
            self.assertFalse(self.bob.email)

    def test_the_same_address_or_a_bad_one_is_refused(self):
        self.assertEqual(self.change("alice@file.example").status_code, 400)
        self.assertEqual(self.change("nope").status_code, 400)
        self.assertEqual(len(mail.outbox), 0)
