from django.core.management.base import BaseCommand

from apps.tv.services import category_ensure_defaults


class Command(BaseCommand):
    help = "Initialize default TV categories."

    def handle(self, *args, **options):
        created_count = category_ensure_defaults()
        self.stdout.write(self.style.SUCCESS(f"TV categories initialized. Newly created: {created_count}"))
