"""Extend the isolation policies to doctors' schedules, time off and holidays.

`appointments.DoctorSchedule`, `DoctorTimeOff` and `BranchHoliday` are
tenant-owned; another group must never read them. Picked up by the derivation
in tenants.rls like every other such model.
"""

from django.db import migrations

from tenants.rls import apply_tenant_policies, drop_tenant_policies


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0023_rls_branch_services"),
        ("appointments", "0009_doctor_schedule_time_off_holidays"),
    ]

    operations = [
        migrations.RunPython(apply_tenant_policies, drop_tenant_policies),
    ]
