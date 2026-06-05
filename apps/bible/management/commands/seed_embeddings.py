import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.bible.models import Book
from apps.bible.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Génère les embeddings vectoriels des versets (recherche sémantique). "
        "Synchrone par défaut ; --async pour dispatcher via Celery."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Recalcule TOUS les embeddings (écrase l'existant, ex. vecteurs stub/zéro).",
        )
        parser.add_argument(
            "--async",
            dest="async_",
            action="store_true",
            help="Dispatche les tâches via Celery (arrière-plan) au lieu d'exécuter en synchrone.",
        )
        parser.add_argument(
            "--book",
            type=int,
            default=None,
            help="Limiter à un seul book_id (par défaut : tous les livres).",
        )

    def handle(self, *args, **opts):
        provider = getattr(settings, "EMBEDDING_PROVIDER", "stub")
        if provider == "stub":
            self.stdout.write(self.style.WARNING(
                "EMBEDDING_PROVIDER=stub : des vecteurs ZÉRO seront écrits (pas de vraie "
                "recherche sémantique). Mettez EMBEDDING_PROVIDER=local dans .env puis "
                "redémarrez les conteneurs (django + celery) pour charger la nouvelle config."
            ))
        if not getattr(settings, "PGVECTOR_ENABLED", False):
            self.stdout.write(self.style.WARNING(
                "PGVECTOR_ENABLED=False : la recherche vectorielle reste désactivée à la "
                "requête (les embeddings seront calculés mais non utilisés tant que ce flag "
                "n'est pas True). En mode --async, la tâche Celery est même court-circuitée."
            ))

        if opts["book"] is not None:
            books = list(Book.objects.filter(id=opts["book"]))
            if not books:
                raise CommandError(f"Book id={opts['book']} introuvable.")
        else:
            books = list(Book.objects.all().order_by("order"))

        force = opts["force"]
        self.stdout.write(f"Embeddings : {len(books)} livre(s), force={force}, mode={'async' if opts['async_'] else 'sync'}")

        if opts["async_"]:
            from apps.bible.tasks import compute_embeddings_task

            for book in books:
                compute_embeddings_task.delay(book.id, force=force)
            self.stdout.write(self.style.SUCCESS(
                f"{len(books)} tâche(s) d'embedding dispatchée(s) via Celery."
            ))
            return

        # Synchrone : charge le modèle local une fois (~1 Go au 1er usage).
        service = EmbeddingService()
        total = 0
        for book in books:
            count = service.compute_bulk_embeddings(book.id, force=force)
            total += count
            self.stdout.write(f"  {book.name:<28} : {count} versets embeddés")

        self.stdout.write(self.style.SUCCESS(f"Terminé : {total} versets embeddés (force={force})."))
