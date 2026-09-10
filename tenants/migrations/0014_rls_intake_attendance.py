"""Extend the isolation policies to intake and attendance.

`medical.PatientMedicalProfile`, `PatientCondition`, `PatientIntake` and
`employees.Attendance` all carry a non-nullable tenant, so the derivation picks
them up like every other tenant-owned model. The first three hold a patient's
self-reported medical history — exactly the data a missing policy must never
expose to another group.
"""

from django.db import migrations

from tenants.rls import apply_tenant_policies, drop_tenant_policies


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0013_rls_portal"),
        ("medical", "0009_patientmedicalprofile_patientcondition_patientintake"),
        ("employees", "0007_attendance"),
    ]

    operations = [
        migrations.RunPython(apply_tenant_policies, drop_tenant_policies),
    ]
