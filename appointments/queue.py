"""Turn order in today's queue: who is ahead of whom, for which doctor.

One place, because the staff queue and the patient portal must give the same
answer — a receptionist saying "three ahead" while the patient's phone says
"two" is worse than no number at all.
"""

from django.utils import timezone

#: Still waiting to see the doctor — these are the ones a turn is counted over.
#: Someone already "entered" is with the doctor: shown separately, never as
#: "ahead" (the owner's decision, 2026-09-18).
WAITING_STATUSES = ("waiting", "called", "quick")


def ahead_counts(queryset):
    """`{appointment id: how many are ahead of it}`, per doctor, for today.

    Oldest first; a tie on the time falls to the booking's id, so the order
    never flips between two refreshes. A booking with no doctor has no queue to
    stand in and is left out. Pass a queryset already narrowed to what the
    caller may see — not one narrowed by a search box, or the numbers shrink
    with it.
    """
    rows = (
        queryset.filter(
            status__in=WAITING_STATUSES,
            doctor__isnull=False,
            scheduled_date__date=timezone.now().date(),
        )
        .order_by("scheduled_date", "id")
        .values_list("id", "branch_id", "doctor_id")
    )
    seen = {}
    ahead = {}
    for pk, branch_id, doctor_id in rows:
        key = (branch_id, doctor_id)
        ahead[pk] = seen.get(key, 0)
        seen[key] = ahead[pk] + 1
    return ahead


def doctors_with_patient_inside(queryset):
    """`{(branch id, doctor id)}` — whose doctor has someone in with them now."""
    return set(
        queryset.filter(
            status="entered",
            doctor__isnull=False,
            scheduled_date__date=timezone.now().date(),
        )
        .values_list("branch_id", "doctor_id")
        .distinct()
    )
