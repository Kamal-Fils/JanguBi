"""Cloisonnement de la LISTE back-office des articles.

L'écriture était cloisonnée (autorité de portée sur create/publish/update/
unpublish/delete) mais la liste admin ne l'était pas : tout éditeur voyait
l'intégralité de la plateforme, brouillons et lettres pastorales non publiées
d'autres diocèses compris. On aligne la lecture sur l'autorité d'écriture —
ce qu'on voit est ce sur quoi on peut agir.
"""

import pytest

from apps.news.models import Article
from apps.news.selectors import article_list_for_editor
from apps.org.tests.factories import DioceseFactory, ParishFactory
from apps.users.enums import PastoralRole, RoleScope, UserRole
from apps.users.models import RoleAssignment
from apps.users.tests.factories import BaseUserFactory, SuperAdminFactory

from .factories import ArticleCategoryFactory

pytestmark = pytest.mark.django_db


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


def _article(*, scope_type, parish=None, diocese=None, author=None, status=Article.Status.DRAFT):
    return Article.objects.create(
        title="Article de test",
        slug=f"art-{Article.objects.count()}",
        content="Contenu",
        category=ArticleCategoryFactory(),
        status=status,
        scope_type=scope_type,
        scope_parish=parish,
        scope_diocese=diocese,
        author=author or BaseUserFactory(),
    )


def _visible_ids(editor, **filters):
    return set(
        article_list_for_editor(editor=editor, status="", **filters).values_list(
            "id", flat=True
        )
    )


def test_cure_ne_voit_pas_les_brouillons_d_une_autre_paroisse():
    parish_a, parish_b = ParishFactory(), ParishFactory()
    cure = _cure_of_parish(parish_a)
    sien = _article(scope_type=Article.ScopeType.PARISH, parish=parish_a)
    autre = _article(scope_type=Article.ScopeType.PARISH, parish=parish_b)

    ids = _visible_ids(cure)

    assert sien.id in ids
    assert autre.id not in ids


def test_cure_ne_voit_pas_une_lettre_pastorale_diocesaine():
    diocese = DioceseFactory()
    cure = _cure_of_parish(ParishFactory(diocese=diocese))
    lettre = _article(
        scope_type=Article.ScopeType.DIOCESE,
        diocese=diocese,
        status=Article.Status.DRAFT,
    )

    assert lettre.id not in _visible_ids(cure)


def test_cure_voit_toujours_ses_propres_articles():
    """Même hors de sa portée : on ne cache pas à un auteur ce qu'il a écrit."""
    cure = _cure_of_parish(ParishFactory())
    sien = _article(
        scope_type=Article.ScopeType.PARISH, parish=ParishFactory(), author=cure
    )

    assert sien.id in _visible_ids(cure)


def test_editeur_sans_affectation_ne_voit_que_les_siens():
    """Fail-closed : c'est le cas d'un clergé sans RoleAssignment."""
    orphelin = BaseUserFactory(role=UserRole.FIDELE, pastoral_role=PastoralRole.PRETRE)
    sien = _article(
        scope_type=Article.ScopeType.PARISH, parish=ParishFactory(), author=orphelin
    )
    autre = _article(scope_type=Article.ScopeType.PARISH, parish=ParishFactory())

    ids = _visible_ids(orphelin)

    assert ids == {sien.id}
    assert autre.id not in ids


def test_admin_global_voit_tout():
    superadmin = SuperAdminFactory()
    a = _article(scope_type=Article.ScopeType.PARISH, parish=ParishFactory())
    b = _article(scope_type=Article.ScopeType.GLOBAL)

    ids = _visible_ids(superadmin)

    assert {a.id, b.id} <= ids


def test_cure_ne_voit_pas_les_articles_de_portee_globale():
    """La portée globale suit la même règle qu'à la publication : province+."""
    cure = _cure_of_parish(ParishFactory())
    global_article = _article(scope_type=Article.ScopeType.GLOBAL)

    assert global_article.id not in _visible_ids(cure)


def test_admin_diocesain_voit_les_paroisses_de_son_diocese():
    diocese = DioceseFactory()
    parish = ParishFactory(diocese=diocese)
    admin = BaseUserFactory(role=UserRole.DIOCESE_ADMIN)
    RoleAssignment.objects.create(
        user=admin,
        role=UserRole.DIOCESE_ADMIN,
        scope=RoleScope.DIOCESE,
        diocese=diocese,
        is_active=True,
    )
    interne = _article(scope_type=Article.ScopeType.PARISH, parish=parish)
    externe = _article(scope_type=Article.ScopeType.PARISH, parish=ParishFactory())

    ids = _visible_ids(admin)

    assert interne.id in ids
    assert externe.id not in ids


def test_les_filtres_de_recherche_restent_appliques():
    """Le cloisonnement s'ajoute aux filtres, il ne les remplace pas."""
    parish = ParishFactory()
    cure = _cure_of_parish(parish)
    brouillon = _article(scope_type=Article.ScopeType.PARISH, parish=parish)
    publie = _article(
        scope_type=Article.ScopeType.PARISH,
        parish=parish,
        status=Article.Status.PUBLISHED,
    )

    ids = set(
        article_list_for_editor(
            editor=cure, status=Article.Status.PUBLISHED
        ).values_list("id", flat=True)
    )

    assert publie.id in ids
    assert brouillon.id not in ids
