"""Turn an encrypted platform backup (.cbk) back into its tar, with the
vault key of the installation that made it (PLATFORM_VAULT_KEY):

    manage.py platform_backup_decrypt clinic-backup-20260911-023000.cbk backup.tar
"""

from django.core.management.base import BaseCommand, CommandError

from platform_admin.backups import BackupError, decrypt_file


class Command(BaseCommand):
    help = "Decrypt a platform backup into a tar archive."

    def add_arguments(self, parser):
        parser.add_argument("source")
        parser.add_argument("destination")

    def handle(self, *args, **options):
        try:
            decrypt_file(options["source"], options["destination"])
        except BackupError as error:
            raise CommandError(str(error))
        self.stdout.write(self.style.SUCCESS(f"Wrote {options['destination']}"))
