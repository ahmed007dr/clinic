"""Who a clinic user is — decided in one place.

A medical group is a **Tenant**; each of its clinics is a **Branch**
(tenants/models.py). Row-level security already keeps one group's data away
from every other group, so the roles below only ever decide what happens
*inside* one group:

* **Owner** — owns the group. Sees every clinic and every figure, and has the
  group dashboard. The only role that can add clinics, see the subscription or
  the audit trail, change group-wide settings, or make someone an Owner.
* **Admin** — runs one clinic (their branch): its staff, its books, its
  reports. Sees that clinic only.
* **Doctor** — clinical work, for their own patients only (see
  `scope_to_own_doctor`). No clinic money; only their own share.
* **Reception** — the front desk, in their clinic.

Before the Owner role existed, "Admin" meant "sees every branch". Every Admin
at that moment was promoted to Owner (accounts.0007), so nobody's access
changed; from then on Admin means one clinic.

Every role check in the application goes through these functions. A role name
compared inline somewhere else is a check that will drift — which is exactly
how the old code ended up with forty-four slightly different ones.
"""

OWNER = "Owner"
ADMIN = "Admin"
DOCTOR = "Doctor"
RECEPTION = "Reception"

from django.db.models import Q

ALL_ROLES = (OWNER, ADMIN, DOCTOR, RECEPTION)

#: Who may read clinical records. Reception never does (§14).
CLINICAL_ROLES = {OWNER, ADMIN, DOCTOR}


def role_name(user):
    role = getattr(user, "role", None)
    return getattr(role, "name", None)


def display_name(user):
    """A person's name for print (the queue ticket's "reception name", a
    receipt's "recorded by") — their full name, or their username when that
    is blank, which is the common case: staff accounts are rarely given one."""
    full = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
    return full or getattr(user, "username", "")


def is_owner(user):
    """Fails closed: a user with no role is nobody."""
    return role_name(user) == OWNER


def is_clinic_admin(user):
    """Administrative capability. An Owner is also an admin of every clinic."""
    return role_name(user) in {OWNER, ADMIN}


def sees_all_branches(user):
    """Only the Owner is group-wide. Everyone else, Admin included, sees their
    own clinic."""
    return is_owner(user)


def is_front_desk(user):
    """Registration, booking and payments."""
    return role_name(user) in {OWNER, ADMIN, RECEPTION}


def can_view_patients(user):
    return role_name(user) in {OWNER, ADMIN, RECEPTION, DOCTOR}


def can_view_clinical(user):
    return role_name(user) in CLINICAL_ROLES


def is_doctor(user):
    return role_name(user) == DOCTOR


def account_is_usable(user):
    """False for someone whose clinic the Owner has stopped. The Owner spans
    every clinic, and a user with no clinic (platform staff) is judged
    elsewhere, so only a branch that exists and is inactive shuts the door."""
    if is_owner(user):
        return True
    branch = getattr(user, "branch", None) if getattr(user, "branch_id", None) else None
    return branch is None or branch.is_active


#: A booking in one of these does not make its patient "visiting" at a clinic:
#: a request nobody has confirmed, or one that did not happen.
NOT_A_VISIT = ("requested", "cancelled", "no_show")


def visiting_patient_ids(branch_id):
    """Patients of *another* clinic who have a confirmed booking at this one
    (docs/15, D10). A subquery of patient ids; nothing else about them."""
    from appointments.models import Appointment

    return (
        Appointment.all_objects.filter(branch_id=branch_id)
        .exclude(status__in=NOT_A_VISIT)
        .values("patient_id")
    )


def _patient_lookup(model, branch_field):
    """How to name a row's patient, when `branch_field` is the patient's own
    clinic — the only place a visiting patient may be admitted."""
    if branch_field == "patient__branch":
        return "patient_id"
    if branch_field == "branch" and model._meta.label_lower == "patients.patient":
        return "pk"
    return None


def recorded_at_my_clinic(queryset, user, branch_field="branch"):
    """Only rows recorded at the user's own clinic; the Owner sees all. Unlike
    `scope_queryset_to_user` it adds no doctor narrowing — for a patient's
    combined timeline, which must never carry another clinic's records."""
    if sees_all_branches(user):
        return queryset
    branch_id = current_branch_id(user)
    if not branch_id:
        return queryset.none()
    return queryset.filter(**{f"{branch_field}_id": branch_id})


def is_visiting_patient(patient, user):
    """True when `user` reaches this patient only through a booking at their
    clinic, not because it is the patient's own clinic."""
    return not sees_all_branches(user) and patient.branch_id != current_branch_id(user)


def scope_queryset_to_user(queryset, user, branch_field="branch", visiting=False):
    """The Owner sees every clinic; everyone else is held to their own; a
    doctor, within it, to their own patients.

    A user with no branch and no Owner role gets nothing rather than
    everything — the direction a mistake falls matters more than whether one
    happens. `branch_field` is a lookup path, because not every record has a
    branch of its own (a prescription belongs to its visit's clinic).

    `visiting=True` — opted into by the few screens that need it — also admits
    a patient of another clinic who has a confirmed booking here (docs/15, D10),
    and only for the two ways of asking "is this patient mine": the patient
    record itself and things hung off the patient's clinic. Everything with a
    clinic of its own (bookings, visits, payments, results) stays exactly as it
    was, which is what keeps the other clinic's history out of sight.
    """
    if sees_all_branches(user):
        return queryset
    branch_id = current_branch_id(user)
    if not branch_id:
        return queryset.none()
    condition = Q(**{f"{branch_field}_id": branch_id})
    lookup = _patient_lookup(queryset.model, branch_field) if visiting else None
    if lookup:
        condition |= Q(**{f"{lookup}__in": visiting_patient_ids(branch_id)})
    queryset = queryset.filter(condition)
    if is_doctor(user):
        queryset = scope_to_own_doctor(queryset, user)
    return queryset


def doctor_branch_ids(user):
    """Every clinic a doctor works in: their home branch, plus any the Owner
    has added (Employee.extra_branches). Empty for anyone who is not a
    linked doctor. Cached on the user object for the request."""
    cached = getattr(user, "_doctor_branch_ids", None)
    if cached is not None:
        return cached
    ids = set()
    if is_doctor(user):
        if getattr(user, "branch_id", None):
            ids.add(user.branch_id)
        employee_id = getattr(user, "employee_id", None)
        if employee_id:
            from employees.models import Employee

            ids.update(
                Employee.extra_branches.through.objects.filter(
                    employee_id=employee_id, branch__is_active=True
                ).values_list("branch_id", flat=True)
            )
    user._doctor_branch_ids = ids
    return ids


def current_branch_id(user):
    """The clinic this request is about.

    Everyone below the Owner works in one clinic, their `branch` — except a
    doctor the Owner has linked to several, who switches between them from
    their profile (`/api/auth/branch/`, stored in the session and put on the
    user by accounts.middleware). The choice is re-checked here on every
    request, so a branch the Owner has since removed stops working at once.
    """
    chosen = getattr(user, "active_branch_id", None)
    if chosen and is_doctor(user) and chosen in doctor_branch_ids(user):
        return chosen
    return getattr(user, "branch_id", None)


def scope_to_own_doctor(queryset, user):
    """A doctor sees their own work and their own patients — nobody else's.

    Decided by the owner of the group (2026-09-11): doctors are contracted
    individually, and one doctor reading a colleague's patients, visits or
    earnings is not part of that contract. Cover for an absent colleague goes
    through an Admin reassigning the booking, not through open access.

    Applied here, inside the one scoping function every list, detail view,
    relation field, dashboard and server-rendered screen already calls, so
    there is no door left that still shows the whole branch:

    * a record with a `doctor` (bookings, visits, prescriptions, procedures,
      plans, sessions) — only where that doctor is them;
    * a patient — only one they have seen, are booked with, or are treating;
    * a record hung off a patient (allergies, lab results, attachments) — only
      for those patients;
    * anything else (branches, services, the doctors list) — unchanged.

    A doctor's login not yet linked to its doctor record sees none of it.
    """
    employee_id = getattr(user, "employee_id", None)
    model = queryset.model
    fields = {field.name for field in model._meta.get_fields()}
    if model._meta.label_lower == "patients.patient":
        lookup = "pk"
    elif "doctor" in fields:
        return queryset.filter(doctor_id=employee_id) if employee_id else queryset.none()
    elif "patient" in fields:
        lookup = "patient_id"
    else:
        return queryset
    if not employee_id:
        return queryset.none()
    return queryset.filter(own_patients_q(employee_id, lookup))


def own_patients_q(employee_id, lookup="pk"):
    """Patients a doctor is connected to: booked with, seen by, or under a
    treatment plan of. `lookup` is the path to the patient's id on the model
    being filtered."""
    from appointments.models import Appointment
    from django.db.models import Q
    from medical.models import TreatmentPlan, Visit

    q = Q()
    for model in (Appointment, Visit, TreatmentPlan):
        # all_objects: the doctor already pins the tenant, and the default
        # manager would return nothing outside a request's tenant context.
        ids = model.all_objects.filter(doctor_id=employee_id).values("patient_id")
        q |= Q(**{f"{lookup}__in": ids})
    return q


def can_manage_account(actor, target):
    """Who may edit, stop or restart whose account (2026-09-11).

    * The Owner: anyone in the group but themselves.
    * A clinic Admin: the employees and doctors of their own clinic — never
      another Admin, never an Owner.
    * Nobody stops their own account: a group left with no one able to sign
      in to restart it has no way back.
    """
    if actor.pk == target.pk:
        return False
    if is_owner(actor):
        return True
    if not is_clinic_admin(actor):
        return False
    return role_name(target) in {DOCTOR, RECEPTION, None} and target.branch_id == actor.branch_id


def assignable_role_names(user):
    """Roles this user may give to someone else.

    A clinic Admin staffs their clinic but can never create an Owner: that
    would be a clinic admin promoting themselves, or a friend, to see every
    clinic's books.
    """
    if is_owner(user):
        return {OWNER, ADMIN, DOCTOR, RECEPTION}
    if is_clinic_admin(user):
        return {ADMIN, DOCTOR, RECEPTION}
    return set()
