"""Tests de la data migration 0007 — bascule des articles legacy HTML.

On teste la fonction de backfill directement contre le registre d'apps réel :
même logique que la migration, sans rejouer tout l'historique de migrations.
"""

from importlib import import_module

import pytest
from django.apps import apps as django_apps

from .factories import ArticleFactory

_migration = import_module("apps.news.migrations.0007_backfill_content_format_html")


def _run_backfill():
    _migration.backfill_html_articles(django_apps, None)


@pytest.mark.django_db
def test_backfill_switches_html_looking_text_articles():
    # Arrange
    legacy = ArticleFactory(
        content="<p>Bonne <strong>nouvelle</strong></p><script>alert(1)</script>",
        content_format="text",
    )
    plain = ArticleFactory(
        content="Un simple texte sans balises.",
        content_format="text",
    )

    # Act
    _run_backfill()

    # Assert
    legacy.refresh_from_db()
    plain.refresh_from_db()
    assert legacy.content_format == "html"
    assert "<script>" not in legacy.content  # sanitizé par nh3
    assert "<strong>" in legacy.content
    assert plain.content_format == "text"
    assert plain.content == "Un simple texte sans balises."


@pytest.mark.django_db
def test_backfill_leaves_html_articles_untouched():
    # Arrange
    already = ArticleFactory(content="<p>Déjà riche</p>", content_format="html")

    # Act
    _run_backfill()

    # Assert
    already.refresh_from_db()
    assert already.content == "<p>Déjà riche</p>"
    assert already.content_format == "html"
