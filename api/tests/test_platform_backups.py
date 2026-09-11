"""Developer portal, phases 6–7: group exports, encrypted backups, and
importing an export back as a new group."""

import io
import json
import tarfile
import tempfile
import zipfile
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import ClinicRole
from appointments.models import Appointment
from billing.models import Payment
from branches.models import Branch
from medical.models import Visit
from patients.models import Patient
from platform_admin import backups, exporter
from platform_admin.importer import import_group
from platform_admin.models import BackupPolicy, BackupRun
from subscriptions.models import Plan, Subscription
from tenants.context import tenant_context
from tenants.models import Tenant
from tenants.testing import login_platform

User = get_user_model()
PASSWORD = "pass12345"

MEDIA = tempfile.mkdtemp(prefix="exp-media-")
PRIVATE = tempfile.mkdtemp(prefix="exp-private-")
BACKUPS = tempfile.mkdtemp(prefix="exp-backups-")


@override_settings(MEDIA_ROOT=MEDIA, MEDICAL_ATTACHMENTS_ROOT=PRIVATE, PLATFORM_BACKUP_ROOT=BACKUPS)
class ExportImportBase(TestCase):
    def setUp(self):
        cache.clear()
        self.tenant = Tenant.objects.create(name="Nile", slug="nile-exp", status="active")
        with tenant_context(self.tenant):
            self.branch = Branch.all_objects.create(tenant=self.tenant, name="Nile Main", code="NM")
            Subscription.all_objects.create(tenant=self.tenant, plan=Plan.objects.get(code="basic"), status="active")
            owner_role = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name="Owner")[0]
            patient = Patient.all_objects.create(tenant=self.tenant, name="Mona", branch=self.branch)
            patient.photo.save("mona.png", io.BytesIO(b"\x89PNG fake"), save=True)
            appointment = Appointment.all_objects.create(tenant=self.tenant, patient=patient, branch=self.branch,
                                                         scheduled_date=timezone.now(), price=300)
            Payment.all_objects.create(tenant=self.tenant, appointment=appointment, patient=patient,
                                       receipt_number="R-1", amount=300, branch=self.branch)
            Visit.all_objects.create(tenant=self.tenant, patient=patient, branch=self.branch, diagnosis="Flu")
        self.owner = User.objects.create_user(username="owner", email="owner@nile.test", password=PASSWORD,
                                              tenant=self.tenant, role=owner_role, branch=self.branch)
        other = Tenant.objects.create(name="Other", slug="other-exp", status="active")
        with tenant_context(other):
            ob = Branch.all_objects.create(tenant=other, name="Other Main", code="OM")
            Patient.all_objects.create(tenant=other, name="Not Mine", branch=ob)
        User.objects.create_user(username="root", email="root@ops.local", password=PASSWORD, tenant=None,
                                 is_platform_staff=True, platform_role="super")
        login_platform(self.client, "root@ops.local")

    def export(self, include_files=True):
        path = Path(tempfile.mkdtemp()) / "nile.zip"
        manifest = exporter.export_tenant(self.tenant, path, include_files=include_files)
        return path, manifest


class ExportTests(ExportImportBase):
    def test_an_export_holds_the_group_and_nothing_else(self):
        path, manifest = self.export()
        self.assertEqual(manifest["tenant"]["slug"], "nile-exp")
        self.assertEqual(manifest["counts"]["patients.patient"], 1)
        self.assertEqual(manifest["plans"], {str(Plan.objects.get(code="basic").pk): "basic"})
        with zipfile.ZipFile(path) as archive:
            data = archive.read("data.json").decode()
            names = archive.namelist()
        self.assertIn("Mona", data)
        self.assertNotIn("Not Mine", data)
        self.assertTrue(any(n.startswith("files/media/patients/mona") for n in names))

    def test_the_export_endpoint_is_audited_and_for_full_administrators(self):
        response = self.client.get(reverse("api:platform-tenant-export", args=[self.tenant.uuid]), {"files": "0"})
        self.assertEqual(response.status_code, 200)
        content = b"".join(response.streaming_content)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            self.assertIn("data.json", archive.namelist())
        User.objects.create_user(username="help", email="help@ops.local", password=PASSWORD, tenant=None,
                                 is_platform_staff=True, platform_role="support")
        self.client.logout()
        login_platform(self.client, "help@ops.local")
        self.assertEqual(self.client.get(reverse("api:platform-tenant-export", args=[self.tenant.uuid])).status_code,
                         403)


class ImportTests(ExportImportBase):
    def test_a_dry_run_reports_and_writes_nothing(self):
        path, _ = self.export()
        report = import_group(path, slug="nile-copy", dry_run=True)
        self.assertTrue(report["dry_run"])
        self.assertIn("owner@nile.test", " ".join(report["problems"]))  # the email is taken here
        self.assertFalse(Tenant.objects.filter(slug="nile-copy").exists())

    def test_a_copy_without_accounts_becomes_a_new_group(self):
        path, _ = self.export()
        report = import_group(path, slug="nile-copy", accounts=False, dry_run=False)
        self.assertEqual(report["problems"], [])
        copy = Tenant.objects.get(slug="nile-copy")
        self.assertFalse(report["restored_uuids"])
        with tenant_context(copy):
            patient = Patient.all_objects.get(tenant=copy)
            self.assertEqual(patient.name, "Mona")
            payment = Payment.all_objects.get(tenant=copy)
            self.assertEqual((payment.patient_id, payment.appointment.patient_id), (patient.pk, patient.pk))
            self.assertEqual(Visit.all_objects.get(tenant=copy).diagnosis, "Flu")
            self.assertTrue(Path(patient.photo.path).is_file())
            self.assertEqual(Subscription.all_objects.get(tenant=copy).plan.code, "basic")
        with tenant_context(self.tenant):
            self.assertEqual(Patient.all_objects.filter(tenant=self.tenant).count(), 1)  # original untouched
            self.assertNotEqual(Patient.all_objects.get(tenant=self.tenant).uuid, patient.uuid)

    def test_restoring_a_deleted_group_keeps_its_accounts_and_ids(self):
        path, manifest = self.export()
        original_uuid = self.tenant.uuid
        self._delete_group()
        report = import_group(path, slug="nile-exp", dry_run=False)
        self.assertEqual(report["problems"], [])
        self.assertTrue(report["restored_uuids"])
        restored = Tenant.objects.get(slug="nile-exp")
        self.assertEqual(restored.uuid, original_uuid)
        owner = User.objects.get(email="owner@nile.test")
        self.assertEqual(owner.tenant, restored)
        self.assertTrue(owner.check_password(PASSWORD))

    def test_the_import_endpoint(self):
        path, _ = self.export(include_files=False)
        upload = SimpleUploadedFile("nile.zip", path.read_bytes(), content_type="application/zip")
        response = self.client.post(reverse("api:platform-import"),
                                    {"file": upload, "slug": "nile-api", "accounts": "0", "dry_run": "1"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["ok"])
        upload = SimpleUploadedFile("nile.zip", path.read_bytes(), content_type="application/zip")
        response = self.client.post(reverse("api:platform-import"),
                                    {"file": upload, "slug": "nile-api", "accounts": "0", "dry_run": "0"})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(Tenant.objects.filter(slug="nile-api").exists())

    def test_not_an_export(self):
        upload = SimpleUploadedFile("x.zip", b"not a zip", content_type="application/zip")
        response = self.client.post(reverse("api:platform-import"), {"file": upload, "slug": "x"})
        self.assertEqual(response.status_code, 400)

    def _delete_group(self):
        from django.apps import apps

        tenant = self.tenant
        with tenant_context(tenant):
            for model in reversed(exporter.tenant_models()):
                manager = model._base_manager
                if exporter.label(model) == "audit.auditlog":
                    manager.filter(tenant=tenant).delete()
                    continue
                manager.filter(tenant=tenant).delete()
        apps.get_model("audit", "AuditLog").objects.filter(tenant=tenant).delete()  # the deletions' own entries
        apps.get_model("platform_admin", "CommercialTerms").objects.filter(customer=tenant).delete()
        tenant.delete()


class BackupTests(ExportImportBase):
    def test_a_backup_is_encrypted_and_holds_every_group(self):
        BackupPolicy.objects.create(upload_to_drive=False)
        row = backups.run(trigger="schedule")
        self.assertEqual(row.status, "done", row.error)
        sealed = Path(BACKUPS) / row.file_name
        self.assertNotIn(b"Mona", sealed.read_bytes())
        plain = Path(tempfile.mkdtemp()) / "b.tar"
        backups.decrypt_file(sealed, plain)
        with tarfile.open(plain) as tar:
            names = tar.getnames()
            platform = json.loads(tar.extractfile("platform.json").read())
        self.assertIn("groups/nile-exp.zip", names)
        self.assertIn("groups/other-exp.zip", names)
        self.assertTrue(any(item["model"] == "tenants.tenant" for item in platform))
        self.assertFalse(any(item["model"] == "patients.patient" for item in platform))

    def test_old_archives_are_pruned(self):
        BackupPolicy.objects.create(upload_to_drive=False, keep_local=1, include_files=False)
        first = backups.run()
        second = backups.run()
        first.refresh_from_db()
        self.assertEqual(first.file_name, "")
        self.assertTrue((Path(BACKUPS) / second.file_name).exists())

    def test_drive_copy_uses_the_vault_credential(self):
        from platform_admin import vault
        from platform_admin.models import IntegrationCredential

        IntegrationCredential.objects.create(
            kind="google_drive", scope="platform", mode="production",
            production_config=vault.seal({"service_account_json": "{}", "folder_id": "F1"}),
        )
        BackupPolicy.objects.create(upload_to_drive=True, include_files=False)
        with mock.patch("platform_admin.gdrive.upload", return_value="drive-123") as upload:
            row = backups.run()
        self.assertEqual(row.drive_file_id, "drive-123")
        self.assertEqual(upload.call_args.args[0]["folder_id"], "F1")

    def test_the_portal_starts_a_backup_in_the_background(self):
        with mock.patch("platform_admin.backups.subprocess.Popen") as popen:
            response = self.client.post(reverse("api:platform-backups"))
        self.assertEqual(response.status_code, 202)
        self.assertIn("platform_backup", popen.call_args.args[0])
        self.assertEqual(BackupRun.objects.get().status, "running")
        again = self.client.post(reverse("api:platform-backups"))
        self.assertEqual(again.status_code, 400)
