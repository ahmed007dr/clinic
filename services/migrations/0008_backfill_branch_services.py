"""Enable, in each clinic, the services it already offers today.

`BranchService` is new, so it starts empty — and an empty table would mean no
clinic offers anything on the public page. What a clinic offers today is
whatever its doctors are under contract for, so each active contract line
switches its service on in every clinic that doctor works in (home clinic and
visiting ones). Nothing else is enabled; management turns the rest on.

Each group is read with its own database binding: the isolation policies
(tenants.0005) hide every other group's rows, so this loops over groups rather
than sweeping the table once — a sweep would quietly find nothing on
PostgreSQL.
"""

from django.db import migrations

from tenants.context import bind_database_tenant, restore_database_tenant


def backfill(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    Rate = apps.get_model("billing", "DoctorServiceRate")
    Employee = apps.get_model("employees", "Employee")
    BranchService = apps.get_model("services", "BranchService")

    for tenant in Tenant.objects.all():
        previous = bind_database_tenant(tenant)
        try:
            extras = {}
            for row in Employee.extra_branches.through.objects.all():
                extras.setdefault(row.employee_id, set()).add(row.branch_id)
            wanted = set()
            rates = Rate.objects.filter(
                tenant=tenant, is_active=True, service__is_active=True,
                doctor__employee_type__name="Doctor",
            ).select_related("doctor")
            for rate in rates:
                for branch_id in {rate.doctor.branch_id, *extras.get(rate.doctor_id, ())}:
                    wanted.add((branch_id, rate.service_id))
            existing = set(BranchService.objects.values_list("branch_id", "service_id"))
            BranchService.objects.bulk_create([
                BranchService(tenant=tenant, branch_id=branch_id, service_id=service_id)
                for branch_id, service_id in sorted(wanted - existing)
            ])
        finally:
            restore_database_tenant(previous)


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0007_branch_service_and_duration"),
        ("billing", "0008_doctor_contracts_commissions"),
        ("employees", "0011_employee_show_publicly"),
        ("tenants", "0021_tenant_public_media"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
