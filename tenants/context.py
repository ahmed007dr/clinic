"""Current-tenant context.

A contextvar rather than a module-level thread-local: contextvars are
async-safe and are reset by token, so a value cannot survive into the next
request on a reused worker thread. That exact leak (a stale request bleeding
across requests, misattributing audit entries) was a real bug in this
codebase — see BUG-002 — so it is designed out here rather than patched.
"""

import contextlib
import contextvars

from django.db import connection

_current_tenant = contextvars.ContextVar("current_tenant", default=None)


def _usable_postgresql_connection():
    """False when SQLite, or when the transaction is already aborted.

    The binding is set and restored in `finally` blocks, which is exactly where
    a poisoned transaction shows up: once a statement has failed, PostgreSQL
    refuses every further statement until rollback, so touching the connection
    here would raise *over* whatever the caller was already failing with and
    hide it. That is the same mistake the audit signal made (BUG-001).

    Skipping is safe rather than merely quiet: SET is transactional in
    PostgreSQL, so the rollback that must follow restores the previous value
    anyway. There is nothing left to undo.
    """
    return connection.vendor == "postgresql" and not connection.needs_rollback


def _set_database_tenant(value):
    if not _usable_postgresql_connection():
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.current_tenant_id', %s, false)", [value])


def bind_database_tenant(tenant):
    """Tell PostgreSQL which tenant this connection is acting for.

    The RLS policies added in tenants.0005 read `app.current_tenant_id`. It is
    set unconditionally — including to '' when there is no tenant — so a value
    can never survive from earlier work on a reused connection. Overwriting
    beats relying on a reset, which is the mistake BUG-002 was.

    Returns the previous value, to be handed back to restore_database_tenant()
    in a finally block. That save/restore pairing is the same discipline the
    contextvar token uses, and it is what lets these scopes nest: a request
    running inside an outer binding puts that binding back on the way out
    instead of blanking it. Without it, any work after an inner scope closes
    reads unbound and silently sees nothing.

    No-op on SQLite, which has no row-level security.
    """
    if not _usable_postgresql_connection():
        return ""
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('app.current_tenant_id', true)")
        previous = cursor.fetchone()[0] or ""
    _set_database_tenant(str(tenant.id) if tenant is not None else "")
    return previous


def restore_database_tenant(previous):
    """Put back what bind_database_tenant() returned."""
    _set_database_tenant(previous or "")


def get_current_tenant():
    return _current_tenant.get()


def set_current_tenant(tenant):
    """Returns a token; pass it to reset_current_tenant in a finally block."""
    return _current_tenant.set(tenant)


def reset_current_tenant(token):
    _current_tenant.reset(token)


@contextlib.contextmanager
def tenant_context(tenant):
    """Scope a block of work to one tenant.

    For everything that runs outside a request/response cycle — scheduled
    reports, management commands, tests.
    """
    token = _current_tenant.set(tenant)
    previous = bind_database_tenant(tenant)
    try:
        yield tenant
    finally:
        _current_tenant.reset(token)
        restore_database_tenant(previous)
