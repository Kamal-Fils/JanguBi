import logging

from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from apps.bible.models import Book, Verse

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Displays the status of Bible verse vectorization (embeddings)."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Bible Embedding Status Report"))
        self.stdout.write("=" * 40)

        total_verses = Verse.objects.count()

        # On compte les vecteurs RÉELS (non nuls), pas seulement non-NULL : un
        # embedding stub vaut [0,0,...] (non-NULL) et donnerait un faux 100 %.
        # On compare au vecteur nul (l2_norm est ambigu selon la build pgvector).
        from django.db import connection

        from apps.bible.services.embedding_service import EMBEDDING_DIM

        zero_vec = "[" + ",".join(["0"] * EMBEDDING_DIM) + "]"
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM bible_verse "
                "WHERE embedding IS NOT NULL AND embedding <> %s::vector",
                [zero_vec],
            )
            real_count = cursor.fetchone()[0]
        present_count = Verse.objects.filter(embedding__isnull=False).count()

        self.stdout.write(f"Total Verses:   {total_verses}")
        self.stdout.write(f"Real vectors:   {real_count} ({round(real_count/total_verses*100, 2) if total_verses else 0}%)")
        self.stdout.write(f"Present (>=0):   {present_count} (inclut d'éventuels vecteurs nuls/stub)")
        self.stdout.write(f"Missing/zero:   {total_verses - real_count}")
        self.stdout.write("-" * 40)

        # Breakdown by Book
        # Use child relationship path for annotation
        books_qs = Book.objects.annotate(
            total_v=Count('chapters__verses'),
            vectorized_v=Count('chapters__verses', filter=Q(chapters__verses__embedding__isnull=False))
        ).order_by('order')

        self.stdout.write(f"{'Book Name':<25} | {'Status':<15} | {'%':<5}")
        self.stdout.write("-" * 50)

        for book in books_qs:
            percentage = round(book.vectorized_v / book.total_v * 100, 1) if book.total_v else 0
            status_bar = f"{book.vectorized_v}/{book.total_v}"
            
            if book.vectorized_v == book.total_v and book.total_v > 0:
                color = self.style.SUCCESS
            elif book.vectorized_v > 0:
                color = self.style.WARNING
            else:
                color = self.style.NOTICE

            self.stdout.write(color(f"{book.name:<25} | {status_bar:<15} | {percentage:>4}%"))

        self.stdout.write("=" * 40)
        self.stdout.write(self.style.SUCCESS("Note: 'Real vectors' = norme L2 > 0 (vrais embeddings) ; 'Present' inclut les vecteurs nuls (stub)."))
        self.stdout.write(self.style.SUCCESS("Done."))
