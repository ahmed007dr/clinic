"""Current-tenant context.

A contextvar rather than a module-level thread-local: contextvars are
async-safe and are reset by token, so a value cannot survive into the next
request on a reused worker thread. That exact leak (a stale request bleeding
across requests, misattributing audit entries) was a real bug in this
codebase — see BUG-002 — so it is designed out here rather than patched.
"""

import contextlib
import contextvars

_current_tenant = contextvars.ContextVar("current_tenant", default=None)


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
    try:
        yield tenant
    finally:
        _current_tenant.reset(token)
