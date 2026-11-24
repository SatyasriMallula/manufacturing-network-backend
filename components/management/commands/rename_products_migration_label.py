from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction
from django.db.migrations.recorder import MigrationRecorder


class Command(BaseCommand):
    help = "Move existing products migration records to the components app label."

    def add_arguments(self, parser):
        parser.add_argument("--database", default="default")

    def handle(self, *args, **options):
        database = options["database"]
        connection = connections[database]
        recorder = MigrationRecorder(connection)
        if not recorder.has_table():
            self.stdout.write("No migration records exist yet; nothing to relabel.")
            return

        migrations = recorder.migration_qs.using(database)
        old_names = set(migrations.filter(app="products").values_list("name", flat=True))
        existing_names = set(migrations.filter(app="components").values_list("name", flat=True))
        conflicts = old_names & existing_names
        if conflicts:
            raise CommandError(
                "Both products and components migration records exist for: "
                + ", ".join(sorted(conflicts))
            )
        if not old_names:
            self.stdout.write("No products migration records need relabeling.")
            return

        with transaction.atomic(using=database):
            updated = migrations.filter(app="products").update(app="components")
        self.stdout.write(
            self.style.SUCCESS(f"Relabeled {updated} migration records from products to components.")
        )
