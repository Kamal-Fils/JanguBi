from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task
def populate_tsv_task(book_id: int):
    """
    Creates/updates the tsvector column for a given book.
    """
    from apps.bible.services.index_service import IndexService
    
    try:
        IndexService.populate_tsv_for_book(book_id)
    except Exception as e:
        logger.error(f"Failed to populate TSV for book_id {book_id}: {e}")
        raise


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=600, max_retries=5)
def compute_embeddings_task(self, book_id: int, force: bool = False):
    """
    Computes vector embeddings for a given book's verses.

    force=True recalcule tous les versets (écrase les vecteurs existants, ex. stub).
    """
    from django.conf import settings
    if not getattr(settings, "PGVECTOR_ENABLED", False):
        logger.info(f"Embeddings disabled (PGVECTOR_ENABLED=False), skipping book_id={book_id}")
        return

    from apps.bible.services.embedding_service import EmbeddingService

    try:
        service = EmbeddingService()
        service.compute_bulk_embeddings(book_id, force=force)
    except Exception as e:
        logger.error(f"Failed to compute embeddings for book_id {book_id}: {e}")
        raise


@shared_task
def fetch_aelf_daily():
    """
    Fetches the daily reading from AELF.
    """
    import asyncio
    from apps.bible.services.aelf_service import AELFService
    
    try:
        service = AELFService()
        asyncio.run(service.fetch_daily_readings())
    except Exception as e:
        logger.error(f"Failed to fetch AELF readings: {e}")
        raise


@shared_task
def import_file_task(file_path: str, source: str):
    """
    Background job to import a JSON bible file.
    """
    from apps.bible.services.import_service import ImportService
    
    try:
        service = ImportService()
        service.import_file(file_path, source)
    except Exception as e:
        logger.error(f"Import failed for {file_path}: {str(e)}")
        raise
