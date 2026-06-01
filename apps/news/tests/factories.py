import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.news.models import Article, ArticleCategory
from apps.org.tests.factories import ChurchFactory, DioceseFactory, ParishFactory
from apps.users.tests.factories import BaseUserFactory, StaffUserFactory


class ArticleCategoryFactory(DjangoModelFactory):
    class Meta:
        model = ArticleCategory

    name = factory.Sequence(lambda n: f"Catégorie {n}")
    slug = factory.Sequence(lambda n: f"categorie-{n}")
    icon = ""
    color = ""
    display_order = factory.Sequence(lambda n: n)
    is_active = True


class ArticleFactory(DjangoModelFactory):
    """Article en brouillon, portée globale."""

    class Meta:
        model = Article

    title = factory.Sequence(lambda n: f"Article test {n}")
    slug = factory.Sequence(lambda n: f"article-test-{n}-global")
    excerpt = factory.Sequence(lambda n: f"Résumé de l'article {n}")
    content = factory.Sequence(lambda n: f"Contenu complet de l'article numéro {n}.")
    category = factory.SubFactory(ArticleCategoryFactory)
    author = factory.SubFactory(StaffUserFactory)
    scope_type = Article.ScopeType.GLOBAL
    # scope_diocese / scope_parish / scope_church : null par défaut (portée globale)
    status = Article.Status.DRAFT
    published_at = None
    views_count = 0


class PublishedArticleFactory(ArticleFactory):
    """Article global publié."""

    status = Article.Status.PUBLISHED
    published_at = factory.LazyFunction(timezone.now)


class ParishArticleFactory(ArticleFactory):
    """Article de portée paroisse, en brouillon (FK réelle)."""

    scope_type = Article.ScopeType.PARISH
    scope_parish = factory.SubFactory(ParishFactory)
    slug = factory.Sequence(lambda n: f"article-paroisse-{n}")


class PublishedParishArticleFactory(ParishArticleFactory):
    """Article de paroisse publié."""

    status = Article.Status.PUBLISHED
    published_at = factory.LazyFunction(timezone.now)


class DioceseArticleFactory(ArticleFactory):
    """Article de portée diocèse, en brouillon (FK réelle)."""

    scope_type = Article.ScopeType.DIOCESE
    scope_diocese = factory.SubFactory(DioceseFactory)
    slug = factory.Sequence(lambda n: f"article-diocese-{n}")


class PublishedDioceseArticleFactory(DioceseArticleFactory):
    """Article de diocèse publié."""

    status = Article.Status.PUBLISHED
    published_at = factory.LazyFunction(timezone.now)


class ChurchArticleFactory(ArticleFactory):
    """Article de portée église, en brouillon (FK réelle — Chantier 3a)."""

    scope_type = Article.ScopeType.CHURCH
    scope_church = factory.SubFactory(ChurchFactory)
    slug = factory.Sequence(lambda n: f"article-eglise-{n}")


class PublishedChurchArticleFactory(ChurchArticleFactory):
    """Article d'église publié."""

    status = Article.Status.PUBLISHED
    published_at = factory.LazyFunction(timezone.now)
