from unittest.mock import AsyncMock, patch

from django.test import TestCase, override_settings

from apps.bible.models import Book, Chapter, Testament, Verse
from apps.bible.tasks import compute_embeddings_task, import_file_task, populate_tsv_task


class TaskTests(TestCase):
    def setUp(self):
        # Create minimal DB structure for tasks
        self.testament = Testament.objects.create(slug="ancien", name="AT", order=1)
        self.book = Book.objects.create(name="Genèse", testament=self.testament, order=1)
        self.chapter = Chapter.objects.create(book=self.book, number=1)
        self.verse = Verse.objects.create(chapter=self.chapter, number=1, text="Dieu créa le ciel et la terre.")

    def test_populate_tsv_task(self):
        # We need to run populate_tsv_task.
        # It executes raw SQL: UPDATE bible_verse SET tsv = to_tsvector(...)
        
        # Ensure it's null initially
        self.verse.refresh_from_db()
        self.assertIsNone(self.verse.tsv)
        
        # Run task synchronously
        populate_tsv_task(self.book.id)
        
        self.verse.refresh_from_db()
        # The exact format depends on PG, but it should be a string/representation of vector
        self.assertIsNotNone(self.verse.tsv)
        self.assertIn("dieu", str(self.verse.tsv).lower())

    # PGVECTOR_ENABLED=True : le garde de compute_embeddings_task court-circuite
    # le calcul quand pgvector est off (cas par défaut). On l'active + stub
    # explicitement ici (la suite tourne sous config.django.base, pas .test).
    @override_settings(EMBEDDING_PROVIDER="stub", PGVECTOR_ENABLED=True)
    def test_compute_embeddings_task_with_stub(self):
        # Run the task synchronously. It should use the stub embedder.
        compute_embeddings_task(self.book.id)
        
        self.verse.refresh_from_db()
        # The stub embedder creates a list of 768 zeros
        self.assertIsNotNone(self.verse.embedding)
        self.assertEqual(len(self.verse.embedding), 768)
        self.assertEqual(self.verse.embedding[0], 0.0)

    @patch("apps.bible.services.import_service.ImportService.import_file")
    def test_import_file_task(self, mock_import):
        # Test that the task calls the service correctly
        import_file_task("/path/to/file.json", "Source")
        mock_import.assert_called_once_with("/path/to/file.json", "Source")

    @patch("apps.bible.services.aelf_service.AELFService.fetch_daily_readings", new_callable=AsyncMock)
    def test_fetch_aelf_daily_task(self, mock_fetch):
        from apps.bible.tasks import fetch_aelf_daily
        fetch_aelf_daily()
        mock_fetch.assert_called_once()

    def test_tasks_module_does_not_call_asyncio_run_directly(self):
        """RÉGRESSION : sous un worker gevent/eventlet une boucle tourne déjà —
        `asyncio.run` lève `RuntimeError: This event loop is already running` et
        le fetch AELF nocturne échoue silencieusement. Utiliser `async_to_sync`.

        Garde au niveau de la SOURCE : `asgiref.async_to_sync` appelle lui-même
        `asyncio.run` dans son propre thread, donc patcher `asyncio.run` ne
        distinguerait pas les deux implémentations.
        """
        import inspect

        from apps.bible import tasks

        source = inspect.getsource(tasks)

        self.assertNotIn("asyncio.run(", source, "utiliser async_to_sync, pas asyncio.run")
        self.assertIn("async_to_sync", source)

    def test_aelf_and_import_tasks_have_bounded_retries(self):
        """Une indisponibilité AELF nocturne doit être retentée, pas perdue."""
        from apps.bible.tasks import fetch_aelf_daily, import_file_task, populate_tsv_task

        for task in (fetch_aelf_daily, import_file_task, populate_tsv_task):
            self.assertIsNotNone(task.max_retries, f"{task.name} sans max_retries")
            self.assertGreater(task.max_retries, 0)
