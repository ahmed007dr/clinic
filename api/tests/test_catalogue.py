"""Service → clinics → doctors (docs/15, Phase 3, D9).

The public catalogue must tell a customer only what can really be booked: a
clinic that does not offer a service never appears under it, and a doctor
appears under a clinic only when they work there, are under contract for the
service with a valid price, and management has switched both the doctor and the
service on. Neither a contract alone nor a switch alone is enough.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.migrations.executor import MigrationExecutor
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from accounts.models import ClinicRole
from billing.models import DoctorServiceRate
from branches.models import Branch
from employees.models import Employee, EmployeeType, Specialization
from importlib import import_module
from services.catalog import offerings, resolve_offering
from services.models import BranchService, Service
from tenants.context import tenant_context
from tenants.models import Tenant
from tenants.provisioning import provision_tenant_defaults
from tenants.testing import act_as_tenant

User = get_user_model()


class CatalogueBase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        act_as_tenant(self, self.tenant)
        provision_tenant_defaults(self.tenant)
        self.a = Branch.all_objects.create(tenant=self.tenant, name="Clinic A", code="CA", address="1 Nile")
        self.b = Branch.all_objects.create(tenant=self.tenant, name="Clinic B", code="CB")
        self.c = Branch.all_objects.create(tenant=self.tenant, name="Clinic C", code="CC")
        self.doctor_type = EmployeeType.all_objects.get(tenant=self.tenant, name="Doctor")
        self.derma = Specialization.all_objects.create(tenant=self.tenant, name="Dermatology")

        def role(name):
            return ClinicRole.all_objects.get(tenant=self.tenant, name=name)

        def user(username, role_name, branch, employee=None, active=True):
            return User.objects.create_user(
                username=username, email=f"{username}@cat.local", password="pass12345",
                tenant=self.tenant, role=role(role_name), branch=branch, employee=employee, is_active=active,
            )

        self.make_user = user
        self.owner = user("owner", "Owner", self.a)
        self.admin_a = user("admin-a", "Admin", self.a)
        self.reception = user("rec", "Reception", self.a)

        self.laser = Service.all_objects.create(
            tenant=self.tenant, name="Laser Hair Removal", base_price=Decimal("400"), duration_minutes=45,
            specialization=self.derma,
        )
        # The example from the brief: A has two doctors, B one, C none.
        self.ahmed = self.doctor("Dr Ahmed", "N1", self.a, price="500")
        self.sara = self.doctor("Dr Sara", "N2", self.a, price="600")
        self.mohamed = self.doctor("Dr Mohamed", "N3", self.b, price="450")
        self.switch(self.a)
        self.switch(self.b)

    def doctor(self, name, national_id, branch, *, service=None, price=None, show=True, rate=True,
               rate_active=True, extra=(), login=True, login_active=True, kind=None):
        service = service or self.laser
        employee = Employee.all_objects.create(
            tenant=self.tenant, name=name, branch=branch, employee_type=kind or self.doctor_type,
            national_id=national_id, salary_value=9999, email=f"{national_id}@secret.local",
            commission_percent=Decimal("40"), show_publicly=show,
            public_profile={"tagline": f"About {name}"},
        )
        employee.extra_branches.set(extra)
        employee.specializations.set([self.derma])
        if login:
            self.make_user(f"u-{national_id}", "Doctor", branch, employee=employee, active=login_active)
        if rate:
            DoctorServiceRate.all_objects.create(
                tenant=self.tenant, doctor=employee, service=service,
                price=Decimal(price) if price is not None else None, commission_percent=Decimal("30"),
                is_active=rate_active,
            )
        return employee

    def switch(self, branch, service=None, **fields):
        service = service or self.laser
        return BranchService.all_objects.update_or_create(
            tenant=self.tenant, branch=branch, service=service, defaults=fields
        )[0]

    def login(self, username):
        self.client.logout()
        self.assertTrue(self.client.login(email=f"{username}@cat.local", password="pass12345"))

    # ---- public calls

    def url(self, name, **kwargs):
        return reverse(f"api:portal:{name}", kwargs={"slug": self.tenant.slug, **kwargs})

    def services(self):
        self.client.logout()
        return self.client.get(self.url("catalog-services")).json()

    def branches(self, service=None):
        self.client.logout()
        return self.client.get(self.url("catalog-branches", service=(service or self.laser).uuid))

    def doctors(self, branch, service=None):
        self.client.logout()
        return self.client.get(self.url("catalog-doctors", service=(service or self.laser).uuid, branch=branch.uuid))

    def branch_names(self, service=None):
        return [b["name"] for b in self.branches(service).json()["branches"]]

    def doctor_names(self, branch, service=None):
        return [d["name"] for d in self.doctors(branch, service).json()["doctors"]]


class TheBriefsExampleTests(CatalogueBase):
    def test_the_service_lists_only_the_clinics_that_offer_it(self):
        self.assertEqual(self.branch_names(), ["Clinic A", "Clinic B"])  # C never appears

    def test_a_clinic_lists_only_its_own_doctors_with_their_prices(self):
        a = self.doctors(self.a).json()["doctors"]
        self.assertEqual([(d["name"], d["price"]) for d in a], [("Dr Ahmed", "500.00"), ("Dr Sara", "600.00")])
        b = self.doctors(self.b).json()["doctors"]
        self.assertEqual([(d["name"], d["price"]) for d in b], [("Dr Mohamed", "450.00")])

    def test_a_clinic_that_does_not_offer_the_service_has_no_page_for_it(self):
        self.assertEqual(self.doctors(self.c).json()["doctors"], [])

    def test_the_service_row_carries_the_lowest_price_and_how_many_clinics(self):
        row = self.services()[0]
        self.assertEqual((row["name"], row["from_price"], row["branches_count"], row["duration_minutes"]),
                         ("Laser Hair Removal", "450.00", 2, 45))
        branches = {b["name"]: b for b in self.branches().json()["branches"]}
        self.assertEqual((branches["Clinic A"]["from_price"], branches["Clinic A"]["doctors_count"]), ("500.00", 2))
        self.assertEqual((branches["Clinic B"]["from_price"], branches["Clinic B"]["doctors_count"]), ("450.00", 1))


class WhatMakesAnOfferingTests(CatalogueBase):
    def test_a_contract_alone_does_not_make_a_clinic_offer_the_service(self):
        # Clinic C has a contracted, public doctor — but nobody switched the service on there.
        self.doctor("Dr Cee", "N4", self.c, price="300")
        self.assertNotIn("Clinic C", self.branch_names())
        self.assertEqual(self.doctor_names(self.c), [])

    def test_a_switch_alone_does_not_put_an_unqualified_doctor_in_front_of_a_customer(self):
        self.switch(self.c)  # offered at C, but no doctor is contracted there
        self.assertNotIn("Clinic C", self.branch_names())
        self.assertEqual(self.doctor_names(self.c), [])

    def test_switching_the_service_off_takes_the_clinic_off_the_page_and_keeps_the_contracts(self):
        self.switch(self.b, is_active=False)
        self.assertEqual(self.branch_names(), ["Clinic A"])
        self.assertTrue(DoctorServiceRate.all_objects.filter(doctor=self.mohamed, is_active=True).exists())
        self.switch(self.b, is_active=True)
        self.assertEqual(self.branch_names(), ["Clinic A", "Clinic B"])

    def test_offered_but_not_bookable_online_is_not_listed(self):
        self.switch(self.b, online_bookable=False)
        self.assertEqual(self.branch_names(), ["Clinic A"])

    def test_a_doctor_who_did_not_agree_to_be_shown_is_not_offered(self):
        Employee.all_objects.filter(pk=self.sara.pk).update(show_publicly=False)
        self.assertEqual(self.doctor_names(self.a), ["Dr Ahmed"])

    def test_a_stopped_login_is_not_offered(self):
        User.objects.filter(employee=self.sara).update(is_active=False)
        self.assertEqual(self.doctor_names(self.a), ["Dr Ahmed"])

    def test_a_doctor_without_an_active_contract_line_is_not_offered(self):
        DoctorServiceRate.all_objects.filter(doctor=self.sara).update(is_active=False)
        self.assertEqual(self.doctor_names(self.a), ["Dr Ahmed"])
        self.doctor("Dr NoRate", "N5", self.a, rate=False)
        self.assertEqual(self.doctor_names(self.a), ["Dr Ahmed"])

    def test_staff_who_are_not_doctors_are_not_offered(self):
        nurse = EmployeeType.all_objects.create(tenant=self.tenant, name="Nurse")
        self.doctor("Nurse Nadia", "N6", self.a, price="100", kind=nurse)
        self.assertEqual(self.doctor_names(self.a), ["Dr Ahmed", "Dr Sara"])

    def test_a_visiting_doctor_is_offered_at_each_clinic_they_work_in(self):
        self.doctor("Dr Visit", "N7", self.a, price="700", extra=[self.b])
        self.assertIn("Dr Visit", self.doctor_names(self.a))
        self.assertIn("Dr Visit", self.doctor_names(self.b))

    def test_a_running_clinic_left_out_of_the_public_page_is_not_bookable(self):
        Branch.all_objects.filter(pk=self.b.pk).update(about_visible=False)
        self.assertEqual(self.branch_names(), ["Clinic A"])
        self.assertEqual(self.doctors(self.b).status_code, 404)

    def test_a_stopped_clinic_is_not_bookable(self):
        Branch.all_objects.filter(pk=self.b.pk).update(is_active=False)
        self.assertEqual(self.branch_names(), ["Clinic A"])

    def test_a_stopped_service_disappears_everywhere(self):
        Service.all_objects.filter(pk=self.laser.pk).update(is_active=False)
        self.assertEqual(self.services(), [])
        self.assertEqual(self.branches().status_code, 404)


class PriceTests(CatalogueBase):
    def test_no_contract_price_falls_back_to_the_catalogue_price(self):
        DoctorServiceRate.all_objects.filter(doctor=self.sara).update(price=None)
        prices = {d["name"]: d["price"] for d in self.doctors(self.a).json()["doctors"]}
        self.assertEqual(prices["Dr Sara"], "400.00")

    def test_a_service_with_no_valid_price_is_not_offered(self):
        free = Service.all_objects.create(tenant=self.tenant, name="Mystery", base_price=Decimal("0"))
        self.doctor("Dr Zero", "N8", self.a, service=free, price=None)
        self.switch(self.a, service=free)
        self.assertEqual(self.branches(free).status_code, 200)
        self.assertEqual(self.branch_names(free), [])
        self.assertNotIn("Mystery", [s["name"] for s in self.services()])

    def test_priced_after_evaluation_needs_no_figure_and_shows_none(self):
        consult = Service.all_objects.create(
            tenant=self.tenant, name="Assessment", base_price=Decimal("0"),
            price_display=Service.PriceDisplay.AFTER_EVALUATION,
        )
        self.doctor("Dr Eval", "N9", self.a, service=consult, price=None)
        self.switch(self.a, service=consult)
        row = next(s for s in self.services() if s["name"] == "Assessment")
        self.assertEqual((row["price_display"], row["from_price"]), ("after_evaluation", None))
        self.assertEqual([d["price"] for d in self.doctors(self.a, consult).json()["doctors"]], [None])

    def test_starting_from_is_reported_so_the_page_can_say_so(self):
        Service.all_objects.filter(pk=self.laser.pk).update(price_display="starting_from")
        self.assertEqual(self.services()[0]["price_display"], "starting_from")


class ResolveOfferingTests(CatalogueBase):
    """The server's own answer at booking time — the same rule as the lists."""

    def resolve(self, branch, doctor, service=None):
        with tenant_context(self.tenant):
            return resolve_offering(branch, doctor, service or self.laser)

    def test_a_listed_choice_resolves_with_its_price(self):
        offer = self.resolve(self.a, self.ahmed)
        self.assertEqual(offer.price, Decimal("500"))

    def test_a_doctor_of_another_clinic_does_not(self):
        self.assertIsNone(self.resolve(self.a, self.mohamed))

    def test_a_clinic_that_does_not_offer_it_does_not(self):
        self.doctor("Dr Cee", "N4", self.c, price="300")
        self.assertIsNone(self.resolve(self.c, Employee.all_objects.get(national_id="N4")))

    def test_missing_pieces_do_not(self):
        self.assertIsNone(self.resolve(None, self.ahmed))
        self.assertIsNone(self.resolve(self.a, None))

    def test_the_count_of_queries_does_not_grow_with_the_group(self):
        with tenant_context(self.tenant):
            with self.assertNumQueries(4):
                offerings()


class PublicSafetyTests(CatalogueBase):
    def test_it_is_public_and_read_only(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url("catalog-services")).status_code, 200)
        self.assertEqual(self.client.post(self.url("catalog-services"), {}).status_code, 405)

    def test_nothing_internal_leaks(self):
        body = str(self.services()) + self.branches().content.decode() + self.doctors(self.a).content.decode()
        for secret in ("secret.local", "9999", "commission", "N1", "national", "salary", "30.00", "40.00"):
            self.assertNotIn(secret, body)

    def test_a_doctors_public_line_is_shown_and_nothing_else_of_them(self):
        doctor = self.doctors(self.a).json()["doctors"][0]
        self.assertEqual(set(doctor), {"uuid", "name", "specializations", "tagline", "price"})
        self.assertEqual(doctor["tagline"], "About Dr Ahmed")

    def test_another_groups_services_are_never_shown_or_reachable(self):
        rival = Tenant.objects.create(name="Rival", slug="rival-cat", status=Tenant.Status.ACTIVE)
        provision_tenant_defaults(rival)
        with tenant_context(rival):
            theirs = Service.all_objects.create(tenant=rival, name="Their Secret", base_price=Decimal("10"))
        self.assertNotIn("Their Secret", str(self.services()))
        response = self.client.get(reverse("api:portal:catalog-branches", kwargs={"slug": self.tenant.slug, "service": theirs.uuid}))
        self.assertEqual(response.status_code, 404)
        stranger = self.client.get(reverse("api:portal:catalog-services", kwargs={"slug": rival.slug}))
        self.assertEqual(stranger.json(), [])


class StaffSwitchTests(CatalogueBase):
    def get(self, **params):
        return self.client.get(reverse("api:branch-services"), params)

    def put(self, **body):
        return self.client.put(reverse("api:branch-services"), body, content_type="application/json")

    def test_the_owner_sees_every_clinics_state_and_who_is_ready(self):
        self.login("owner")
        body = self.get(branch=self.a.uuid).json()
        self.assertEqual([b["name"] for b in body["branches"]], ["Clinic A", "Clinic B", "Clinic C"])
        row = next(s for s in body["services"] if s["name"] == "Laser Hair Removal")
        self.assertEqual((row["enabled"], row["online_bookable"], row["doctors_ready"]), (True, True, 2))
        empty = self.get(branch=self.c.uuid).json()["services"][0]
        self.assertEqual((empty["enabled"], empty["doctors_ready"]), (False, 0))

    def test_switching_a_service_on_in_a_clinic_lists_it_there_once_a_doctor_is_ready(self):
        self.doctor("Dr Cee", "N4", self.c, price="300")
        self.login("owner")
        self.assertEqual(self.put(branch=str(self.c.uuid), service=str(self.laser.uuid), enabled=True).status_code, 200)
        self.assertIn("Clinic C", self.branch_names())
        self.login("owner")
        self.put(branch=str(self.c.uuid), service=str(self.laser.uuid), enabled=False)
        self.assertNotIn("Clinic C", self.branch_names())

    def test_enabling_does_not_create_a_contract(self):
        self.login("owner")
        before = DoctorServiceRate.all_objects.count()
        self.put(branch=str(self.c.uuid), service=str(self.laser.uuid), enabled=True)
        self.assertEqual(DoctorServiceRate.all_objects.count(), before)

    def test_an_admin_manages_their_own_clinic_only(self):
        self.login("admin-a")
        own = self.get().json()
        self.assertEqual([b["name"] for b in own["branches"]], ["Clinic A"])
        self.assertEqual(self.put(branch=str(self.a.uuid), service=str(self.laser.uuid), online_bookable=False).status_code, 200)
        self.assertEqual(self.get(branch=self.b.uuid).status_code, 404)
        self.assertEqual(self.put(branch=str(self.b.uuid), service=str(self.laser.uuid), enabled=False).status_code, 404)
        self.assertTrue(BranchService.all_objects.get(branch=self.b, service=self.laser).is_active)

    def test_reception_is_refused(self):
        self.login("rec")
        self.assertEqual(self.get().status_code, 403)
        self.assertEqual(self.put(branch=str(self.a.uuid), service=str(self.laser.uuid), enabled=False).status_code, 403)

    def test_bad_input_is_refused(self):
        self.login("owner")
        self.assertEqual(self.put(branch=str(self.a.uuid), service=str(self.laser.uuid), enabled="yes").status_code, 400)
        self.assertEqual(self.put(branch=str(self.a.uuid), service="00000000-0000-0000-0000-000000000000").status_code, 404)

    def test_the_service_screen_can_set_duration_and_how_the_price_is_described(self):
        self.login("owner")
        response = self.client.patch(
            reverse("api:service-detail", args=[self.laser.uuid]),
            {"duration_minutes": 60, "price_display": "starting_from"}, content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.laser.refresh_from_db()
        self.assertEqual((self.laser.duration_minutes, self.laser.price_display), (60, "starting_from"))
        bad = self.client.patch(reverse("api:service-detail", args=[self.laser.uuid]),
                                {"duration_minutes": 1}, content_type="application/json")
        self.assertEqual(bad.status_code, 400)


class BackfillTests(CatalogueBase):
    """The migration switches on what each clinic already offers through its
    doctors' contracts — no more."""

    def test_it_enables_each_contracted_service_in_each_clinic_the_doctor_works_in(self):
        BranchService.all_objects.all().delete()
        self.doctor("Dr Visit", "N7", self.a, price="700", extra=[self.c])
        other = Service.all_objects.create(tenant=self.tenant, name="Peel", base_price=Decimal("100"))
        self.doctor("Dr Off", "N8", self.b, service=other, price="90", rate_active=False)  # inactive contract

        executor = MigrationExecutor(connection)
        state = executor.loader.project_state([
            ("services", "0007_branch_service_and_duration"),
            ("billing", "0008_doctor_contracts_commissions"),
            ("employees", "0011_employee_show_publicly"),
            ("tenants", "0021_tenant_public_media"),
        ])
        import_module("services.migrations.0008_backfill_branch_services").backfill(state.apps, None)

        pairs = set(BranchService.all_objects.values_list("branch__name", "service__name"))
        self.assertEqual(pairs, {
            ("Clinic A", "Laser Hair Removal"), ("Clinic B", "Laser Hair Removal"),
            ("Clinic C", "Laser Hair Removal"),  # the visiting doctor's second clinic
        })

        # Running it again adds nothing.
        import_module("services.migrations.0008_backfill_branch_services").backfill(state.apps, None)
        self.assertEqual(BranchService.all_objects.count(), 3)
