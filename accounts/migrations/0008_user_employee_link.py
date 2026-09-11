"""Link each login to the doctor it belongs to.

Visits, bookings and prescriptions name an Employee; accounts are Users; and
nothing joined the two, so a doctor's account could not be limited to that
doctor's own patients. This adds the link, and makes it for existing doctor
accounts where it is unambiguous: one Doctor account and exactly one Employee
in the same group share an email address. Anything less certain is left for an
Admin to link on the staff screen — a doctor linked to the wrong record would
see a colleague's patients, which is the thing this exists to prevent.

Bound per tenant, like accounts.0007, so it works with or without the
row-level security policies installed.
"""

import django.db.models.deletion
from django.db import migrations, models


def bind_tenant(schema_editor, tenant_id):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('app.current_tenant_id', %s, false)",
            [str(tenant_id) if tenant_id is not None else ""],
        )


def link_doctors_by_email(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    User = apps.get_model("accounts", "User")
    Employee = apps.get_model("employees", "Employee")

    for tenant in Tenant.objects.all():
        bind_tenant(schema_editor, tenant.id)
        try:
            taken = set(
                User.objects.filter(tenant=tenant, employee__isnull=False)
                .values_list("employee_id", flat=True)
            )
            for user in User.objects.filter(
                tenant=tenant, role__name="Doctor", employee__isnull=True
            ).exclude(email=""):
                matches = list(
                    Employee.objects.filter(tenant=tenant, email__iexact=user.email)
                    .values_list("pk", flat=True)[:2]
                )
                if len(matches) == 1 and matches[0] not in taken:
                    User.objects.filter(pk=user.pk).update(employee_id=matches[0])
                    taken.add(matches[0])
        finally:
            bind_tenant(schema_editor, None)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_owner_role"),
        ("employees", "0007_attendance"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="employee",
            field=models.OneToOneField(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="user_account", to="employees.employee",
            ),
        ),
        migrations.RunPython(link_doctors_by_email, migrations.RunPython.noop),
    ]
