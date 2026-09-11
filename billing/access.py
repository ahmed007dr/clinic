"""Who may see which money — decided in one place.

The clinic's books belong to its management. Before this module, every member
of a branch could list its payments and expenses for any date range and open
the financial report, so a receptionist could read the clinic's takings for the
whole year and a doctor every colleague's patients' payments.

* **Owner / Admin** — the books: every payment and expense in their scope, any
  period, and the reports built on them.
* **Reception** — only the money in their own *open* cash shift
  (billing.shifts). Once the shift is closed it is management's to review;
  nothing in it, and nothing from any other shift or date, stays visible.
* **Doctor** — no clinic money at all; only their own share, once doctor
  commissions exist.

Every list, aggregate and report goes through these functions. Branch scoping
(`scope_queryset_to_user`) still applies on top — this narrows *within* what
the branch rule already allows.
"""

from accounts.roles import RECEPTION, is_clinic_admin, role_name, scope_queryset_to_user


def can_view_finance(user):
    """The financial report, month and period totals, the revenue chart."""
    return is_clinic_admin(user)


def restrict_payments(queryset, user):
    """Narrow a payment queryset to what the user's role may read. Branch
    scoping is the caller's (a ClinicViewSet applies it itself)."""
    if is_clinic_admin(user):
        return queryset
    if role_name(user) == RECEPTION:
        return queryset.filter(shift__user=user, shift__status="open")
    return queryset.none()


def restrict_expenses(queryset, user):
    if is_clinic_admin(user):
        return queryset
    if role_name(user) == RECEPTION:
        return queryset.filter(shift__user=user, shift__status="open")
    return queryset.none()


def visible_payments(user, queryset):
    """Branch scope and role together — for aggregates built outside a viewset."""
    return restrict_payments(scope_queryset_to_user(queryset, user), user)


def visible_expenses(user, queryset):
    return restrict_expenses(scope_queryset_to_user(queryset, user), user)
