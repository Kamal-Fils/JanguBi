"""
Chantier 3a (côté news) — scope ÉGLISE + FK réelles + feed multi-appartenance.

Couvre la visibilité par appartenance (église/paroisse/diocèse/global), l'agrégation
du feed sur toutes les appartenances, la création scope église/paroisse (résolution
INT→FK), et la résolution/flag de la migration data.
"""

import pytest

from apps.news.migration_ops import resolve_scope_fk
from apps.news.models import Article
from apps.news.selectors import article_list_for_user
from apps.news.services import article_create
from apps.org.models import Diocese, Parish
from apps.org.tests.factories import ChurchFactory, DioceseFactory, ParishFactory
from apps.users.enums import PastoralRole, RoleScope, UserRole
from apps.users.models import RoleAssignment
from apps.users.services_memberships import membership_create
from apps.users.tests.factories import BaseUserFactory

from .factories import (
    ArticleCategoryFactory,
    PublishedArticleFactory,
    PublishedChurchArticleFactory,
    PublishedDioceseArticleFactory,
    PublishedParishArticleFactory,
)


def _member_of_church(church):
    user = BaseUserFactory()
    membership_create(user=user, church=church, is_primary=True)
    return user


def _cure_of_parish(parish):
    user = BaseUserFactory(role=UserRole.FIDELE, pastoral_role=PastoralRole.PRETRE)
    RoleAssignment.objects.create(
        user=user,
        role=UserRole.PARISH_ADMIN,
        scope=RoleScope.PARISH,
        parish=parish,
        is_active=True,
    )
    return user


def _feed_ids(user):
    return set(article_list_for_user(user=user).values_list("id", flat=True))


# ---------------------------------------------------------------------------
# Visibilité scope ÉGLISE
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_article_church_scope_visible_to_church_members_only():
    church = ChurchFactory()
    other_church = ChurchFactory()
    art_church = PublishedChurchArticleFactory(scope_church=church)
    art_global = PublishedArticleFactory()

    member = _member_of_church(church)
    outsider = _member_of_church(other_church)

    member_feed = _feed_ids(member)
    assert art_church.id in member_feed
    assert art_global.id in member_feed  # global visible à tous

    outsider_feed = _feed_ids(outsider)
    assert art_church.id not in outsider_feed  # pas membre de cette église
    assert art_global.id in outsider_feed


@pytest.mark.django_db
def test_feed_aggregates_all_memberships():
    # Membre de 2 paroisses (A/B) dans 2 diocèses (D1/D2) via 2 églises.
    church_a = ChurchFactory()
    church_b = ChurchFactory()
    parish_a, parish_b = church_a.parish, church_b.parish
    d1, d2 = parish_a.diocese, parish_b.diocese

    user = BaseUserFactory()
    membership_create(user=user, church=church_a, is_primary=True)
    membership_create(user=user, church=church_b)

    visible = [
        PublishedChurchArticleFactory(scope_church=church_a),
        PublishedParishArticleFactory(scope_parish=parish_a),
        PublishedDioceseArticleFactory(scope_diocese=d1),
        PublishedChurchArticleFactory(scope_church=church_b),
        PublishedParishArticleFactory(scope_parish=parish_b),
        PublishedDioceseArticleFactory(scope_diocese=d2),
        PublishedArticleFactory(),  # global
    ]
    # Une paroisse C NON suivie → invisible.
    hidden = PublishedParishArticleFactory(scope_parish=ParishFactory())

    feed = _feed_ids(user)
    assert {a.id for a in visible} <= feed
    assert hidden.id not in feed


@pytest.mark.django_db
def test_non_regression_global_diocese_parish_visibility():
    # NON-RÉGRESSION : un membre d'une paroisse voit global + son diocèse + sa paroisse.
    church = ChurchFactory()
    parish, diocese = church.parish, church.parish.diocese
    user = _member_of_church(church)

    g = PublishedArticleFactory()
    d = PublishedDioceseArticleFactory(scope_diocese=diocese)
    p = PublishedParishArticleFactory(scope_parish=parish)
    other = PublishedDioceseArticleFactory(scope_diocese=DioceseFactory())

    feed = _feed_ids(user)
    assert {g.id, d.id, p.id} <= feed
    assert other.id not in feed


# ---------------------------------------------------------------------------
# Création scope église / paroisse (résolution INT→FK)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_article_create_with_church_scope():
    parish = ParishFactory()
    church = ChurchFactory(parish=parish)
    cure = _cure_of_parish(parish)
    cat = ArticleCategoryFactory()

    article = article_create(
        author=cure,
        title="Annonce église",
        content="Contenu.",
        category_id=cat.id,
        scope_type=Article.ScopeType.CHURCH,
        scope_church_id=church.id,
    )

    assert article.scope_type == Article.ScopeType.CHURCH
    assert article.scope_church_id == church.id
    assert article.scope_parish_id is None
    assert article.scope_diocese_id is None


@pytest.mark.django_db
def test_article_create_parish_scope_resolves_to_fk():
    parish = ParishFactory()
    cure = _cure_of_parish(parish)
    cat = ArticleCategoryFactory()

    article = article_create(
        author=cure,
        title="Annonce paroisse",
        content="Contenu.",
        category_id=cat.id,
        scope_type=Article.ScopeType.PARISH,
        scope_parish_id=parish.id,
    )

    # L'INT reçu a été résolu en FK réelle.
    assert article.scope_parish_id == parish.id
    assert article.scope_parish == parish


@pytest.mark.django_db
def test_article_create_church_scope_other_parish_forbidden():
    # Un curé de A ne peut pas créer un article scope église d'une église de B.
    parish_a = ParishFactory()
    church_b = ChurchFactory(parish=ParishFactory())
    cure_a = _cure_of_parish(parish_a)
    cat = ArticleCategoryFactory()

    from apps.core.exceptions import ApplicationError

    with pytest.raises(ApplicationError):
        article_create(
            author=cure_a,
            title="Injection",
            content="Contenu.",
            category_id=cat.id,
            scope_type=Article.ScopeType.CHURCH,
            scope_church_id=church_b.id,
        )


# ---------------------------------------------------------------------------
# Migration data — résolution / flag
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_migration_resolves_scope_ids_to_fk():
    parish = ParishFactory()
    diocese = DioceseFactory()
    assert resolve_scope_fk(value=parish.id, Model=Parish) == (parish.id, False)
    assert resolve_scope_fk(value=diocese.id, Model=Diocese) == (diocese.id, False)


@pytest.mark.django_db
def test_migration_flags_unresolvable_scope_ids():
    # id introuvable → flagué (None, True), JAMAIS d'exception ; None → rien à résoudre.
    assert resolve_scope_fk(value=999999, Model=Parish) == (None, True)
    assert resolve_scope_fk(value=None, Model=Parish) == (None, False)
