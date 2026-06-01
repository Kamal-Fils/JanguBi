"""
Chantier 3b — correction de l'autorité CHURCH côté Article (RG-CONT) :
un church_admin scopé sur X PEUT publier un article scope église sur X
(le 3a exigeait à tort l'autorité paroisse), mais PAS sur une autre église.
"""

import pytest

from apps.core.exceptions import ApplicationError
from apps.news.models import Article
from apps.news.services import article_create
from apps.org.tests.factories import ChurchFactory
from apps.users.enums import RoleScope, UserRole
from apps.users.models import RoleAssignment
from apps.users.tests.factories import BaseUserFactory

from .factories import ArticleCategoryFactory


def _church_admin(church):
    user = BaseUserFactory(role=UserRole.CHURCH_ADMIN)
    RoleAssignment.objects.create(
        user=user, role=UserRole.CHURCH_ADMIN, scope=RoleScope.CHURCH,
        church=church, is_active=True,
    )
    return user


@pytest.mark.django_db
def test_church_admin_can_publish_church_scoped_to_own_church_article():
    church = ChurchFactory()
    admin = _church_admin(church)
    cat = ArticleCategoryFactory()

    article = article_create(
        author=admin,
        title="Annonce église",
        content="Contenu.",
        category_id=cat.id,
        scope_type=Article.ScopeType.CHURCH,
        scope_church_id=church.id,
    )

    assert article.scope_church_id == church.id


@pytest.mark.django_db
def test_church_admin_cannot_publish_church_scoped_to_other_church_article():
    church_x = ChurchFactory()
    church_y = ChurchFactory()
    admin = _church_admin(church_x)
    cat = ArticleCategoryFactory()

    with pytest.raises(ApplicationError):
        article_create(
            author=admin,
            title="Injection",
            content="Contenu.",
            category_id=cat.id,
            scope_type=Article.ScopeType.CHURCH,
            scope_church_id=church_y.id,
        )
