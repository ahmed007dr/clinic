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
