import pytest
from unittest.mock import patch, AsyncMock

from django.test import TestCase, override_settings

import apps.bible.services.aelf_service

from apps.bible.models import Book, Chapter, Testament, Verse
from apps.bible.tasks import compute_embeddings_task, populate_tsv_task, import_file_task


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

    @override_settings(EMBEDDING_PROVIDER="stub")
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
