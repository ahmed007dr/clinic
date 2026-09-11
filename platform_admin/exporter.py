"""One owner group's data as a single file — and the platform's own records.

The export is what a backup, a handover to the group, and an import
(platform_admin/importer.py) all rest on:

    manifest.json   format, version, the group, counts per model
    data.json       every row that belongs to the group (Django's JSON
                    serialisation), accounts included with their password
                    hashes so a restored group can sign in
    files/media/…   photos and logos (MEDIA_ROOT)
    files/attachments/…  medical attachments (MEDICAL_ATTACHMENTS_ROOT)

A group's rows are read inside that group's own `tenant_context`: row-level
security still decides what is visible, so an export can never pick up another
group's row. (A database-level dump is not possible for the application's
role by design — FORCE ROW LEVEL SECURITY applies to it too; see
docs/10-deployment-runbook.md §4.)

"Belongs to the group" = every model with a foreign key named `tenant` to
Tenant, filtered to it. Rows of those models with no tenant (platform
operators, platform-level audit entries) and every model without one are the
platform's, written by `platform_records`.
"""

import json
import zipfile
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.db import models
from django.utils import timezone

from tenants.context import tenant_context
from tenants.models import Tenant

FORMAT = "clinic-group-export"
VERSION = 1
#: Framework tables that are rebuilt, not restored.
SKIP = {"contenttypes.contenttype", "auth.permission", "sessions.session", "admin.logentry", "migrations.migration"}


def label(model):
    return model._meta.label_lower


def has_tenant(model):
    field = next((f for f in model._meta.concrete_fields if f.name == "tenant"), None)
    return isinstance(field, models.ForeignKey) and field.related_model is Tenant


def tenant_models():
    """Every model whose rows belong to a group, parents before children
    (the order an import must create them in)."""
    found = [m for m in apps.get_models() if has_tenant(m) and not m._meta.proxy and label(m) not in SKIP]
    return dependency_order(found)


def dependency_order(found):
    chosen = set(found)
    ordered, seen = [], set()

    def visit(model, trail=()):
        if model in seen or model in trail:
            return
        for field in model._meta.concrete_fields:
            target = getattr(field, "related_model", None)
            if target in chosen and target is not model:
                visit(target, trail + (model,))
        seen.add(model)
        ordered.append(model)

    for model in sorted(found, key=label):
        visit(model)
    return ordered


def rows_of(model, tenant):
    manager = getattr(model, "all_objects", None) or model._base_manager
    return manager.filter(tenant=tenant).order_by("pk")


def _storage_key(field):
    location = Path(getattr(field.storage, "location", settings.MEDIA_ROOT)).resolve()
    if location == Path(settings.MEDICAL_ATTACHMENTS_ROOT).resolve():
        return "attachments"
    return "media"


def file_fields(model):
    return [f for f in model._meta.concrete_fields if isinstance(f, models.FileField)]


def export_tenant(tenant, destination, include_files=True):
    """Write the group's export to `destination` (a path). Returns the manifest."""
    counts, missing = {}, []
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive, \
            tenant_context(tenant):
        objects = []
        for model in tenant_models():
            rows = list(rows_of(model, tenant))
            if not rows:
                continue
            counts[label(model)] = len(rows)
            objects.extend(rows)
            if not include_files:
                continue
            for field in file_fields(model):
                key = _storage_key(field)
                for row in rows:
                    name = getattr(row, field.attname).name
                    if not name:
                        continue
                    try:
                        path = field.storage.path(name)
                    except NotImplementedError:
                        continue
                    if Path(path).is_file():
                        archive.write(path, f"files/{key}/{name}")
                    else:
                        missing.append(f"{key}/{name}")
        archive.writestr("data.json", serializers.serialize("json", objects, indent=None))
        # Rows can point at platform records; name those by something stable
        # across installations (a plan's code, not its id).
        plans = {}
        for row in objects:
            for field in row._meta.concrete_fields:
                if getattr(field, "related_model", None) is not None and label(field.related_model) == "subscriptions.plan":
                    plan_id = getattr(row, field.attname)
                    if plan_id and plan_id not in plans:
                        plans[plan_id] = field.related_model._base_manager.filter(pk=plan_id).values_list(
                            "code", flat=True).first()
        manifest = {
            "format": FORMAT,
            "version": VERSION,
            "created_at": timezone.now().isoformat(),
            "tenant": {
                "uuid": str(tenant.uuid), "name": tenant.name, "slug": tenant.slug, "status": tenant.status,
                "portal_show_diagnosis": tenant.portal_show_diagnosis,
                "portal_self_registration": tenant.portal_self_registration,
            },
            "counts": counts,
            "plans": {str(k): v for k, v in plans.items()},
            "files_included": include_files,
            "missing_files": missing[:200],
        }
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def platform_records(destination):
    """The platform's own rows (everything not belonging to a group) as
    Django JSON — the other half of a full backup."""
    tenant_labels = {label(m) for m in tenant_models()}
    objects = []
    for model in apps.get_models():
        if model._meta.proxy or label(model) in SKIP:
            continue
        manager = model._base_manager
        if label(model) in tenant_labels:
            field = model._meta.get_field("tenant")
            if not field.null:
                continue
            objects.extend(manager.filter(tenant__isnull=True).order_by("pk"))
        else:
            objects.extend(manager.all().order_by("pk"))
    Path(destination).write_text(serializers.serialize("json", objects), encoding="utf-8")
    return len(objects)
