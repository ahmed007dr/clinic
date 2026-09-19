"""The public catalogue — service → clinics → doctors (docs/15, Phase 3).

    GET catalog/services/                                           what can be booked at all
    GET catalog/services/<service>/branches/                        the clinics that offer it — only those
    GET catalog/services/<service>/branches/<branch>/doctors/       who delivers it there, and at what price
    GET catalog/availability/days/?service&branch&doctor            the coming days that still have a time
    GET catalog/availability/?service&branch&doctor&date            the times offered on a day (Phase 4)

Public on purpose (a visitor browses before signing in), read-only, and every
list comes from `services.catalog.offerings` — the one rule for "bookable" — so
a clinic that does not offer a service never appears under it, and a doctor who
is not under contract for it, not shown publicly, or without a valid price never
appears under a clinic. Only what a clinic publishes anyway is returned: names,
prices, the public line a doctor approved; no internal id beyond the public
`uuid`, nothing about contracts, shares or patients.
"""

import uuid as uuid_module

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from branches.models import Branch
from services.catalog import offerings
from services.models import Service

from .views import PortalView

NOT_FOUND = {"detail": "غير موجود."}


def _money(value):
    return None if value is None else str(value)


def _quantity(service):
    """How a service is sold: by quantity or as one thing. When by quantity, every
    price the catalogue shows for it is the price of one unit."""
    return {
        "requires_quantity": service.requires_quantity,
        # The doctor fixes the real quantity in the room; a booking may go without one.
        "doctor_sets_quantity": service.requires_quantity and service.doctor_sets_quantity,
        "quantity_unit": service.quantity_unit,
        "min_quantity": str(service.min_quantity),
        "max_quantity": str(service.max_quantity) if service.max_quantity is not None else None,
    }


def _floor(prices):
    prices = [p for p in prices if p is not None]
    return min(prices) if prices else None


class _PublicCatalogView(PortalView):
    authentication_classes = []
    permission_classes = [AllowAny]


class CatalogServicesView(_PublicCatalogView):
    def get(self, request, slug):
        by_service = {}
        for offer in offerings():
            by_service.setdefault(offer.service, []).append(offer)
        rows = []
        for service, offers in by_service.items():
            rows.append({
                "uuid": str(service.uuid),
                "name": service.name,
                "description": service.description or "",
                "specialization": service.specialization.name if service.specialization_id else None,
                "duration_minutes": service.duration_minutes,
                "price_display": service.price_display,
                **_quantity(service),
                "from_price": _money(_floor(o.price for o in offers)),
                "branches_count": len({o.branch.pk for o in offers}),
            })
        return Response(sorted(rows, key=lambda row: row["name"]))


class CatalogBranchesView(_PublicCatalogView):
    def get(self, request, slug, service):
        found = Service.objects.filter(uuid=service, is_active=True).first()
        if found is None:
            return Response(NOT_FOUND, status=404)
        by_branch = {}
        for offer in offerings(service=found):
            by_branch.setdefault(offer.branch, []).append(offer)
        rows = [
            {
                "uuid": str(branch.uuid),
                "name": branch.name,
                "address": branch.address or "",
                "phone": branch.phone or "",
                "map_url": branch.map_url,
                "from_price": _money(_floor(o.price for o in offers)),
                "doctors_count": len({o.doctor.pk for o in offers}),
            }
            for branch, offers in by_branch.items()
        ]
        return Response({
            "service": {
                "uuid": str(found.uuid), "name": found.name,
                "duration_minutes": found.duration_minutes, "price_display": found.price_display,
                **_quantity(found),
            },
            "branches": sorted(rows, key=lambda row: row["name"]),
        })


class CatalogDoctorsView(_PublicCatalogView):
    def get(self, request, slug, service, branch):
        found = Service.objects.filter(uuid=service, is_active=True).first()
        clinic = Branch.objects.filter(uuid=branch, is_active=True, about_visible=True).first()
        if found is None or clinic is None:
            return Response(NOT_FOUND, status=404)
        rows = []
        for offer in offerings(service=found, branch=clinic):
            profile = offer.doctor.public_profile or {}
            rows.append({
                "uuid": str(offer.doctor.uuid),
                "name": offer.doctor.name,
                "specializations": sorted(s.name for s in offer.doctor.specializations.all()),
                "tagline": profile.get("tagline", ""),
                "price": _money(offer.price),
            })
        return Response({
            "service": {
                "uuid": str(found.uuid), "name": found.name,
                "duration_minutes": found.duration_minutes, "price_display": found.price_display,
                **_quantity(found),
            },
            "branch": {"uuid": str(clinic.uuid), "name": clinic.name},
            "doctors": sorted(rows, key=lambda row: row["name"]),
        })


# ------------------------------------------------------------- availability


class AvailabilityThrottle(AnonRateThrottle):
    scope = "portal_availability"


def _choice(request):
    """The (service, branch, doctor) named in the query, resolved to the
    server's own bookable offering — or None if it is not one. Never trusts that
    the client was shown this choice."""
    from employees.models import Employee
    from services.catalog import resolve_offering

    def uuid_of(name):
        try:
            return uuid_module.UUID(str(request.query_params.get(name) or ""))
        except ValueError:
            return None

    service, branch, doctor = uuid_of("service"), uuid_of("branch"), uuid_of("doctor")
    if not (service and branch and doctor):
        return None
    return resolve_offering(
        Branch.objects.filter(uuid=branch).first(),
        Employee.objects.filter(uuid=doctor).first(),
        Service.objects.filter(uuid=service).first(),
    )


class CatalogAvailabilityView(_PublicCatalogView):
    """`?service=&branch=&doctor=&date=YYYY-MM-DD` → the times offered that day."""

    throttle_classes = [AvailabilityThrottle]

    def get(self, request, slug):
        from appointments.availability import available_slots, parse_day

        offer = _choice(request)
        day = parse_day(request.query_params.get("date"))
        if offer is None:
            return Response(NOT_FOUND, status=404)
        if day is None:
            return Response({"date": ["تاريخ غير صالح."]}, status=400)
        return Response({
            "date": day.isoformat(),
            "duration_minutes": offer.service.duration_minutes,
            "slots": [slot.strftime("%H:%M") for slot in available_slots(offer, day)],
        })


class CatalogAvailableDaysView(_PublicCatalogView):
    """`?service=&branch=&doctor=[&from=YYYY-MM-DD]` → the coming days that still have a time."""

    throttle_classes = [AvailabilityThrottle]

    def get(self, request, slug):
        from appointments.availability import available_days, parse_day

        offer = _choice(request)
        if offer is None:
            return Response(NOT_FOUND, status=404)
        first = parse_day(request.query_params["from"]) if request.query_params.get("from") else None
        return Response({"days": [d.isoformat() for d in available_days(offer, first=first)]})
