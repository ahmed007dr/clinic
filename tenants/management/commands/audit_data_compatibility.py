"""Find data that SQLite accepts and PostgreSQL will not.

Strictly read-only. It reports; it never truncates, repairs or deletes. That is
deliberate: the fixes are judgement calls about real patient records, and a
command that silently "cleaned" them would destroy the evidence needed to make
those calls.

Why this is needed at all: SQLite is permissive in ways PostgreSQL is not, and
every one of those differences is a migration that fails halfway, or worse,
succeeds while dropping something.

  * VARCHAR(n) is advisory in SQLite and enforced in PostgreSQL. This has
    already bitten once — `fake.phone_number()` produced 22 characters for a
    `varchar(20)` column, which passed locally and raised DataError on
    PostgreSQL.
  * Foreign keys are not enforced in SQLite unless `PRAGMA foreign_keys=ON` is
    set per connection, which Django does — but rows written by anything else
    (a manual sqlite3 session, an old import script, a restored backup) can
    leave dangling references that PostgreSQL will refuse.
  * Dates and UUIDs are stored as text in SQLite, so malformed values survive
    until a real `date`/`uuid` column rejects them.
  * Django-level validators (MinValueValidator on money) are not database
    constraints, so negative amounts can already be present.

Checks are generated from the model registry rather than a hand-written list,
so a model added later is audited without anyone remembering to add it — the
same reasoning as tenants/rls.py.

    python manage.py audit_data_compatibility
    python manage.py audit_data_compatibility --database default --strict
    python manage.py audit_data_compatibility --samples 10
"""

import uuid as uuid_module
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.apps import apps
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand
from django.core.validators import validate_email
from django.db import connections, models

# Only these are worth reporting per row; the rest are summarised.
SAMPLE_DEFAULT = 5


class Finding:
    def __init__(self, severity, category, table, column, count, detail="", samples=None):
        self.severity = severity  # "BLOCKER" or "WARNING"
        self.category = category
        self.table = table
        self.column = column
        self.count = count
        self.detail = detail
        self.samples = samples or []


class Command(BaseCommand):
    help = "Report data that would fail a SQLite -> PostgreSQL migration. Read-only."

    def add_arguments(self, parser):
        parser.add_argument("--database", default="default", help="Database alias to audit.")
        parser.add_argument(
            "--samples", type=int, default=SAMPLE_DEFAULT,
            help="Offending primary keys to list per finding.",
        )
        parser.add_argument(
            "--strict", action="store_true",
            help="Exit 1 if any blocker is found (for CI).",
        )

    # ------------------------------------------------------------------ helpers

    def q(self, name):
        return self.connection.ops.quote_name(name)

    def fetch(self, sql, params=None):
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params or [])
            return cursor.fetchall()

    def scalar(self, sql, params=None):
        rows = self.fetch(sql, params)
        return rows[0][0] if rows else 0

    def table_exists(self, table):
        return table in self.existing_tables

    def concrete_fields(self, model):
        return [
            f for f in model._meta.local_fields
            if f.concrete and not isinstance(f, models.ManyToManyField)
        ]

    # --------------------------------------------------------------------- main

    def handle(self, *args, **options):
        alias = options["database"]
        self.connection = connections[alias]
        self.samples = max(0, options["samples"])
        self.findings = []

        with self.connection.cursor() as cursor:
            self.existing_tables = set(
                self.connection.introspection.table_names(cursor)
            )

        self.stdout.write("")
        self.stdout.write(f"  Auditing database alias '{alias}' ({self.connection.vendor})")
        self.stdout.write(f"  {len(self.existing_tables)} tables present")

        if self.connection.vendor == "postgresql":
            self.warn_about_rls()

        audited = self.collect_models()
        self.stdout.write(f"  {len(audited)} models audited")
        self.stdout.write("")

        for model in audited:
            self.check_max_length(model)
            self.check_not_null(model)
            self.check_uniqueness(model)
            self.check_emails(model)
            self.check_decimals(model)
            self.check_dates(model)
            self.check_uuids(model)
            self.check_foreign_keys(model)
            self.check_tenant_consistency(model)

        self.report()

        blockers = [f for f in self.findings if f.severity == "BLOCKER"]
        if options["strict"] and blockers:
            raise SystemExit(1)

    def warn_about_rls(self):
        """A PostgreSQL run with policies installed and no tenant bound sees no
        rows at all, which would print a clean bill of health for a database
        full of problems. Say so rather than let the output mislead."""
        policies = self.scalar(
            "SELECT count(*) FROM pg_policy WHERE polname = 'tenant_isolation'"
        )
        if policies:
            self.stdout.write(self.style.WARNING(
                f"  NOTE: {policies} row-level security policies are active on this "
                "database.\n"
                "        Tenant-owned tables will report zero rows unless a tenant is\n"
                "        bound, so a clean result here proves nothing. This command is\n"
                "        meant for the *source* database before migration."
            ))

    def collect_models(self):
        audited, missing = [], []
        for model in apps.get_models():
            meta = model._meta
            if meta.proxy or not meta.managed:
                continue
            if not self.table_exists(meta.db_table):
                missing.append(meta.label)
                continue
            audited.append(model)
        if missing:
            self.stdout.write(self.style.WARNING(
                f"  {len(missing)} model(s) have no table in this database — the schema "
                f"is behind the code:\n        " + ", ".join(sorted(missing))
            ))
        return sorted(audited, key=lambda m: m._meta.label)

    def add(self, *args, **kwargs):
        self.findings.append(Finding(*args, **kwargs))

    def sample_pks(self, table, where, params=None, alias=None):
        """Offending primary keys. `alias` must match the alias used in `where`
        — rewriting the predicate to drop it silently changes its meaning,
        which produced empty sample lists for the cross-tenant check."""
        if not self.samples:
            return []
        source = f"{self.q(table)} {alias}" if alias else self.q(table)
        pk = f"{alias}.{self.q('id')}" if alias else self.q('id')
        rows = self.fetch(
            f"SELECT {pk} FROM {source} WHERE {where} LIMIT {self.samples}", params
        )
        return [r[0] for r in rows]

    def raw_text(self, table, column):
        """Read a column as text, bypassing the driver's type converters.

        Django registers converters for date/datetime columns on SQLite, and a
        value they cannot parse comes back as None — so the offending text is
        invisible in Python exactly when it matters. CAST in SQL sidesteps that
        and shows what is actually stored.
        """
        return self.fetch(
            f"SELECT {self.q('id')}, CAST({self.q(column)} AS TEXT) "
            f"FROM {self.q(table)}"
        )

    # ------------------------------------------------------------------- checks

    def check_max_length(self, model):
        """VARCHAR(n) is advisory in SQLite, enforced in PostgreSQL."""
        table = model._meta.db_table
        for field in self.concrete_fields(model):
            n = getattr(field, "max_length", None)
            if not n or not isinstance(field, (models.CharField, models.TextField)):
                continue
            col = field.column
            where = f"{self.q(col)} IS NOT NULL AND length({self.q(col)}) > %s"
            count = self.scalar(
                f"SELECT count(*) FROM {self.q(table)} WHERE {where}", [n]
            )
            if count:
                longest = self.scalar(
                    f"SELECT max(length({self.q(col)})) FROM {self.q(table)}"
                )
                self.add(
                    "BLOCKER", "max_length overflow", table, col, count,
                    f"declared varchar({n}), longest value is {longest}",
                    self.sample_pks(table, where, [n]),
                )

    def check_not_null(self, model):
        table = model._meta.db_table
        for field in self.concrete_fields(model):
            if field.null or field.primary_key:
                continue
            col = field.column
            where = f"{self.q(col)} IS NULL"
            count = self.scalar(f"SELECT count(*) FROM {self.q(table)} WHERE {where}")
            if count:
                self.add(
                    "BLOCKER", "NULL in NOT NULL column", table, col, count,
                    "column is declared NOT NULL",
                    self.sample_pks(table, where),
                )

    def check_uniqueness(self, model):
        table = model._meta.db_table
        groups = []
        for field in self.concrete_fields(model):
            if field.unique and not field.primary_key:
                groups.append(([field.column], f"unique=True on {field.name}"))
        for constraint in model._meta.constraints:
            if isinstance(constraint, models.UniqueConstraint) and constraint.fields:
                try:
                    cols = [model._meta.get_field(f).column for f in constraint.fields]
                except Exception:
                    continue
                groups.append((cols, f"UniqueConstraint {constraint.name}"))
        for cols, detail in groups:
            quoted = ", ".join(self.q(c) for c in cols)
            not_null = " AND ".join(f"{self.q(c)} IS NOT NULL" for c in cols)
            rows = self.fetch(
                f"SELECT {quoted}, count(*) FROM {self.q(table)} "
                f"WHERE {not_null} GROUP BY {quoted} HAVING count(*) > 1 "
                f"LIMIT {max(self.samples, 1)}"
            )
            if rows:
                total = self.scalar(
                    f"SELECT count(*) FROM (SELECT 1 FROM {self.q(table)} "
                    f"WHERE {not_null} GROUP BY {quoted} HAVING count(*) > 1) x"
                )
                self.add(
                    "BLOCKER", "duplicate values", table, ",".join(cols), total, detail,
                    [f"{r[:-1]} x{r[-1]}" for r in rows],
                )

    def check_emails(self, model):
        """Malformed addresses are a warning, not a blocker: PostgreSQL stores
        them happily. They break outbound mail, which is a real defect but not a
        migration failure."""
        table = model._meta.db_table
        for field in self.concrete_fields(model):
            if not isinstance(field, models.EmailField):
                continue
            col = field.column
            rows = self.fetch(
                f"SELECT {self.q('id')}, {self.q(col)} FROM {self.q(table)} "
                f"WHERE {self.q(col)} IS NOT NULL AND {self.q(col)} <> ''"
            )
            bad = []
            for pk, value in rows:
                try:
                    validate_email(value)
                except ValidationError:
                    bad.append(f"{pk}: {value!r}")
            if bad:
                self.add(
                    "WARNING", "malformed email", table, col, len(bad),
                    "fails Django's email validation",
                    bad[: self.samples],
                )

    def check_decimals(self, model):
        table = model._meta.db_table
        for field in self.concrete_fields(model):
            if not isinstance(field, models.DecimalField):
                continue
            col = field.column
            rows = [(pk, raw) for pk, raw in self.raw_text(table, col) if raw is not None]
            overflow, negative, unparseable = [], [], []
            whole_digits = (field.max_digits or 0) - (field.decimal_places or 0)
            floors = [
                v.limit_value for v in field.validators
                if hasattr(v, "limit_value") and type(v).__name__ == "MinValueValidator"
            ]
            for pk, raw in rows:
                try:
                    value = Decimal(str(raw))
                except (InvalidOperation, ValueError, TypeError):
                    unparseable.append(f"{pk}: {raw!r}")
                    continue
                digits = value.as_tuple()
                if len(digits.digits) + min(digits.exponent, 0) > whole_digits:
                    overflow.append(f"{pk}: {value}")
                if floors and value < Decimal(str(min(floors))):
                    negative.append(f"{pk}: {value}")
            if unparseable:
                self.add("BLOCKER", "unparseable decimal", table, col,
                         len(unparseable), "not a valid number",
                         unparseable[: self.samples])
            if overflow:
                self.add("BLOCKER", "decimal overflow", table, col, len(overflow),
                         f"exceeds numeric({field.max_digits},{field.decimal_places})",
                         overflow[: self.samples])
            if negative:
                self.add("WARNING", "value below declared minimum", table, col,
                         len(negative),
                         "MinValueValidator is form-level only, so the database "
                         "already holds these",
                         negative[: self.samples])

    def check_dates(self, model):
        """SQLite keeps dates as text, so a malformed value survives until a
        real date/timestamp column rejects it."""
        table = model._meta.db_table
        for field in self.concrete_fields(model):
            if not isinstance(field, (models.DateField, models.DateTimeField)):
                continue
            col = field.column
            bad = []
            for pk, raw in self.raw_text(table, col):
                if raw is None:
                    continue  # genuinely NULL — check_not_null covers that
                if isinstance(raw, (datetime, date)):
                    continue
                text = str(raw)
                parsed = False
                for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S",
                            "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                    try:
                        datetime.strptime(text[:26], fmt)
                        parsed = True
                        break
                    except ValueError:
                        continue
                if not parsed:
                    bad.append(f"{pk}: {raw!r}")
            if bad:
                self.add("BLOCKER", "unparseable date/timestamp", table, col,
                         len(bad), "not an ISO date PostgreSQL will accept",
                         bad[: self.samples])

    def check_uuids(self, model):
        table = model._meta.db_table
        for field in self.concrete_fields(model):
            if not isinstance(field, models.UUIDField):
                continue
            col = field.column
            bad, empty = [], []
            for pk, raw in self.raw_text(table, col):
                if raw is None or raw == "":
                    empty.append(str(pk))
                    continue
                try:
                    uuid_module.UUID(str(raw))
                except (ValueError, AttributeError, TypeError):
                    bad.append(f"{pk}: {raw!r}")
            if empty:
                self.add("BLOCKER", "missing UUID", table, col, len(empty),
                         "public identifier is null/empty", empty[: self.samples])
            if bad:
                self.add("BLOCKER", "malformed UUID", table, col, len(bad),
                         "PostgreSQL's uuid type will reject this",
                         bad[: self.samples])

    def check_foreign_keys(self, model):
        """SQLite only enforces foreign keys when the connection asks it to, so
        rows written outside Django can point at nothing."""
        table = model._meta.db_table
        for field in self.concrete_fields(model):
            if not isinstance(field, models.ForeignKey):
                continue
            target = field.target_field.model
            target_table = target._meta.db_table
            if not self.table_exists(target_table):
                continue
            col, target_col = field.column, field.target_field.column
            where = (
                f"src.{self.q(col)} IS NOT NULL AND NOT EXISTS ("
                f"SELECT 1 FROM {self.q(target_table)} tgt "
                f"WHERE tgt.{self.q(target_col)} = src.{self.q(col)})"
            )
            count = self.scalar(
                f"SELECT count(*) FROM {self.q(table)} src WHERE {where}"
            )
            if count:
                rows = self.fetch(
                    f"SELECT src.{self.q('id')}, src.{self.q(col)} "
                    f"FROM {self.q(table)} src WHERE {where} LIMIT {max(self.samples,1)}"
                )
                self.add(
                    "BLOCKER", "orphaned foreign key", table, col, count,
                    f"points at missing {target._meta.label}",
                    [f"row {r[0]} -> {col}={r[1]}" for r in rows],
                )

    def check_tenant_consistency(self, model):
        """A row whose tenant disagrees with its parent's tenant is a genuine
        isolation defect: under RLS one of the two becomes invisible, and which
        one depends on which tenant is bound."""
        meta = model._meta
        try:
            tenant_field = meta.get_field("tenant")
        except Exception:
            return
        if not tenant_field.is_relation:
            return
        table = meta.db_table

        for field in self.concrete_fields(model):
            if not isinstance(field, models.ForeignKey) or field.name == "tenant":
                continue
            related = field.target_field.model
            try:
                related_tenant = related._meta.get_field("tenant")
            except Exception:
                continue
            if not related_tenant.is_relation or related_tenant.null:
                continue
            related_table = related._meta.db_table
            if not self.table_exists(related_table):
                continue
            where = (
                f"src.{self.q(field.column)} IS NOT NULL AND EXISTS ("
                f"SELECT 1 FROM {self.q(related_table)} tgt "
                f"WHERE tgt.{self.q(field.target_field.column)} = src.{self.q(field.column)} "
                f"AND tgt.{self.q(related_tenant.column)} <> src.{self.q(tenant_field.column)})"
            )
            count = self.scalar(
                f"SELECT count(*) FROM {self.q(table)} src WHERE {where}"
            )
            if count:
                self.add(
                    "BLOCKER", "cross-tenant reference", table, field.column, count,
                    f"row's tenant differs from its {related._meta.label}'s tenant",
                    self.sample_pks(table, where, alias="src"),
                )

    # ------------------------------------------------------------------- output

    def report(self):
        blockers = [f for f in self.findings if f.severity == "BLOCKER"]
        warnings = [f for f in self.findings if f.severity == "WARNING"]

        if not self.findings:
            self.stdout.write(self.style.SUCCESS(
                "  No incompatible values found."
            ))
        for label, group, style in (
            ("BLOCKERS — these will fail the migration", blockers, self.style.ERROR),
            ("WARNINGS — these migrate, but are defects", warnings, self.style.WARNING),
        ):
            if not group:
                continue
            self.stdout.write("")
            self.stdout.write(style(f"  {label}: {len(group)}"))
            for f in sorted(group, key=lambda x: (x.category, x.table, x.column)):
                self.stdout.write(
                    f"    [{f.category}] {f.table}.{f.column} — {f.count} row(s)"
                )
                if f.detail:
                    self.stdout.write(f"        {f.detail}")
                for s in f.samples:
                    self.stdout.write(f"        - {s}")

        self.stdout.write("")
        self.stdout.write(
            f"  Summary: {len(blockers)} blocker(s), {len(warnings)} warning(s), "
            f"{len(self.findings)} finding(s) total."
        )
        self.stdout.write(
            "  Nothing was modified. Remediation is a judgement call on real "
            "records; see docs/06-implementation-progress.md."
        )
        self.stdout.write("")
