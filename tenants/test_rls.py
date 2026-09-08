"""TENANT-007 — the database itself refuses cross-tenant rows.

The rest of the suite proves the *application* scopes its queries. These tests
prove the layer underneath, which holds even when the application forgets:
PostgreSQL row-level security, installed by tenants.0005.

Why that layer is worth having, given the ORM manager already scopes reads:
the manager, the contextvar and the isolation tests share one failure mode —
code that forgets to ask. A new report, a management command, a raw SQL query,
a future API endpoint. RLS does not depend on anyone asking.

These tests speak SQL directly rather than going through the ORM. Going
through the ORM would prove the ORM works, which is what the other modules are
for; the claim here is about the database, so it has to be made to the
database. They skip on SQLite, which has no equivalent — a fact worth keeping
visible, because it means a green SQLite run says nothing about this layer.
"""

from django.apps import apps as django_apps
from django.db import ProgrammingError, connection, transaction
from django.test import TestCase

from patients.models import Patient

from .context import tenant_context
from .models import Tenant
from .rls import tenant_tables

# Derived from the live model registry, not written out. A literal list would
# guard against a policy being deleted but not against the realistic decay
# mode: a tenant-owned model added later while the list stays as it was. Asking
# the models means a new model arrives already expected, and ships unprotected
# only over a failing test.
EXPECTED_PROTECTED_TABLES = set(tenant_tables(django_apps))


class RowLevelSecurityTests(TestCase):
    """Bypassed entirely on SQLite — see the module docstring."""

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("row-level security is PostgreSQL-only")
        self.a = Tenant.objects.first()
        self.b = Tenant.objects.create(
            name="Rival Clinic", slug="rival-clinic", status=Tenant.Status.ACTIVE
        )
        with tenant_context(self.a):
            self.patient_a = Patient.all_objects.create(tenant=self.a, name="A Patient")
        with tenant_context(self.b):
            self.patient_b = Patient.all_objects.create(tenant=self.b, name="B Patient")

    def sql(self, query, params=None):
        """For statements that return rows."""
        with connection.cursor() as cursor:
            cursor.execute(query, params or [])
            return cursor.fetchall()

    def execute(self, query, params=None):
        """For statements that do not — an UPDATE blocked by a policy affects
        no rows rather than raising, so the row count is the interesting part.
        """
        with connection.cursor() as cursor:
            cursor.execute(query, params or [])
            return cursor.rowcount

    def bind(self, value):
        """Set the GUC directly, bypassing the helpers, so these tests fail if
        the policy stops working rather than if the helper does."""
        self.execute("SELECT set_config('app.current_tenant_id', %s, false)", [str(value)])

    # ---- the policies exist and are forced ----------------------------------

    def test_the_expected_set_is_not_empty(self):
        """The derivation feeds the check below, so an empty or broken result
        would turn that check into a no-op that passes."""
        self.assertGreaterEqual(len(EXPECTED_PROTECTED_TABLES), 19)
        self.assertIn("patients_patient", EXPECTED_PROTECTED_TABLES)
        # Excluded on purpose — see tenants/rls.py for why each one is.
        self.assertNotIn("accounts_user", EXPECTED_PROTECTED_TABLES)
        self.assertNotIn("audit_auditlog", EXPECTED_PROTECTED_TABLES)

    def test_every_tenant_table_has_the_policy_enabled_and_forced(self):
        """FORCE is the load-bearing half: without it PostgreSQL skips policies
        for the table owner, which is the role the application connects as, so
        the protection would be silently absent in exactly the case it matters.

        The expected set comes from the models, so a tenant-owned model added
        without a policy fails here rather than shipping unprotected.
        """
        rows = self.sql(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = current_schema() AND c.relname = ANY(%s)
            """,
            [sorted(EXPECTED_PROTECTED_TABLES)],
        )
        found = {name: (enabled, forced) for name, enabled, forced in rows}
        self.assertEqual(set(found), EXPECTED_PROTECTED_TABLES, "a protected table is missing")
        for table, (enabled, forced) in sorted(found.items()):
            with self.subTest(table=table):
                self.assertTrue(enabled, f"{table} does not have RLS enabled")
                self.assertTrue(forced, f"{table} does not FORCE RLS — the owner would bypass it")

    def test_the_application_role_cannot_bypass_policies(self):
        """A SUPERUSER or BYPASSRLS role ignores every policy above. If the
        application connects as one, this whole layer is decorative."""
        (superuser, bypass), = self.sql(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
        )
        self.assertFalse(superuser, "the application role is SUPERUSER — RLS does not apply to it")
        self.assertFalse(bypass, "the application role has BYPASSRLS — RLS does not apply to it")

    # ---- reads --------------------------------------------------------------

    def test_an_unbound_connection_sees_no_rows(self):
        """Fails closed. Returning everything when nobody said which tenant is
        the dangerous default this exists to rule out."""
        self.bind("")
        self.assertEqual(self.sql("SELECT count(*) FROM patients_patient")[0][0], 0)

    def test_each_tenant_sees_only_its_own_rows(self):
        for tenant, expected in ((self.a, "A Patient"), (self.b, "B Patient")):
            with self.subTest(tenant=tenant.slug):
                self.bind(tenant.id)
                names = [n for (n,) in self.sql("SELECT name FROM patients_patient")]
                self.assertEqual(names, [expected])

    def test_knowing_another_tenants_primary_key_does_not_help(self):
        """The point of the layer. Tenant scoping in the ORM can be forgotten by
        a single query; this cannot be, so a leaked or guessed id is inert."""
        self.bind(self.a.id)
        rows = self.sql(
            "SELECT count(*) FROM patients_patient WHERE id = %s", [self.patient_b.pk]
        )
        self.assertEqual(rows[0][0], 0)

    def test_a_raw_unscoped_query_still_cannot_span_tenants(self):
        """Written the way a forgotten filter in a report would be."""
        self.bind(self.a.id)
        self.assertEqual(self.sql("SELECT count(*) FROM patients_patient")[0][0], 1)

    # ---- writes -------------------------------------------------------------

    def _insert_patient_for(self, tenant_id, name):
        """Every NOT NULL column is supplied, so a failure here can only be the
        policy. Asserting on a bare Exception would pass just as happily on a
        missing-column error, which would prove nothing.

        The savepoint matters: a rejected statement aborts the transaction, and
        without one the assertion that follows cannot query.
        """
        with transaction.atomic():
            self.execute(
                "INSERT INTO patients_patient"
                " (tenant_id, uuid, name, gender, marital_status, serial_number,"
                "  created_at, updated_at)"
                " VALUES (%s, gen_random_uuid(), %s, 'male', 'single', 'X', now(), now())",
                [tenant_id, name],
            )

    def test_a_tenant_can_insert_its_own_row(self):
        """The counterpart to the next test: it shows the INSERT above is
        well-formed, so the rejection there is the policy and nothing else."""
        self.bind(self.a.id)
        self._insert_patient_for(self.a.id, "legitimate")
        self.assertEqual(self.sql("SELECT count(*) FROM patients_patient")[0][0], 2)

    def test_a_tenant_cannot_insert_a_row_owned_by_another(self):
        """WITH CHECK, not just USING. Without it a tenant could write rows into
        another tenant's data even while unable to read them back."""
        self.bind(self.a.id)
        # Django wraps the psycopg2 error, so the message is what identifies
        # the cause — the type alone would also match a plain syntax error.
        with self.assertRaises(ProgrammingError) as caught:
            self._insert_patient_for(self.b.id, "smuggled")
        self.assertIn("row-level security", str(caught.exception))

    def test_a_tenant_cannot_update_another_tenants_row(self):
        """An UPDATE the policy hides is not an error — the row is simply not
        visible to match, so it silently affects nothing. Checking the row
        count is what distinguishes that from a write that took effect."""
        self.bind(self.a.id)
        affected = self.execute(
            "UPDATE patients_patient SET name = 'stolen' WHERE id = %s", [self.patient_b.pk]
        )
        self.assertEqual(affected, 0)
        self.bind(self.b.id)
        names = [n for (n,) in self.sql("SELECT name FROM patients_patient")]
        self.assertEqual(names, ["B Patient"])

    def test_a_tenant_cannot_delete_another_tenants_row(self):
        self.bind(self.a.id)
        affected = self.execute(
            "DELETE FROM patients_patient WHERE id = %s", [self.patient_b.pk]
        )
        self.assertEqual(affected, 0)
        self.bind(self.b.id)
        self.assertEqual(self.sql("SELECT count(*) FROM patients_patient")[0][0], 1)


class DatabaseBindingTests(TestCase):
    """The helpers in tenants.context are what put the tenant on the
    connection, so the guarantee above is only as good as they are."""

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("row-level security is PostgreSQL-only")
        self.a = Tenant.objects.first()
        self.b = Tenant.objects.create(
            name="Rival Clinic", slug="rival-clinic", status=Tenant.Status.ACTIVE
        )

    def current(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('app.current_tenant_id', true)")
            return cursor.fetchone()[0] or ""

    def test_tenant_context_binds_and_unbinds_the_connection(self):
        self.assertEqual(self.current(), "")
        with tenant_context(self.a):
            self.assertEqual(self.current(), str(self.a.id))
        self.assertEqual(self.current(), "")

    def test_nested_contexts_restore_the_outer_binding(self):
        """Restoring rather than blanking is what lets a request run inside an
        outer binding without stranding the work that follows it unbound."""
        with tenant_context(self.a):
            with tenant_context(self.b):
                self.assertEqual(self.current(), str(self.b.id))
            self.assertEqual(self.current(), str(self.a.id))

    def test_the_binding_is_cleared_when_the_block_raises(self):
        with self.assertRaises(ValueError):
            with tenant_context(self.a):
                raise ValueError("boom")
        self.assertEqual(self.current(), "")
