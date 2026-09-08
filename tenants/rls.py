"""Row-level security policies, derived from the models rather than listed.

tenants.0005 introduced the policies against a hand-written list of 19 tables.
A list is the wrong shape for this: the realistic way this protection decays is
not someone deleting a policy, it is someone adding a tenant-owned model and
nobody noticing the list did not grow. The table would then have no policy, and
nothing would say so.

So membership is a property of the model. A table needs the policy when it has
a non-nullable `tenant` foreign key — which is exactly what TenantOwnedModel
gives every one of its subclasses. New clinical and SaaS models therefore
inherit the requirement by existing, and `tenants/test_rls.py` derives its
expectations the same way, so a model added without a policy fails the suite.

Three tables are excluded deliberately:

  accounts_user          authentication has to find the user *before* any
                         tenant is known; a policy here makes login impossible
  audit_auditlog         platform-level events legitimately belong to no tenant
  tenants_serialcounter  sequence bookkeeping read while issuing a serial,
                         including from contexts that have no tenant bound

The first two have a nullable `tenant` and would be skipped anyway; they are
named here so the reason is recorded rather than inferred. SerialCounter is the
one genuine exception — its `tenant` is NOT NULL, so it has to be excluded by
name. Revisiting it means auditing every caller of `next_serial` first.
"""

from django.core.exceptions import FieldDoesNotExist

EXCLUDED_TABLES = {
    "accounts_user",
    "audit_auditlog",
    "tenants_serialcounter",
}

# current_setting(..., true) yields NULL when unset; NULLIF turns the empty
# string into NULL too. `tenant_id = NULL` matches nothing, so an unset tenant
# sees no rows — the same fail-closed behaviour as the ORM manager.
#
# FORCE is the load-bearing half: without it PostgreSQL skips policies for the
# table owner, which is the role the application connects as, so the protection
# would be silently absent in exactly the case it exists for.
POLICY = """
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON {table};
CREATE POLICY tenant_isolation ON {table}
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::bigint)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::bigint);
"""

REVERSE = """
DROP POLICY IF EXISTS tenant_isolation ON {table};
ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
"""


def _owns_a_tenant(model):
    try:
        field = model._meta.get_field("tenant")
    except FieldDoesNotExist:
        return False
    # A nullable tenant means rows can legitimately belong to none, so a
    # blanket policy would hide them from everyone.
    return field.is_relation and not field.null


def tenant_tables(apps):
    """Every table that must carry the isolation policy, in a stable order.

    Takes the app registry as an argument so a migration can pass its own
    historical registry and get the answer for that point in history, while
    tests pass the live one.
    """
    tables = set()
    for model in apps.get_models():
        meta = model._meta
        if meta.proxy or not meta.managed:
            continue
        if meta.db_table in EXCLUDED_TABLES:
            continue
        if _owns_a_tenant(model):
            tables.add(meta.db_table)
    return sorted(tables)


def apply_tenant_policies(apps, schema_editor):
    """Idempotent — the policy is dropped and recreated, so re-running is safe
    and a migration can reapply it after a model changes."""
    if schema_editor.connection.vendor != "postgresql":
        return  # SQLite has no equivalent; the application layers still apply
    with schema_editor.connection.cursor() as cursor:
        for table in tenant_tables(apps):
            cursor.execute(POLICY.format(table=table))


def drop_tenant_policies(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in tenant_tables(apps):
            cursor.execute(REVERSE.format(table=table))
