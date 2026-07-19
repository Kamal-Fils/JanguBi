"""
Chantier 3a (côté news) — scope ÉGLISE + FK réelles + feed multi-appartenance.

Couvre la visibilité par appartenance (église/paroisse/diocèse/global), l'agrégation
du feed sur toutes les appartenances, la création scope église/paroisse (résolution
INT→FK), et la résolution/flag de la migration data.
"""

import inspect

import pytest

from apps.core.exceptions import ApplicationError
from apps.news.migration_ops import resolve_scope_fk
from apps.news.models import Article
from apps.news.selectors import article_list_for_user
from apps.news.services import (
    article_create,
    article_delete,
    article_unpublish,
    article_update,
)
from apps.org.models import Diocese, Parish
from apps.org.tests.factories import ChurchFactory, DioceseFactory, ParishFactory
from apps.users.enums import PastoralRole, RoleScope, UserRole
from apps.users.models import RoleAssignment
from apps.users.services_memberships import membership_create
from apps.users.tests.factories import BaseUserFactory, SuperAdminFactory

from .factories import (
    ArticleCategoryFactory,
    ParishArticleFactory,
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


# ---------------------------------------------------------------------------
# Autorité de portée sur un article DÉJÀ persisté — update / unpublish / delete
#
# Régression sécurité : ces trois services ne faisaient que `_check_editor`
# (« est un éditeur quelconque »), sans vérifier l'autorité territoriale. Un curé
# de la paroisse A pouvait donc réécrire, dépublier ou supprimer le contenu de la
# paroisse B, d'un diocèse, ou de la portée globale.
# ---------------------------------------------------------------------------


def _eveque_of_diocese(diocese):
    user = BaseUserFactory(role=UserRole.FIDELE, pastoral_role=PastoralRole.EVEQUE)
    RoleAssignment.objects.create(
        user=user,
        role=UserRole.DIOCESE_ADMIN,
        scope=RoleScope.DIOCESE,
        diocese=diocese,
        is_active=True,
    )
    return user


@pytest.mark.django_db
def test_cure_cannot_update_article_of_other_parish():
    cure_a = _cure_of_parish(ParishFactory())
    article_b = ParishArticleFactory(scope_parish=ParishFactory())

    with pytest.raises(ApplicationError, match="autorité"):
        article_update(article=article_b, editor=cure_a, title="Détournement")

    article_b.refresh_from_db()
    assert article_b.title != "Détournement"


@pytest.mark.django_db
def test_cure_cannot_unpublish_article_of_other_parish():
    cure_a = _cure_of_parish(ParishFactory())
    article_b = PublishedParishArticleFactory(scope_parish=ParishFactory())

    with pytest.raises(ApplicationError, match="autorité"):
        article_unpublish(article=article_b, editor=cure_a, reason="Censure")

    article_b.refresh_from_db()
    assert article_b.status == Article.Status.PUBLISHED


@pytest.mark.django_db
def test_cure_cannot_delete_article_of_other_parish():
    cure_a = _cure_of_parish(ParishFactory())
    article_b = ParishArticleFactory(scope_parish=ParishFactory())

    with pytest.raises(ApplicationError, match="autorité"):
        article_delete(article=article_b, editor=cure_a)

    assert Article.objects.filter(pk=article_b.pk).exists()


@pytest.mark.django_db
def test_cure_cannot_unpublish_diocese_scoped_article():
    # Escalade verticale : le curé n'a pas autorité sur le diocèse au-dessus de lui.
    parish = ParishFactory()
    cure = _cure_of_parish(parish)
    article = PublishedDioceseArticleFactory(scope_diocese=parish.diocese)

    with pytest.raises(ApplicationError, match="autorité"):
        article_unpublish(article=article, editor=cure)


@pytest.mark.django_db
def test_cure_can_update_unpublish_and_delete_own_parish_article():
    # Contrôle positif : sur SA paroisse, le curé garde la main de bout en bout.
    parish = ParishFactory()
    cure = _cure_of_parish(parish)

    draft = ParishArticleFactory(scope_parish=parish)
    assert article_update(article=draft, editor=cure, title="Titre revu").title == "Titre revu"

    published = PublishedParishArticleFactory(scope_parish=parish)
    assert (
        article_unpublish(article=published, editor=cure).status == Article.Status.UNPUBLISHED
    )

    article_delete(article=draft, editor=cure)
    assert not Article.objects.filter(pk=draft.pk).exists()


@pytest.mark.django_db
def test_global_admin_can_update_and_delete_any_parish_article():
    admin = SuperAdminFactory()
    article = ParishArticleFactory(scope_parish=ParishFactory())

    assert article_update(article=article, editor=admin, title="Modéré").title == "Modéré"

    article_delete(article=article, editor=admin)
    assert not Article.objects.filter(pk=article.pk).exists()


# --- Lettres pastorales : acte d'évêque, y compris pour retirer/réécrire -----


@pytest.mark.django_db
def test_cure_cannot_update_parish_scoped_pastoral_letter():
    # Le curé a bien autorité sur la paroisse, mais une lettre pastorale reste
    # réservée à l'évêque — sinon il réécrit la parole de son évêque chez lui.
    parish = ParishFactory()
    cure = _cure_of_parish(parish)
    letter = ParishArticleFactory(
        scope_parish=parish, content_type=Article.ContentType.PASTORAL_LETTER
    )

    with pytest.raises(ApplicationError, match="lettre pastorale"):
        article_update(article=letter, editor=cure, title="Réécriture")


@pytest.mark.django_db
def test_cure_cannot_unpublish_parish_scoped_pastoral_letter():
    parish = ParishFactory()
    cure = _cure_of_parish(parish)
    letter = PublishedParishArticleFactory(
        scope_parish=parish, content_type=Article.ContentType.PASTORAL_LETTER
    )

    with pytest.raises(ApplicationError, match="lettre pastorale"):
        article_unpublish(article=letter, editor=cure)

    letter.refresh_from_db()
    assert letter.status == Article.Status.PUBLISHED


@pytest.mark.django_db
def test_eveque_can_update_own_diocese_pastoral_letter():
    diocese = DioceseFactory()
    eveque = _eveque_of_diocese(diocese)
    letter = PublishedDioceseArticleFactory(
        scope_diocese=diocese, content_type=Article.ContentType.PASTORAL_LETTER
    )

    updated = article_update(article=letter, editor=eveque, title="Lettre révisée")

    assert updated.title == "Lettre révisée"


# --- Invariant : la portée n'est PAS modifiable via article_update -----------


def test_article_update_ne_permet_pas_de_changer_la_portee():
    """Garde-fou de conception (cf. `_check_article_authority`).

    `_check_article_authority` ne vérifie QUE la portée courante de l'article.
    C'est suffisant tant que la portée est immuable après création. Si un jour
    un paramètre de portée apparaît ici, ce test casse et impose de vérifier
    l'autorité sur l'ANCIENNE **et** la NOUVELLE portée.
    """
    params = set(inspect.signature(article_update).parameters)
    scope_params = {p for p in params if p.startswith("scope")}
    assert scope_params == set(), (
        f"article_update expose désormais {scope_params} : la portée devient modifiable. "
        "Il faut vérifier l'autorité sur l'ancienne ET la nouvelle portée."
    )


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
