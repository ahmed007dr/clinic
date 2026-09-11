"""Backups: an encrypted archive on the server, a copy on Google Drive, and a
cPanel full-account backup on request (the group owner's decision,
2026-09-11: "on cPanel and on Google Drive, both").

What one backup holds (a tar inside the encrypted file):

    platform.json          the platform's own records (exporter.platform_records)
    groups/<slug>.zip      each group's export (exporter.export_tenant)

Encryption is Fernet, chunk by chunk, with the vault key (vault._fernet,
PLATFORM_VAULT_KEY): a backup on Drive or copied off the server is useless
without that key. **Keep the key somewhere other than the backups.**
`manage.py platform_backup_decrypt` turns a backup back into its tar.

Runs from cron (`manage.py platform_backup`) or from the portal, which starts
the same command in the background so a long backup never ties up a web
request.
"""

import hashlib
import json
import os
import struct
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from tenants.models import Tenant

from . import exporter, vault
from .models import BackupPolicy, BackupRun, IntegrationCredential

MAGIC = b"CLINICBK1\n"
CHUNK = 8 * 1024 * 1024


class BackupError(RuntimeError):
    """The message is for the operator."""


def backup_root():
    root = Path(getattr(settings, "PLATFORM_BACKUP_ROOT", "") or Path(settings.BASE_DIR) / "backups")
    root.mkdir(parents=True, exist_ok=True)
    return root


# ------------------------------------------------------------ encryption


def encrypt_file(source, destination):
    """Returns (size, sha256) of the encrypted file."""
    fernet = vault._fernet()
    digest = hashlib.sha256()
    with open(source, "rb") as plain, open(destination, "wb") as out:
        out.write(MAGIC)
        digest.update(MAGIC)
        while True:
            chunk = plain.read(CHUNK)
            if not chunk:
                break
            token = fernet.encrypt(chunk)
            header = struct.pack(">I", len(token))
            out.write(header)
            out.write(token)
            digest.update(header)
            digest.update(token)
    return Path(destination).stat().st_size, digest.hexdigest()


def decrypt_file(source, destination):
    from cryptography.fernet import InvalidToken

    fernet = vault._fernet()
    with open(source, "rb") as sealed, open(destination, "wb") as out:
        if sealed.read(len(MAGIC)) != MAGIC:
            raise BackupError("ليس ملف نسخة احتياطية.")
        while True:
            header = sealed.read(4)
            if not header:
                break
            (length,) = struct.unpack(">I", header)
            try:
                out.write(fernet.decrypt(sealed.read(length)))
            except InvalidToken:
                raise BackupError("مفتاح التشفير لا يطابق هذه النسخة (PLATFORM_VAULT_KEY).")


# ------------------------------------------------------------ running


def build_archive(workdir, include_files=True):
    """Write platform.json and every group's export into `workdir`, then a
    tar of them. Returns (tar path, number of groups)."""
    workdir = Path(workdir)
    exporter.platform_records(workdir / "platform.json")
    (workdir / "groups").mkdir()
    tenants = list(Tenant.objects.order_by("pk"))
    for tenant in tenants:
        exporter.export_tenant(tenant, workdir / "groups" / f"{tenant.slug}.zip", include_files=include_files)
    tar_path = workdir / "backup.tar"
    with tarfile.open(tar_path, "w") as tar:
        tar.add(workdir / "platform.json", arcname="platform.json")
        tar.add(workdir / "groups", arcname="groups")
    return tar_path, len(tenants)


def run(run_row=None, trigger="manual", actor=None):
    """Make one backup. Never raises: the outcome is on the BackupRun."""
    policy = BackupPolicy.current()
    run_row = run_row or BackupRun.objects.create(trigger=trigger, created_by=actor)
    try:
        stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
        name = f"clinic-backup-{stamp}-{run_row.pk}.cbk"
        with tempfile.TemporaryDirectory() as workdir:
            tar_path, groups = build_archive(workdir, include_files=policy.include_files)
            size, sha = encrypt_file(tar_path, backup_root() / name)
        run_row.file_name, run_row.size, run_row.sha256, run_row.groups = name, size, sha, groups
        run_row.status = BackupRun.Status.DONE
        if policy.upload_to_drive:
            _to_drive(run_row, policy)
        run_row.save()
        prune(policy)
        run_row.refresh_from_db(fields=["file_name"])
    except Exception as error:  # noqa: BLE001 — recorded for the operator
        run_row.status = BackupRun.Status.FAILED
        run_row.error = f"{error.__class__.__name__}: {error}"[:2000]
    run_row.finished_at = timezone.now()
    run_row.save()
    return run_row


def _to_drive(run_row, policy):
    from .gdrive import DriveError, delete, upload

    try:
        found = vault.resolve(IntegrationCredential.Kind.GOOGLE_DRIVE)
    except vault.VaultError as error:
        run_row.drive_error = str(error)[:300]
        return
    if found is None:
        run_row.drive_error = "لم تُضبط Google Drive."
        return
    config = found[0]
    try:
        run_row.drive_file_id = upload(config, backup_root() / run_row.file_name, mime="application/octet-stream")
        run_row.drive_error = ""
    except DriveError as error:
        run_row.drive_error = str(error)[:300]
        return
    old = BackupRun.objects.exclude(drive_file_id="").exclude(pk=run_row.pk).order_by("-started_at")
    for stale in old[max(policy.keep_drive - 1, 0):]:
        try:
            delete(config, stale.drive_file_id)
        except DriveError:
            continue
        stale.drive_file_id = ""
        stale.save(update_fields=["drive_file_id"])


def prune(policy):
    """Keep the newest `keep_local` archives on the server."""
    kept = BackupRun.objects.filter(status=BackupRun.Status.DONE).exclude(file_name="").order_by("-started_at")
    for stale in kept[policy.keep_local:]:
        path = backup_root() / stale.file_name
        if path.exists():
            path.unlink()
        stale.file_name = ""
        stale.save(update_fields=["file_name"])


def start_in_background(actor=None):
    """From the portal: record the run and hand it to a separate process."""
    if BackupRun.objects.filter(status=BackupRun.Status.RUNNING,
                                started_at__gte=timezone.now() - timedelta(hours=3)).exists():
        raise BackupError("توجد نسخة احتياطية جارية الآن.")
    row = BackupRun.objects.create(trigger="manual", created_by=actor)
    manage = Path(settings.BASE_DIR) / "manage.py"
    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "cwd": settings.BASE_DIR}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([sys.executable, str(manage), "platform_backup", "--run", str(row.pk)], **kwargs)
    return row


# ------------------------------------------------------------ cPanel


def request_cpanel_backup(email=""):
    """Ask cPanel for a full-account backup into the account's home
    directory (UAPI Backup::fullbackup_to_homedir). cPanel builds it in the
    background and emails `email` when done."""
    from .mailboxes import MailboxError, _cpanel

    try:
        config = _cpanel()
    except MailboxError as error:
        raise BackupError(str(error))
    query = urllib.parse.urlencode({"email": email} if email else {})
    request = urllib.request.Request(
        f"{config['host'].rstrip('/')}/execute/Backup/fullbackup_to_homedir?{query}",
        headers={"Authorization": f"cpanel {config['username']}:{config['api_token']}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as error:
        raise BackupError(f"رفض cPanel الطلب ({error.code}).")
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise BackupError("تعذّر الاتصال بـ cPanel.")
    if not body.get("status"):
        raise BackupError("cPanel: " + "؛ ".join(str(e) for e in (body.get("errors") or ["خطأ غير معروف."])))
    return body.get("data") or {}
