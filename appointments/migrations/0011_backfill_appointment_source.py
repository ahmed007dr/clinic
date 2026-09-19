"""Mark the bookings the patient portal already made as coming from the website.

Until `Appointment.source` existed, the only trace of a portal request was the
prefix its notes carry (`portal/views.py`). Those get `source="portal"`; every
other booking keeps the default — it was made by staff.

Each group is read under its own database binding (row-level security hides the
others), so this loops over groups rather than sweeping the table once.
"""

from django.db import migrations

from tenants.context import bind_database_tenant, restore_database_tenant

PREFIX = "[طلب من بوابة المرضى]"


def backfill(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    Appointment = apps.get_model("appointments", "Appointment")
    for tenant in Tenant.objects.all():
        previous = bind_database_tenant(tenant)
        try:
            Appointment.objects.filter(tenant=tenant, notes__startswith=PREFIX).update(source="portal")
        finally:
            restore_database_tenant(previous)


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0010_appointment_source"),
        ("tenants", "0021_tenant_public_media"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
