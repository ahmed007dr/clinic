"""What a branch offers, worked out from who works there.

The specialties a branch shows in "About" are not typed in by anyone: they are
the specialties of its doctors — those based there and those the Owner linked
to it — whose logins management has not stopped. So the list is right the day a
doctor is added or moved, and never needs a second place to keep in step.
"""

from employees.models import Employee


def specialties_by_branch():
    """`{branch id: [{"name", "description"}]}`, each list sorted by name."""
    doctors = (
        Employee.objects.filter(employee_type__name="Doctor")
        .exclude(user_account__is_active=False)
        .prefetch_related("specializations", "extra_branches")
    )
    found = {}
    for doctor in doctors:
        branch_ids = {doctor.branch_id, *(b.pk for b in doctor.extra_branches.all())}
        for specialty in doctor.specializations.all():
            for branch_id in branch_ids:
                found.setdefault(branch_id, {})[specialty.pk] = specialty
    return {
        branch_id: sorted(
            ({"name": s.name, "description": s.description or ""} for s in by_pk.values()),
            key=lambda item: item["name"],
        )
        for branch_id, by_pk in found.items()
    }
