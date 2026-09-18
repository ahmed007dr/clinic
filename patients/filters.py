"""Narrowing patients by what the search screen offers.

One place, so the list on screen and the PDF / Excel export of that list can
never disagree about who matches.
"""

from django.db.models import Q


def narrow_patients(queryset, params):
    """Gender, registration date range and clinic."""
    if params.get("gender") in ("male", "female"):
        queryset = queryset.filter(gender=params["gender"])
    if params.get("created_from"):
        queryset = queryset.filter(created_at__date__gte=params["created_from"])
    if params.get("created_to"):
        queryset = queryset.filter(created_at__date__lte=params["created_to"])
    if params.get("branch"):
        queryset = queryset.filter(branch__uuid=params["branch"])
    return queryset


def search_patients(queryset, term):
    """Every word must match somewhere: name, file number, either phone, national ID."""
    condition = Q()
    for word in (term or "").split():
        condition &= (
            Q(name__icontains=word)
            | Q(serial_number__icontains=word)
            | Q(phone1__icontains=word)
            | Q(phone2__icontains=word)
            | Q(national_id__icontains=word)
        )
    return queryset.filter(condition)
