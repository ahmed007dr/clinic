"""TENANT-007 — the database refuses cross-tenant rows.

Layers 2–4 (scoped manager, request contextvar, isolation tests) all live in
application code, so they all share one failure mode: code that forgets to ask.
This layer does not depend on the application asking. If a view, a report, a
management command or a future API endpoint queries a tenant table without
scoping it, PostgreSQL returns nothing rather than everything.

FORCE is what makes it real: without it, policies are skipped for the table
owner, which is exactly the role the application connects as.

Excluded on purpose — all three have a nullable tenant and would break under a
blanket policy:
  accounts_user     authentication has to find the user *before* any tenant is
                    known, so an RLS policy here would make login impossible
  audit_auditlog    platform-level events legitimately belong to no tenant
  tenants_serialcounter  internal sequence bookkeeping

Requires the application role to be neither SUPERUSER nor BYPASSRLS. Migrations
should run as a separate role that does have BYPASSRLS, or data migrations that
touch tenant tables will silently see nothing.
"""

from django.db import migrations

TENANT_TABLES = [
    "accounts_clinicrole",
    "appointments_appointment",
    "billing_expense",
    "billing_expensecategory",
    "billing_payment",
    "billing_paymentmethod",
    "branches_branch",
    "employees_employee",
    "employees_employeetype",
    "employees_salarytype",
    "employees_specialization",
    "medical_allergy",
    "medical_prescription",
    "medical_prescriptionitem",
    "medical_visit",
    "notifications_notification",
    "patients_patient",
    "reports_reportrecipient",
    "services_service",
]

# current_setting(..., true) yields NULL when unset; NULLIF turns the empty
# string into NULL too. tenant_id = NULL matches nothing, so an unset tenant
# sees no rows — the same fail-closed behaviour as the ORM manager.
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


def apply_policies(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return  # SQLite has no equivalent; the application layers still apply
    with schema_editor.connection.cursor() as cursor:
        for table in TENANT_TABLES:
            cursor.execute(POLICY.format(table=table))


def drop_policies(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in TENANT_TABLES:
            cursor.execute(REVERSE.format(table=table))


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0004_seed_serial_counters"),
        ("medical", "0002_prescription_prescriptionitem_and_more"),
        ("billing", "0005_add_uuid"),
        ("employees", "0005_add_uuid"),
        ("accounts", "0006_add_uuid"),
        ("notifications", "0005_add_uuid"),
        ("reports", "0005_add_uuid"),
        ("services", "0005_add_uuid"),
        ("branches", "0005_add_uuid"),
        ("patients", "0005_add_uuid"),
        ("appointments", "0005_add_uuid"),
    ]

    operations = [
        migrations.RunPython(apply_policies, drop_policies),
    ]
