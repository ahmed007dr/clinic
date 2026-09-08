from django.apps import AppConfig


class EmployeesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "employees"

    # The default "Doctor" employee type is seeded by
    # tenants.provisioning.provision_tenant_defaults (SEC-010).
