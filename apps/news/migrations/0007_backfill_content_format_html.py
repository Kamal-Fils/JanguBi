import re

import nh3
from django.db import migrations

# Balises usuelles produites par l'injection legacy / les éditeurs riches.
_HTML_TAG_RE = re.compile(
    r"<(p|h[1-6]|div|br|ul|ol|li|strong|em|b|i|a|img|blockquote|span|table|figure)"
    r"[\s/>]",
    re.IGNORECASE,
)


def backfill_html_articles(apps, schema_editor):
    """Les articles legacy injectés en HTML ont reçu content_format='text'
    (défaut de la migration 0006) : le détail les affichait balises visibles.
    On les bascule en 'html' après sanitization nh3 (même garantie que
    services._clean_content : aucun HTML non filtré en base)."""
    Article = apps.get_model("news", "Article")
    to_fix = []
    for article in Article.objects.filter(content_format="text").iterator():
        if article.content and _HTML_TAG_RE.search(article.content):
            article.content = nh3.clean(article.content)
            article.content_format = "html"
            to_fix.append(article)
    if to_fix:
        Article.objects.bulk_update(to_fix, ["content", "content_format"], batch_size=200)


class Migration(migrations.Migration):
    dependencies = [
        ("news", "0006_article_announcement_date_article_content_format"),
    ]

    operations = [
        # Irréversible sans perte (le contenu est sanitizé sur place) :
        # le reverse est un no-op assumé.
        migrations.RunPython(backfill_html_articles, migrations.RunPython.noop),
    ]
