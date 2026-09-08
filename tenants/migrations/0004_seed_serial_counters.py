from datetime import datetime

from django.db import migrations

# (app_label, model, scope) — scope must match the strings passed to
# SerialCounter.next_serial() from each model's save().
SOURCES = [
    ("patients", "Patient", "patient"),
    ("appointments", "Appointment", "appointment"),
    ("employees", "Employee", "employee"),
    ("notifications", "Notification", "notification"),
]


def seed_counters(apps, schema_editor):
    """Carry existing serial numbers over into the new counters.

    Without this, a counter starting from zero would re-issue numbers that
    existing rows already hold — every insert on a day that already has
    records would collide with the (tenant, serial_number) constraint.
    """
    SerialCounter = apps.get_model("tenants", "SerialCounter")
    highest = {}

    for app_label, model_name, scope in SOURCES:
        model = apps.get_model(app_label, model_name)
        rows = model.objects.exclude(serial_number="").values_list("tenant_id", "serial_number")
        for tenant_id, serial in rows.iterator():
            if tenant_id is None or not serial:
                continue
            date_part, sep, seq_part = serial.partition("-")
            if not sep:
                continue
            try:
                day = datetime.strptime(date_part, "%Y%m%d").date()
                seq = int(seq_part)
            except ValueError:
                continue  # hand-edited or legacy format — leave it alone
            key = (tenant_id, scope, day)
            if seq > highest.get(key, 0):
                highest[key] = seq

    for (tenant_id, scope, day), last_value in highest.items():
        SerialCounter.objects.update_or_create(
            tenant_id=tenant_id,
            scope=scope,
            date=day,
            defaults={"last_value": last_value},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0003_serialcounter_and_more"),
        ("patients", "0003_alter_patient_serial_number_and_more"),
        ("appointments", "0003_alter_appointment_price_and_more"),
        ("employees", "0003_alter_employee_national_id_and_more"),
        ("notifications", "0003_alter_notification_serial_number_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_counters, migrations.RunPython.noop),
    ]
