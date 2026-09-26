"""The public directory of clinic groups — the site's front door (docs/15, §10).

    GET /api/directory/            every group that chose to be listed, one card each
    GET /api/directory/?q=laser    …narrowed by a word: a group, a clinic, an address, a specialty or a service
    GET /api/directory/services/   every bookable service of every listed group — the store's front page (docs/16, R1);
                                   `?q=` narrows it by a word, `?governorate=` to services with a clinic there

Public and read-only. This is the one place the public API reads *across*
groups, so it is deliberately narrow:

* **Opt-in.** Only a group whose Owner switched on `Tenant.listed_in_directory`
  (and whose account is usable) appears. Nothing is listed by default.
* **One group at a time.** Each group is read inside its own tenant context —
  row-level security hides every other group's rows — never in one sweep.
* **Only what the group already publishes on its public page:** the approved
  logo and cover, the running clinics' names and addresses, the specialties
  its doctors offer (minus what management hid) and the services that can be
  booked online, with the lowest price. No phone, e-mail, doctor, patient or
  staff detail; a card links to the group's own public page for the rest.

The list is built once a minute and shared: a directory that costs a few
queries per group on every visit would be a way to load the server for free.
"""

from django.core.cache import cache
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from branches.about import specialties_by_branch, visible_specialties
from branches.media import url_of
from branches.models import Branch
from services.catalog import offerings
from services.nearby import normalize
from tenants.context import tenant_context
from tenants.models import Tenant

CACHE_KEY = "public-directory-v2"
CACHE_SECONDS = 60
#: A card names a few services; the count says how many there are.
SERVICES_PER_CARD = 8


class DirectoryThrottle(AnonRateThrottle):
    scope = "directory"


def forget_directory():
    """Called when a group's listing changes, so the switch shows at once."""
    cache.delete(CACHE_KEY)


def _card(tenant):
    """One group's card, or None when it has nothing public to show yet.
    Runs inside the group's tenant context."""
    branches = list(
        Branch.objects.filter(is_active=True, about_visible=True)
        .prefetch_related("about_hidden_specialties").order_by("name")
    )
    if not branches:
        return None
    found = specialties_by_branch()
    specialties = sorted({
        s["name"] for branch in branches for s in visible_specialties(branch, found.get(branch.pk, []))
    })
    prices = {}
    for offer in offerings():
        entry = prices.setdefault(offer.service.pk, {
            "service": offer.service, "name": offer.service.name, "from_price": None, "branches": {},
        })
        entry["branches"][offer.branch.pk] = offer.branch
        if offer.price is not None and (entry["from_price"] is None or offer.price < entry["from_price"]):
            entry["from_price"] = offer.price
    services = sorted(prices.values(), key=lambda row: row["name"])
    logo = url_of(tenant.public_logo)
    rows = []
    for row in services:
        service = row["service"]
        governorates = sorted({b.governorate.strip() for b in row["branches"].values() if b.governorate.strip()})
        rows.append({
            "group": tenant.slug, "group_name": tenant.name, "group_logo": logo,
            "uuid": str(service.uuid), "name": service.name, "description": service.description or "",
            "specialization": service.specialization.name if service.specialization_id else None,
            "duration_minutes": service.duration_minutes, "price_display": service.price_display,
            "requires_quantity": service.requires_quantity,
            "quantity_unit": service.quantity_unit if service.requires_quantity else "",
            "from_price": None if row["from_price"] is None else str(row["from_price"]),
            "branches_count": len(row["branches"]), "governorates": governorates,
            # What a search matches against; never sent to the browser.
            "_search": " ".join([
                service.name, service.description or "", tenant.name,
                service.specialization.name if service.specialization_id else "", *governorates,
            ]).casefold(),
            "_governorates": {normalize(g) for g in governorates},
        })
    return {
        "_service_rows": rows,
        "slug": tenant.slug,
        "name": tenant.name,
        "logo": logo,
        "cover": url_of(tenant.public_cover),
        "clinics": [{"name": b.name, "address": b.address or ""} for b in branches],
        "specialties": specialties,
        "services_count": len(services),
        "services": [
            {"name": row["name"], "from_price": None if row["from_price"] is None else str(row["from_price"])}
            for row in services[:SERVICES_PER_CARD]
        ],
        # What a search matches against; never sent to the browser.
        "_search": " ".join([
            tenant.name, *(b.name for b in branches), *(b.address or "" for b in branches),
            *specialties, *(row["name"] for row in services),
        ]).casefold(),
    }


def directory_cards():
    cards = cache.get(CACHE_KEY)
    if cards is None:
        cards = []
        for tenant in Tenant.objects.filter(listed_in_directory=True).order_by("name"):
            if not tenant.is_usable:
                continue
            with tenant_context(tenant):
                card = _card(tenant)
            if card is not None:
                cards.append(card)
        cache.set(CACHE_KEY, cards, CACHE_SECONDS)
    return cards


class DirectoryServicesView(APIView):
    """The store's front page: what can be bought, across every listed group."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [DirectoryThrottle]

    def get(self, request):
        rows = [row for card in directory_cards() for row in card["_service_rows"]]
        words = request.query_params.get("q", "")[:100].casefold().split()
        if words:
            rows = [row for row in rows if all(word in row["_search"] for word in words)]
        wanted = normalize(request.query_params.get("governorate"))
        if wanted:
            rows = [row for row in rows if wanted in row["_governorates"]]
        rows = sorted(rows, key=lambda row: (row["name"], row["group_name"]))[:300]
        return Response({
            "count": len(rows),
            "results": [{k: v for k, v in row.items() if not k.startswith("_")} for row in rows],
        })


class DirectoryView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [DirectoryThrottle]

    def get(self, request):
        cards = directory_cards()
        # Every word must appear somewhere on the card: "laser cairo" narrows twice.
        words = request.query_params.get("q", "")[:100].casefold().split()
        if words:
            cards = [card for card in cards if all(word in card["_search"] for word in words)]
        return Response({
            "count": len(cards),
            "results": [{k: v for k, v in card.items() if not k.startswith("_")} for card in cards],
        })
