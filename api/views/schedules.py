"""Doctors' working hours, time off, and clinic holidays (docs/15, Phase 4, D7).

    GET  /api/schedules/?branch=<uuid>[&doctor=<uuid>]   the clinic's doctors, and the chosen doctor's week
    PUT  /api/schedules/                                  `{branch, doctor, days: [{weekday, start_time, end_time,
                                                          break_start?, break_end?}]}` replaces that doctor's week
                                                          at that clinic (a weekday not listed is a day off)
    /api/doctor-time-off/                                 a doctor's leave — CRUD
    /api/branch-holidays/                                 a clinic's closed days — CRUD

The Owner works on any clinic; a clinic's Admin only on their own (another
clinic's uuid is a 404). A clinic Admin cannot close the whole group: a holiday
with no clinic is the Owner's. What these say only shapes the times the website
offers (appointments/availability.py); reception can still book any time by
hand.
"""

from datetime import time

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.roles import is_owner, sees_all_branches
from api.permissions import IsClinicAdmin
from api.relations import TenantScopedRelatedField
from api.serializers.common import ClinicSerializer
from api.viewsets import ClinicViewSet
from appointments.models import BranchHoliday, DoctorSchedule, DoctorTimeOff
from branches.models import Branch
from employees.models import Employee


def _branches_for(user):
    queryset = Branch.objects.all()
    if sees_all_branches(user):
        return queryset
    return queryset.filter(pk=user.branch_id) if user.branch_id else queryset.none()


def doctors_at(branch):
    """Doctors who work at this clinic: based there, or linked to it."""
    from django.db.models import Q

    return (
        Employee.objects.filter(employee_type__name="Doctor")
        .filter(Q(branch=branch) | Q(extra_branches=branch))
        .distinct().order_by("name")
    )


class DaySerializer(serializers.Serializer):
    weekday = serializers.IntegerField(min_value=0, max_value=6)
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    break_start = serializers.TimeField(required=False, allow_null=True)
    break_end = serializers.TimeField(required=False, allow_null=True)

    def validate(self, attrs):
        start, end = attrs["start_time"], attrs["end_time"]
        if end <= start:
            raise serializers.ValidationError({"end_time": "وقت النهاية بعد البداية."})
        b_start, b_end = attrs.get("break_start"), attrs.get("break_end")
        if (b_start is None) != (b_end is None):
            raise serializers.ValidationError({"break_end": "حدّد بداية الاستراحة ونهايتها معًا."})
        if b_start is not None and not (start <= b_start < b_end <= end):
            raise serializers.ValidationError({"break_start": "الاستراحة داخل ساعات العمل."})
        return attrs


class ScheduleSerializer(serializers.Serializer):
    branch = serializers.UUIDField()
    doctor = serializers.UUIDField()
    days = DaySerializer(many=True)

    def validate_days(self, days):
        weekdays = [d["weekday"] for d in days]
        if len(weekdays) != len(set(weekdays)):
            raise serializers.ValidationError("يوم مكرر.")
        return days


def _hhmm(value):
    return value.strftime("%H:%M") if isinstance(value, time) else None


class SchedulesView(APIView):
    permission_classes = [IsClinicAdmin]

    def get(self, request):
        branches = list(_branches_for(request.user).order_by("name"))
        wanted = request.query_params.get("branch")
        branch = (
            get_object_or_404(_branches_for(request.user), uuid=wanted) if wanted
            else (branches[0] if branches else None)
        )
        if branch is None:
            return Response({"branch": None, "branches": [], "doctors": [], "doctor": None, "days": []})
        doctors = list(doctors_at(branch))
        chosen = None
        if request.query_params.get("doctor"):
            chosen = next((d for d in doctors if str(d.uuid) == request.query_params["doctor"]), None)
            if chosen is None:
                return Response({"detail": "الطبيب لا يعمل في هذه العيادة."}, status=404)
        rows = (
            DoctorSchedule.objects.filter(doctor=chosen, branch=branch, is_active=True)
            if chosen else DoctorSchedule.objects.none()
        )
        return Response({
            "branch": {"uuid": str(branch.uuid), "name": branch.name},
            "branches": [{"uuid": str(b.uuid), "name": b.name} for b in branches],
            "doctors": [{"uuid": str(d.uuid), "name": d.name} for d in doctors],
            "doctor": str(chosen.uuid) if chosen else None,
            "days": [
                {
                    "weekday": row.weekday,
                    "start_time": _hhmm(row.start_time), "end_time": _hhmm(row.end_time),
                    "break_start": _hhmm(row.break_start), "break_end": _hhmm(row.break_end),
                }
                for row in rows.order_by("weekday")
            ],
        })

    @transaction.atomic
    def put(self, request):
        serializer = ScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        branch = get_object_or_404(_branches_for(request.user), uuid=data["branch"])
        doctor = get_object_or_404(doctors_at(branch), uuid=data["doctor"])

        wanted = {day["weekday"]: day for day in data["days"]}
        DoctorSchedule.objects.filter(doctor=doctor, branch=branch).exclude(weekday__in=wanted).delete()
        for weekday, day in wanted.items():
            DoctorSchedule.objects.update_or_create(
                tenant=request.user.tenant, doctor=doctor, branch=branch, weekday=weekday,
                defaults={
                    "start_time": day["start_time"], "end_time": day["end_time"],
                    "break_start": day.get("break_start"), "break_end": day.get("break_end"),
                    "is_active": True,
                },
            )
        return Response({"saved": len(wanted)})


class DoctorTimeOffSerializer(ClinicSerializer):
    # Doctors of the caller's clinic only: an Admin cannot book another clinic's
    # doctor off by pasting a uuid (api/relations.py).
    doctor = TenantScopedRelatedField(model=Employee, branch_field="branch")
    doctor_name = serializers.CharField(source="doctor.name", read_only=True)

    class Meta:
        model = DoctorTimeOff
        fields = ["uuid", "doctor", "doctor_name", "start_date", "end_date", "reason"]

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "تاريخ النهاية قبل البداية."})
        doctor = attrs.get("doctor")
        if doctor is not None and getattr(doctor.employee_type, "name", None) != "Doctor":
            raise serializers.ValidationError({"doctor": "اختر طبيبًا."})
        return attrs


class DoctorTimeOffViewSet(ClinicViewSet):
    queryset = DoctorTimeOff.objects.all()
    serializer_class = DoctorTimeOffSerializer
    permission_classes = [IsClinicAdmin]
    branch_field = "doctor__branch"
    ordering = ["-start_date"]

    def filter_tenant_queryset(self, queryset):
        queryset = queryset.select_related("doctor")
        doctor = self.request.query_params.get("doctor")
        return queryset.filter(doctor__uuid=doctor) if doctor else queryset


class BranchHolidaySerializer(ClinicSerializer):
    branch = TenantScopedRelatedField(model=Branch, required=False, allow_null=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)

    class Meta:
        model = BranchHoliday
        fields = ["uuid", "branch", "branch_name", "start_date", "end_date", "name"]

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "تاريخ النهاية قبل البداية."})
        user = self.request_user
        branch = attrs["branch"] if "branch" in attrs else getattr(self.instance, "branch", None)
        if not is_owner(user):
            # A clinic's Admin closes their own clinic, never the whole group.
            if branch is None or branch.pk != user.branch_id:
                raise serializers.ValidationError({"branch": "يمكنك تحديد إجازات عيادتك فقط."})
        return attrs


class BranchHolidayViewSet(ClinicViewSet):
    queryset = BranchHoliday.objects.all()
    serializer_class = BranchHolidaySerializer
    permission_classes = [IsClinicAdmin]
    # Scoped by hand below: a group-wide day has no clinic, so the usual clinic
    # filter would hide it from the Admins it applies to.
    branch_field = None
    ordering = ["-start_date"]

    def perform_destroy(self, instance):
        from rest_framework.exceptions import PermissionDenied

        if not is_owner(self.request.user) and instance.branch_id != self.request.user.branch_id:
            raise PermissionDenied("الإجازة العامة للمجمع من صلاحية المالك.")
        instance.delete()

    def filter_tenant_queryset(self, queryset):
        # An Admin sees their own clinic's closed days and the group-wide ones
        # (read-only for them: validate() refuses to write a group-wide day).
        from django.db.models import Q

        queryset = queryset.select_related("branch")
        user = self.request.user
        if sees_all_branches(user):
            return queryset
        return queryset.filter(Q(branch_id=user.branch_id) | Q(branch__isnull=True))
