"""Test helpers for working under row-level security.

Tests build fixtures the way no request ever does: they write rows for a
tenant while standing outside any request. Under the RLS policies added in
tenants.0005 the database rejects that, because the connection has not said
which tenant it is acting for. That rejection is the policy working, not a
bug to route around — so the helper here declares the tenant rather than
disabling the guard.

Deliberately *not* done here:

  * no BYPASSRLS role for the test database. Running the suite with the
    policies switched off would mean production code that forgets to declare
    its tenant passes every test and fails in production — which is exactly
    the bug this layer exists to catch.
  * no bypass flag in the policy itself. A policy with an "or if this GUC is
    set" clause is a backdoor; anything able to run set_config gets the whole
    database.
"""

from .context import bind_database_tenant, restore_database_tenant


def act_as_tenant(testcase, tenant):
    """Bind `tenant` at the database layer for the rest of the test method.

    Binds the *database* layer only, deliberately. The contextvar that drives
    the ORM's scoped manager stays unset, because outside a request it genuinely
    is unset — tests that assert `Model.objects` returns nothing outside a
    request, or that a reverse accessor is tenant-scoped, must keep observing
    that. What this restores is the ability of `all_objects` to reach the rows
    it names, which is what fixture setup and post-request assertions rely on.

    Without it, an assertion made after a test-client request reads on an
    unbound connection and sees nothing, so a negative assertion like
    `assertFalse(Visit.all_objects.filter(...).exists())` passes whether or not
    the row is there. Use it in setUp; the binding is undone on cleanup.
    """
    previous = bind_database_tenant(tenant)
    testcase.addCleanup(restore_database_tenant, previous)
    return tenant


def link_doctor(user, *patients):
    """Make `user` a doctor of record, and of `patients`.

    A doctor sees only their own patients (accounts.roles.scope_to_own_doctor):
    the login must be linked to a doctor record, and a patient is theirs once
    booked with them. Tests written before that rule used an unlinked Doctor
    account over a whole branch; this is the smallest fixture that gives such
    an account the same patients under the new rule. Returns the Employee.
    """
    from django.utils import timezone

    from appointments.models import Appointment
    from employees.models import Employee, EmployeeType

    from .context import tenant_context

    tenant = user.tenant
    with tenant_context(tenant):
        doctor_type, _ = EmployeeType.all_objects.get_or_create(tenant=tenant, name="Doctor")
        employee = Employee.all_objects.create(
            tenant=tenant, name=f"Dr {user.username}", branch=user.branch,
            employee_type=doctor_type, national_id=f"TEST-DR-{user.pk}", salary_value=0,
        )
        user.employee = employee
        user.save(update_fields=["employee"])
        for patient in patients:
            Appointment.all_objects.create(
                tenant=tenant, patient=patient, doctor=employee,
                branch=patient.branch or user.branch, scheduled_date=timezone.now(),
            )
    return employee
