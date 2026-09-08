# accounts/apps.py
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    # Role seeding moved to tenants.provisioning (SEC-010) — roles are
    # tenant-owned, so they belong to tenant setup rather than to migrate.
    #
    # Note: accounts/signals.py defines set_default_role but nothing has ever
    # imported it, so that receiver has never been connected. Left as-is
    # deliberately — switching dormant behaviour on is a separate decision,
    # not a side effect of this refactor.
