"""Staff attendance — one row per employee per day, recorded per clinic.

Recording is administrative (clinic Admin for their clinic, Owner for any).
The daily sheet is the screen people actually use: every employee of the
clinic, with today's status, saved in one request.
"""

from datetime import date as date_type

from django.db import transaction
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.roles import scope_queryset_to_user
from api.permissions import IsClinicAdmin
from api.relations import TenantScopedRelatedField
from api.serializers.common import ClinicSerializer
from api.viewsets import ClinicViewSet
from employees.models import Attendance, Employee
from tenants.context import get_current_tenant


class AttendanceSerializer(ClinicSerializer):
    employee = TenantScopedRelatedField(model=Employee, branch_field="branch")
    employee_name = serializers.CharField(source="employee.name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)

    class Meta:
        model = Attendance
        fields = [
            "uuid", "employee", "employee_name", "branch_name", "date", "status",
            "check_in", "check_out", "minutes_late", "notes", "updated_at",
        ]
        read_only_fields = ["updated_at"]

    def validate(self, attrs):
        check_in = attrs.get("check_in", getattr(self.instance, "check_in", None))
        check_out = attrs.get("check_out", getattr(self.instance, "check_out", None))
        if check_in and check_out and check_out < check_in:
            raise serializers.ValidationError({"check_out": "وقت الانصراف قبل وقت الحضور."})
        if attrs.get("status") in (Attendance.Status.ABSENT, Attendance.Status.LEAVE):
            attrs["check_in"] = attrs["check_out"] = None
            attrs["minutes_late"] = None
        employee = attrs.get("employee", getattr(self.instance, "employee", None))
        day = attrs.get("date", getattr(self.instance, "date", None))
        if employee and day:
            clash = Attendance.objects.filter(employee=employee, date=day)
            if self.instance:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError({"date": "الحضور مسجل لهذا الموظف في هذا اليوم."})
        return attrs


class SheetEntry(serializers.Serializer):
    employee = TenantScopedRelatedField(model=Employee, branch_field="branch")
    status = serializers.ChoiceField(choices=Attendance.Status.choices)
    check_in = serializers.TimeField(required=False, allow_null=True)
    check_out = serializers.TimeField(required=False, allow_null=True)
    minutes_late = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=1440)
    notes = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class SheetSerializer(serializers.Serializer):
    date = serializers.DateField()
    entries = SheetEntry(many=True)

    def validate_date(self, value):
        if value > date_type.today():
            raise serializers.ValidationError("لا يمكن تسجيل الحضور لتاريخ قادم.")
        return value


class AttendanceViewSet(ClinicViewSet):
    queryset = Attendance.objects.all()
    serializer_class = AttendanceSerializer
    permission_classes = [IsClinicAdmin]
    created_by_field = "recorded_by"
    ordering = ["-date", "employee__name"]

    def filter_tenant_queryset(self, queryset):
        queryset = queryset.select_related("employee", "branch")
        params = self.request.query_params
        for key, lookup in (("date", "date"), ("from", "date__gte"), ("to", "date__lte"),
                            ("status", "status")):
            if params.get(key):
                queryset = queryset.filter(**{lookup: params[key]})
        if params.get("employee"):
            queryset = queryset.filter(employee__uuid=params["employee"])
        return queryset

    def perform_create(self, serializer):
        serializer.validated_data["branch"] = serializer.validated_data["employee"].branch
        super().perform_create(serializer)

    @action(detail=False, methods=["get", "post"], url_path="sheet")
    def sheet(self, request):
        """The day's sheet: every employee the caller manages, with their
        status for the day. GET reads it; POST saves it in one transaction."""
        employees = scope_queryset_to_user(Employee.objects.all(), request.user).select_related(
            "branch", "employee_type"
        ).order_by("branch__name", "name")

        if request.method == "POST":
            serializer = SheetSerializer(data=request.data, context={"request": request})
            serializer.is_valid(raise_exception=True)
            day = serializer.validated_data["date"]
            tenant = get_current_tenant()
            with transaction.atomic():
                for entry in serializer.validated_data["entries"]:
                    employee = entry.pop("employee")
                    if entry["status"] in (Attendance.Status.ABSENT, Attendance.Status.LEAVE):
                        entry.update(check_in=None, check_out=None, minutes_late=None)
                    Attendance.objects.update_or_create(
                        employee=employee, date=day,
                        defaults={**entry, "tenant": tenant, "branch": employee.branch,
                                  "recorded_by": request.user},
                    )
            day_text = day.isoformat()
        else:
            day_text = request.query_params.get("date") or date_type.today().isoformat()

        branch = request.query_params.get("branch")
        if branch:
            employees = employees.filter(branch__uuid=branch)
        rows = {a.employee_id: a for a in Attendance.objects.filter(date=day_text, employee__in=employees)}
        return Response({
            "date": day_text,
            "entries": [
                {
                    "employee": str(e.uuid),
                    "employee_name": e.name,
                    "employee_type": getattr(e.employee_type, "name", None),
                    "branch_name": e.branch.name if e.branch else None,
                    "attendance": AttendanceSerializer(rows[e.pk]).data if e.pk in rows else None,
                }
                for e in employees
            ],
        })
