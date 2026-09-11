"""Bringing a group's export (platform_admin/exporter.py) into this
installation — as a new group, always with a dry run first.

Used to restore a group from a backup (unzip `groups/<slug>.zip` out of a
decrypted backup) or to move a group from another installation.

How rows are written:

* every row gets a new primary key; references between the group's own rows
  are rewritten through an old→new map, model by model, parents first
  (exporter.tenant_models); a reference to a row not created yet (a
  self-reference, a cycle) is filled in once everything exists;
* references to platform records: the group → the new group; a plan → the
  plan with the same code here; an account outside the export (a platform
  operator who wrote an audit entry) → empty; anything else unresolvable →
  empty when the field allows it, otherwise a problem that stops the import;
* the rows' public uuids are kept when restoring a group that no longer
  exists here, and regenerated when copying one that does;
* rows are bulk-created, so no save() side effects run — no doctor emails, no
  commission recalculation, no audit entry per row; one audit entry records
  the import;
* files go back into their storage; a name already taken gets a new one and
  the row is updated to it.

Accounts come with their password hashes; an email address already used here
is a problem — import without accounts (`accounts=False`) to bring the data
alone.
"""

import json
import uuid as uuid_module
import zipfile
from collections import defaultdict

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core import serializers
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.validators import validate_slug
from django.db import models, transaction

from subscriptions.models import Plan
from tenants.context import tenant_context
from tenants.models import Tenant

from .exporter import FORMAT, VERSION, file_fields, label, tenant_models

User = get_user_model()
SKIP_M2M = {"auth.group", "auth.permission"}


class ImportError_(ValueError):
    """The message is for the operator."""


def read(path):
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise ImportError_("الملف ليس ملف تصدير صالحاً (zip).")
    try:
        manifest = json.loads(archive.read("manifest.json"))
        data = archive.read("data.json").decode("utf-8")
    except (KeyError, ValueError):
        archive.close()
        raise ImportError_("ملف التصدير ناقص (manifest.json / data.json).")
    if manifest.get("format") != FORMAT or manifest.get("version") != VERSION:
        archive.close()
        raise ImportError_("صيغة ملف التصدير غير مدعومة.")
    return archive, manifest, data


def import_group(path, *, slug, name=None, accounts=True, dry_run=True, actor=None):
    """Returns a report: {ok, dry_run, problems, warnings, counts, files,
    tenant?}. Nothing is written when `dry_run` or when there are problems."""
    archive, manifest, data = read(path)
    try:
        return _import(archive, manifest, data, slug, name, accounts, dry_run)
    finally:
        archive.close()


def _import(archive, manifest, data, slug, name, accounts, dry_run):
    problems, warnings = [], []
    slug = (slug or "").strip().lower()
    try:
        validate_slug(slug)
    except ValidationError:
        problems.append("المعرّف يقبل حروفاً لاتينية وأرقاماً و - فقط.")
    if Tenant.objects.filter(slug=slug).exists():
        problems.append(f"يوجد مجموعة بالمعرّف «{slug}» بالفعل.")

    known = {label(m): m for m in tenant_models()}
    if not accounts:
        known.pop(label(User), None)
    by_model = defaultdict(list)
    unknown = set()
    for item in serializers.deserialize("json", data, ignorenonexistent=True, handle_forward_references=True):
        model_label = label(type(item.object))
        if model_label not in known:
            if model_label != label(User):
                unknown.add(model_label)
            continue
        by_model[model_label].append(item)
    if unknown:
        warnings.append("جداول غير موجودة هنا وتم تجاهلها: " + "، ".join(sorted(unknown)))

    if accounts:
        emails = [item.object.email for item in by_model.get(label(User), []) if item.object.email]
        taken = sorted(User.objects.filter(email__in=emails).values_list("email", flat=True))
        if taken:
            problems.append("بريد مستخدم هنا بالفعل: " + "، ".join(taken[:10])
                            + (" …" if len(taken) > 10 else "") + " — استورد بدون الحسابات أو غيّرها أولاً.")

    plan_codes = manifest.get("plans") or {}
    plans_here = dict(Plan.objects.values_list("code", "pk"))
    plan_map = {}
    for old, code in plan_codes.items():
        if code in plans_here:
            plan_map[int(old)] = plans_here[code]
        else:
            problems.append(f"الباقة «{code}» غير موجودة هنا.")

    counts = {model_label: len(items) for model_label, items in by_model.items()}
    report = {
        "ok": not problems, "dry_run": dry_run or bool(problems), "problems": problems, "warnings": warnings,
        "counts": counts, "source": manifest.get("tenant"), "files": 0,
    }
    if problems or dry_run:
        report["files"] = sum(1 for n in archive.namelist() if n.startswith("files/") and not n.endswith("/"))
        return report

    with transaction.atomic():
        source = manifest["tenant"]
        restoring = not Tenant.objects.filter(uuid=source["uuid"]).exists()
        tenant = Tenant.objects.create(
            name=(name or source["name"])[:200], slug=slug, status=Tenant.Status.TRIAL,
            portal_show_diagnosis=source.get("portal_show_diagnosis", False),
            portal_self_registration=source.get("portal_self_registration", False),
            **({"uuid": source["uuid"]} if restoring else {}),
        )
        with tenant_context(tenant):
            maps, created = _write_rows(tenant, known, by_model, plan_map, restoring, warnings)
            report["files"] = _write_files(archive, known, created)
        report["tenant"] = {"uuid": str(tenant.uuid), "slug": tenant.slug, "name": tenant.name}
        report["dry_run"] = False
        report["restored_uuids"] = restoring
    return report


def _write_rows(tenant, known, by_model, plan_map, restoring, warnings):
    maps = defaultdict(dict)      # label -> {old pk: new pk}
    created = defaultdict(list)   # label -> [(new instance, old instance values for files)]
    later = []                    # (model, new pk, attname, target label, old target pk)
    nulled = defaultdict(int)
    m2m = []

    for model in tenant_models():
        model_label = label(model)
        items = by_model.get(model_label)
        if not items or model_label not in known:
            continue
        objects, olds = [], []
        for item in items:
            obj = item.object
            olds.append(obj.pk)
            obj.pk = None
            if hasattr(obj, "id"):
                obj.id = None
            obj.tenant_id = tenant.pk
            if not restoring and any(f.name == "uuid" for f in model._meta.concrete_fields):
                obj.uuid = uuid_module.uuid4()
            for field in model._meta.concrete_fields:
                if not isinstance(field, models.ForeignKey) or field.name == "tenant":
                    continue
                old_target = getattr(obj, field.attname)
                if old_target is None:
                    continue
                target_label = label(field.related_model)
                if field.related_model is Tenant:
                    setattr(obj, field.attname, tenant.pk)
                elif target_label == "subscriptions.plan":
                    setattr(obj, field.attname, plan_map.get(old_target))
                elif target_label in known:
                    if old_target in maps[target_label]:
                        setattr(obj, field.attname, maps[target_label][old_target])
                    else:
                        # Not created yet (self-reference or cycle): later.
                        setattr(obj, field.attname, None)
                        later.append((model, len(objects), field, target_label, old_target))
                        if not field.null:
                            raise ImportError_(f"ترتيب غير قابل للحل في {model_label}.{field.name}")
                else:
                    if field.null:
                        setattr(obj, field.attname, None)
                        nulled[f"{model_label}.{field.name}"] += 1
                    else:
                        raise ImportError_(f"مرجع لا يمكن حله: {model_label}.{field.name}")
            objects.append(obj)
            m2m.append((model, len(objects) - 1, item.m2m_data))
        saved = model._base_manager.bulk_create(objects, batch_size=500)
        for old, new in zip(olds, saved):
            maps[model_label][old] = new.pk
        created[model_label] = saved
        # Resolve this model's deferred references once its rows exist too.
    for model, index, field, target_label, old_target in later:
        row = created[label(model)][index]
        new_target = maps[target_label].get(old_target)
        if new_target is not None:
            model._base_manager.filter(pk=row.pk).update(**{field.attname: new_target})
        elif field.null:
            nulled[f"{label(model)}.{field.name}"] += 1
    for model, index, m2m_data in m2m:
        row = created[label(model)][index]
        for field_name, old_ids in (m2m_data or {}).items():
            field = model._meta.get_field(field_name)
            target_label = label(field.related_model)
            if target_label in SKIP_M2M or target_label not in known:
                continue
            ids = [maps[target_label][i] for i in old_ids if i in maps[target_label]]
            if ids:
                getattr(row, field_name).set(ids)
    for where, count in nulled.items():
        warnings.append(f"{count} مرجعاً خارج المجموعة أُفرغ في {where}")
    return maps, created


def _write_files(archive, known, created):
    written = 0
    names = set(archive.namelist())
    for model_label, rows in created.items():
        model = apps.get_model(model_label)
        for field in file_fields(model):
            from .exporter import _storage_key

            key = _storage_key(field)
            for row in rows:
                name = getattr(row, field.attname).name
                entry = f"files/{key}/{name}"
                if not name or entry not in names:
                    continue
                stored = field.storage.save(name, ContentFile(archive.read(entry)))
                if stored != name:
                    model._base_manager.filter(pk=row.pk).update(**{field.attname: stored})
                written += 1
    return written
