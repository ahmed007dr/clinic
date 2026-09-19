"""The public directory of clinic groups (docs/15, §10).

Three rules under test. A group is in the directory only when its Owner chose it
(default: not listed) and it is running. A card carries only what the group
already publishes on its own public page. And nothing crosses between groups:
one group's clinics, specialties and services never appear on another's card.
"""

from decimal import Decimal

from django.core.cache import cache
from django.urls import reverse

from api.tests.test_catalogue import CatalogueBase
from branches.models import Branch
from employees.models import Specialization
from services.models import Service
from tenants.context import tenant_context
from tenants.models import Tenant
from tenants.provisioning import provision_tenant_defaults


class DirectoryBase(CatalogueBase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)

    def list_group(self, listed=True, tenant=None):
        tenant = tenant or self.tenant
        Tenant.objects.filter(pk=tenant.pk).update(listed_in_directory=listed)
        cache.clear()

    def directory(self, **params):
        self.client.logout()
        response = self.client.get(reverse("api:directory"), params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def slugs(self, **params):
        return [card["slug"] for card in self.directory(**params)["results"]]

    def other_group(self, **fields):
        """A second running group with a clinic of its own that offers Botox."""
        other = Tenant.objects.create(name="Other Group", slug="other-group", status=Tenant.Status.ACTIVE, **fields)
        with tenant_context(other):
            provision_tenant_defaults(other)
            Branch.all_objects.create(tenant=other, name="Other Clinic", code="OC", address="9 Sea Rd")
            Specialization.all_objects.create(tenant=other, name="Cardiology")
            Service.all_objects.create(tenant=other, name="Botox", base_price=Decimal("900"))
        return other


class WhoIsListedTests(DirectoryBase):
    def test_nothing_is_listed_until_the_owner_chooses(self):
        self.assertFalse(self.tenant.listed_in_directory)
        self.assertEqual(self.slugs(), [])

    def test_a_listed_running_group_appears_with_its_public_card(self):
        self.list_group()
        (card,) = self.directory()["results"]
        self.assertEqual((card["slug"], card["name"]), (self.tenant.slug, self.tenant.name))
        self.assertEqual([c["name"] for c in card["clinics"]], ["Clinic A", "Clinic B", "Clinic C"])
        self.assertEqual(card["clinics"][0]["address"], "1 Nile")
        self.assertEqual(card["specialties"], ["Dermatology"])

    def test_a_group_that_is_not_running_is_never_listed(self):
        self.list_group()
        for status in (Tenant.Status.SUSPENDED, Tenant.Status.CANCELLED):
            with self.subTest(status=status):
                Tenant.objects.filter(pk=self.tenant.pk).update(status=status)
                cache.clear()
                self.assertEqual(self.slugs(), [])

    def test_a_group_with_no_public_clinic_is_left_out(self):
        self.list_group()
        Branch.all_objects.filter(tenant=self.tenant).update(about_visible=False)
        cache.clear()
        self.assertEqual(self.slugs(), [])
        Branch.all_objects.filter(tenant=self.tenant).update(about_visible=True, is_active=False)
        cache.clear()
        self.assertEqual(self.slugs(), [])

    def test_only_the_clinics_management_publishes_are_named(self):
        self.list_group()
        Branch.all_objects.filter(pk=self.c.pk).update(about_visible=False)
        Branch.all_objects.filter(pk=self.b.pk).update(is_active=False)
        cache.clear()
        (card,) = self.directory()["results"]
        self.assertEqual([c["name"] for c in card["clinics"]], ["Clinic A"])


class WhatACardShowsTests(DirectoryBase):
    def test_services_are_only_those_that_can_be_booked_with_their_lowest_price(self):
        self.list_group()
        (card,) = self.directory()["results"]
        self.assertEqual(card["services_count"], 1)
        # Dr Ahmed 500, Dr Sara 600, Dr Mohamed 450 — the lowest is shown.
        self.assertEqual(card["services"], [{"name": "Laser Hair Removal", "from_price": "450.00"}])

    def test_a_service_nobody_can_deliver_is_not_advertised(self):
        self.list_group()
        Service.all_objects.create(tenant=self.tenant, name="Botox", base_price=Decimal("900"))
        self.switch(self.a, Service.all_objects.get(name="Botox"))
        cache.clear()
        (card,) = self.directory()["results"]
        self.assertEqual([s["name"] for s in card["services"]], ["Laser Hair Removal"])

    def test_a_specialty_management_hid_is_not_shown(self):
        self.list_group()
        for branch in (self.a, self.b, self.c):
            branch.about_hidden_specialties.add(self.derma)
        cache.clear()
        (card,) = self.directory()["results"]
        self.assertEqual(card["specialties"], [])

    def test_nothing_private_leaves_the_server(self):
        self.list_group()
        text = self.client.get(reverse("api:directory")).content.decode()
        for secret in ("secret.local", "9999", "N1", "Dr Ahmed", "Dr Sara", "u-N1", "cat.local", "national"):
            self.assertNotIn(secret, text, secret)
        (card,) = self.directory()["results"]
        self.assertEqual(
            set(card), {"slug", "name", "logo", "cover", "clinics", "specialties", "services_count", "services"})
        for clinic in card["clinics"]:
            self.assertEqual(set(clinic), {"name", "address"})  # no phone, no map, no e-mail

    def test_no_login_is_needed(self):
        self.list_group()
        self.client.logout()
        self.assertEqual(self.client.get(reverse("api:directory")).status_code, 200)


class SearchTests(DirectoryBase):
    def test_a_word_matches_a_clinic_an_address_a_specialty_or_a_service(self):
        self.list_group()
        for word in ("clinic b", "nile", "dermato", "LASER", self.tenant.name.split()[0]):
            with self.subTest(word=word):
                self.assertEqual(self.slugs(q=word), [self.tenant.slug])
        self.assertEqual(self.slugs(q="cardiology"), [])

    def test_every_word_must_match(self):
        self.list_group()
        self.assertEqual(self.slugs(q="laser nile"), [self.tenant.slug])
        self.assertEqual(self.slugs(q="laser mars"), [])

    def test_an_empty_search_lists_everything(self):
        self.list_group()
        self.assertEqual(self.slugs(q="  "), [self.tenant.slug])


class GroupsStayApartTests(DirectoryBase):
    def test_each_card_holds_only_its_own_group(self):
        self.list_group()
        other = self.other_group(listed_in_directory=True)
        cache.clear()
        cards = {card["slug"]: card for card in self.directory()["results"]}
        self.assertEqual(set(cards), {self.tenant.slug, other.slug})
        mine, theirs = cards[self.tenant.slug], cards["other-group"]
        self.assertEqual([c["name"] for c in theirs["clinics"]], ["Other Clinic"])
        self.assertEqual(theirs["specialties"], [])  # no doctor works there, so nothing to offer
        self.assertNotIn("Other Clinic", str(mine))
        self.assertNotIn("Clinic A", str(theirs))
        self.assertNotIn("Dermatology", str(theirs))

    def test_a_group_that_is_not_listed_stays_out_while_another_is_in(self):
        self.list_group(listed=False)
        self.other_group(listed_in_directory=True)
        cache.clear()
        self.assertEqual(self.slugs(), ["other-group"])

    def test_a_search_finds_only_the_group_that_has_the_word(self):
        self.list_group()
        self.other_group(listed_in_directory=True)
        cache.clear()
        self.assertEqual(self.slugs(q="other clinic"), ["other-group"])
        self.assertEqual(self.slugs(q="1 nile"), [self.tenant.slug])


class TheOwnerChoosesTests(DirectoryBase):
    def settings_url(self):
        return reverse("api:clinic-settings")

    def test_the_owner_lists_and_unlists_the_group_and_it_shows_at_once(self):
        self.login("owner")
        self.assertFalse(self.client.get(self.settings_url()).json()["listed_in_directory"])
        self.assertEqual(self.slugs(), [])  # also warms the cache with an empty list
        self.login("owner")
        response = self.client.patch(self.settings_url(), {"listed_in_directory": True}, content_type="application/json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["listed_in_directory"])
        self.assertEqual(response.json()["directory_url"], "http://testserver/")
        self.assertEqual(self.slugs(), [self.tenant.slug])
        self.login("owner")
        self.client.patch(self.settings_url(), {"listed_in_directory": False}, content_type="application/json")
        self.assertEqual(self.slugs(), [])

    def test_only_a_real_boolean_is_accepted(self):
        self.login("owner")
        response = self.client.patch(self.settings_url(), {"listed_in_directory": "false"}, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Tenant.objects.get(pk=self.tenant.pk).listed_in_directory)

    def test_an_admin_or_reception_cannot_list_the_group(self):
        for who in ("admin-a", "rec"):
            self.login(who)
            response = self.client.patch(self.settings_url(), {"listed_in_directory": True}, content_type="application/json")
            self.assertEqual(response.status_code, 403, who)
        self.assertFalse(Tenant.objects.get(pk=self.tenant.pk).listed_in_directory)
