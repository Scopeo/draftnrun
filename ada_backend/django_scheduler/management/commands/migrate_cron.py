from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import connection
import sys


class Command(BaseCommand):
    help = "Manage cron database migrations with version tracking"

    def add_arguments(self, parser):
        parser.add_argument(
            "action", choices=["upgrade", "downgrade", "status", "makemigrations", "current"], help="Action to perform"
        )
        parser.add_argument(
            "--target",
            help="Target migration (for downgrade)",
        )

    def handle(self, *args, **options):
        action = options["action"]
        target = options.get("target")

        if action == "upgrade":
            self.upgrade()
        elif action == "downgrade":
            self.downgrade(target)
        elif action == "status":
            self.status()
        elif action == "makemigrations":
            self.makemigrations()
        elif action == "current":
            self.current()

    def upgrade(self):
        """Apply all pending migrations"""
        self.stdout.write("Applying cron database migrations...")
        try:
            call_command("migrate", verbosity=1)
            self.stdout.write(self.style.SUCCESS("✓ Migrations applied successfully"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Migration failed: {e}"))
            sys.exit(1)

    def downgrade(self, target=None):
        """Revert to a specific migration or the previous one"""
        if target:
            self.stdout.write(f"Reverting to migration: {target}")
            try:
                call_command("migrate", "django_scheduler", target, verbosity=1)
                self.stdout.write(self.style.SUCCESS(f"✓ Reverted to {target}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"✗ Downgrade failed: {e}"))
                sys.exit(1)
        else:
            # Get current migration and revert to previous
            current = self.get_current_migration()
            if current == "0001":
                self.stdout.write(self.style.WARNING("Already at initial migration"))
                return

            # Find previous migration
            previous = self.get_previous_migration(current)
            if previous:
                self.stdout.write(f"Reverting from {current} to {previous}")
                try:
                    call_command("migrate", "django_scheduler", previous, verbosity=1)
                    self.stdout.write(self.style.SUCCESS(f"✓ Reverted to {previous}"))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"✗ Downgrade failed: {e}"))
                    sys.exit(1)
            else:
                self.stdout.write(self.style.ERROR("No previous migration found"))

    def status(self):
        """Show migration status"""
        self.stdout.write("Cron database migration status:")
        try:
            call_command("showmigrations", "django_scheduler", verbosity=1)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Status check failed: {e}"))

    def current(self):
        """Show current migration version"""
        current = self.get_current_migration()
        self.stdout.write(f"Current migration: {current}")

    def makemigrations(self):
        """Create new migrations"""
        self.stdout.write("Creating new cron database migrations...")
        try:
            call_command("makemigrations", "django_scheduler", verbosity=1)
            self.stdout.write(self.style.SUCCESS("✓ Migration files created"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Migration creation failed: {e}"))
            sys.exit(1)

    def get_current_migration(self):
        """Get the current migration version"""
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT name FROM django_migrations
                WHERE app = 'django_scheduler'
                ORDER BY applied DESC
                LIMIT 1
            """
            )
            result = cursor.fetchone()
            return result[0] if result else "0001"

    def get_previous_migration(self, current):
        """Get the previous migration version"""
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT name FROM django_migrations
                WHERE app = 'django_scheduler'
                AND name < %s
                ORDER BY name DESC
                LIMIT 1
            """,
                [current],
            )
            result = cursor.fetchone()
            return result[0] if result else None
