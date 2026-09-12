"""Make a platform backup (platform_admin/backups.py).

Daily from cron, e.g.:

    30 2 * * *  cd ~/app && venv/bin/python manage.py platform_backup >> ~/logs/backup.log 2>&1

`--run <id>` finishes a run the portal has already recorded (the portal's
"backup now" starts this command in the background).
"""

from django.core.management.base import BaseCommand, CommandError

from platform_admin import backups
from platform_admin.models import BackupRun


class Command(BaseCommand):
    help = "Make an encrypted backup of the platform and every group, and copy it to Google Drive."

    def add_arguments(self, parser):
        parser.add_argument("--run", type=int, help="An existing BackupRun id to carry out.")

    def handle(self, *args, **options):
        row = None
        if options.get("run"):
            row = BackupRun.objects.filter(pk=options["run"], status=BackupRun.Status.RUNNING).first()
            if row is None:
                raise CommandError("No such running backup.")
        row = backups.run(row, trigger="schedule" if row is None else row.trigger)
        if row.status != BackupRun.Status.DONE:
            raise CommandError(f"Backup failed: {row.error}")
        self.stdout.write(self.style.SUCCESS(
            f"{row.file_name} {row.size} bytes, {row.groups} groups"
            + (f", Drive {row.drive_file_id}" if row.drive_file_id else "")
            + (f" (Drive: {row.drive_error})" if row.drive_error else "")
        ))
