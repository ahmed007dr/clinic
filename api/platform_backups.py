"""Backups and exports in the developer portal (docs/06 PLAT-006).

Reading the list is for any operator; starting a backup, changing the policy,
asking cPanel for a full-account backup, and downloading anything are for full
administrators only — a backup is every clinic's medical records.
"""

import tempfile
from pathlib import Path

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from platform_admin import backups, exporter, vault
from platform_admin.audit import record
from platform_admin.models import BackupPolicy, BackupRun, IntegrationCredential
from platform_admin.permissions import is_platform_super
from tenants.models import Tenant

from .platform import IsPlatformStaff


def _refuse_support(request):
    if not is_platform_super(request.user):
        return Response({"detail": "للمدير الكامل فقط."}, status=403)
    return None


def policy_payload(policy):
    return {
        "keep_local": policy.keep_local,
        "upload_to_drive": policy.upload_to_drive,
        "keep_drive": policy.keep_drive,
        "include_files": policy.include_files,
    }


def run_payload(row):
    return {
        "id": row.id,
        "status": row.status,
        "status_label": row.get_status_display(),
        "file_name": row.file_name,
        "on_server": bool(row.file_name) and (backups.backup_root() / row.file_name).exists(),
        "size": row.size,
        "sha256": row.sha256,
        "groups": row.groups,
        "drive_file_id": row.drive_file_id,
        "drive_error": row.drive_error,
        "error": row.error,
        "trigger": row.trigger,
        "created_by": getattr(row.created_by, "email", None),
        "started_at": row.started_at,
        "finished_at": row.finished_at,
    }


def _configured(kind):
    try:
        return vault.resolve(kind) is not None
    except vault.VaultError:
        return False


class BackupListView(APIView):
    permission_classes = [IsPlatformStaff]

    def get(self, request):
        return Response({
            "policy": policy_payload(BackupPolicy.current()),
            "drive_configured": _configured(IntegrationCredential.Kind.GOOGLE_DRIVE),
            "cpanel_configured": _configured(IntegrationCredential.Kind.CPANEL),
            "runs": [run_payload(row) for row in BackupRun.objects.select_related("created_by")[:50]],
        })

    def post(self, request):
        try:
            row = backups.start_in_background(actor=request.user)
        except backups.BackupError as error:
            return Response({"detail": str(error)}, status=400)
        record(request, None, "backup started", f"run #{row.pk}", model_name="BackupRun", object_id=row.pk)
        return Response(run_payload(row), status=202)


class BackupPolicyView(APIView):
    permission_classes = [IsPlatformStaff]

    def patch(self, request):
        policy = BackupPolicy.current()
        for name in ("keep_local", "keep_drive"):
            if name in request.data:
                try:
                    setattr(policy, name, min(max(int(request.data[name]), 1), 365))
                except (TypeError, ValueError):
                    return Response({"detail": "العدد رقم صحيح."}, status=400)
        for name in ("upload_to_drive", "include_files"):
            if name in request.data:
                setattr(policy, name, bool(request.data[name]))
        policy.save()
        record(request, None, "backup policy", str(policy_payload(policy)), model_name="BackupPolicy",
               object_id=policy.pk)
        return Response(policy_payload(policy))


class CpanelBackupView(APIView):
    """Ask cPanel for a full-account backup into the home directory."""

    permission_classes = [IsPlatformStaff]

    def post(self, request):
        try:
            backups.request_cpanel_backup(email=request.user.email)
        except backups.BackupError as error:
            return Response({"detail": str(error)}, status=400)
        record(request, None, "cpanel full backup requested", request.user.email, model_name="BackupRun")
        return Response({"detail": "طلب cPanel النسخة الكاملة؛ تُحفظ في المجلد الرئيسي للحساب ويصلك بريد عند انتهائها."})


class BackupDownloadView(APIView):
    permission_classes = [IsPlatformStaff]

    def get(self, request, pk):
        refused = _refuse_support(request)
        if refused:
            return refused
        row = get_object_or_404(BackupRun, pk=pk, status=BackupRun.Status.DONE)
        path = backups.backup_root() / row.file_name if row.file_name else None
        if path is None or not path.exists():
            raise Http404
        record(request, None, "backup downloaded", row.file_name, model_name="BackupRun", object_id=row.pk)
        return FileResponse(open(path, "rb"), as_attachment=True, filename=row.file_name)


class TenantExportView(APIView):
    """One group's data as a zip (`?files=0` for the data alone) — to hand
    over to the group, or to import elsewhere (platform_admin/importer.py)."""

    permission_classes = [IsPlatformStaff]

    def get(self, request, uuid):
        refused = _refuse_support(request)
        if refused:
            return refused
        tenant = get_object_or_404(Tenant, uuid=uuid)
        include_files = request.query_params.get("files") != "0"
        handle = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        handle.close()
        manifest = exporter.export_tenant(tenant, handle.name, include_files=include_files)
        record(
            request, tenant, "group exported",
            f"{sum(manifest['counts'].values())} rows, files {'yes' if include_files else 'no'}",
            model_name="Tenant", object_id=tenant.pk,
        )
        name = f"{tenant.slug}-{timezone.now():%Y%m%d-%H%M}.zip"
        response = FileResponse(_deleting(handle.name), as_attachment=True, filename=name)
        response["Cache-Control"] = "no-store"
        return response


class _deleting:
    """A file that removes itself once the response has streamed it."""

    def __init__(self, path):
        self.path = Path(path)
        self.handle = open(path, "rb")

    def read(self, *args):
        return self.handle.read(*args)

    def close(self):
        self.handle.close()
        try:
            self.path.unlink()
        except OSError:
            pass


class GroupImportView(APIView):
    """POST multipart {file, slug, name?, accounts=1|0, dry_run=1|0}: bring a
    group export in as a new group (platform_admin/importer.py). Run it with
    dry_run=1 first; it reports what would be created and every problem."""

    permission_classes = [IsPlatformStaff]

    def post(self, request):
        from platform_admin.importer import ImportError_, import_group

        upload = request.FILES.get("file")
        if upload is None:
            return Response({"detail": "اختر ملف التصدير (zip)."}, status=400)
        flag = lambda name, default: str(request.data.get(name, default)).lower() in ("1", "true", "yes")  # noqa: E731
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as handle:
            for chunk in upload.chunks():
                handle.write(chunk)
            path = handle.name
        try:
            report = import_group(
                path, slug=request.data.get("slug"), name=request.data.get("name") or None,
                accounts=flag("accounts", "1"), dry_run=flag("dry_run", "1"), actor=request.user,
            )
        except ImportError_ as error:
            return Response({"detail": str(error)}, status=400)
        finally:
            Path(path).unlink(missing_ok=True)
        if report.get("tenant"):
            tenant = Tenant.objects.get(uuid=report["tenant"]["uuid"])
            record(request, tenant, "group imported",
                   f"from {report['source'].get('slug')}: {sum(report['counts'].values())} rows, {report['files']} files",
                   model_name="Tenant", object_id=tenant.pk)
        return Response(report, status=201 if report.get("tenant") else 200)
