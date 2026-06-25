"""Tests services apps/spiritual — reflection_upsert / reflection_delete."""

from datetime import date

import pytest

from apps.core.exceptions import ApplicationError
from apps.org.tests.factories import ParishFactory
from apps.spiritual.models import PastoralReflection
from apps.spiritual.services import reflection_delete, reflection_upsert
from apps.users.enums import PastoralRole, RoleScope, UserRole
from apps.users.models import RoleAssignment
from apps.users.tests.factories import BaseUserFactory

D = date(2026, 6, 5)


def _parish_priest(parish):
    """Prêtre avec autorité territoriale réelle (RoleAssignment) sur la paroisse."""
    user = BaseUserFactory(pastoral_role=PastoralRole.PRETRE)
    RoleAssignment.objects.create(
        user=user, role=UserRole.PARISH_ADMIN, scope=RoleScope.PARISH,
        parish=parish, is_active=True,
    )
    return user


@pytest.mark.django_db
def test_upsert_success_for_parish_priest():
    parish = ParishFactory()
    author = _parish_priest(parish)

    reflection = reflection_upsert(
        author=author, content="Méditez l'Évangile du jour.", reflection_date=D,
        scope_type="parish", scope_parish_id=parish.id,
    )

    assert reflection.id is not None
    assert reflection.scope_parish_id == parish.id
    assert reflection.content == "Méditez l'Évangile du jour."


@pytest.mark.django_db
def test_upsert_forbidden_for_fidele():
    parish = ParishFactory()
    fidele = BaseUserFactory()  # pas clergé, pas admin

    with pytest.raises(ApplicationError):
        reflection_upsert(
            author=fidele, content="x", reflection_date=D,
            scope_type="parish", scope_parish_id=parish.id,
        )


@pytest.mark.django_db
def test_upsert_rejects_other_parish_authority():
    parish_a = ParishFactory()
    parish_b = ParishFactory()
    author = _parish_priest(parish_a)  # autorité sur A uniquement

    with pytest.raises(ApplicationError):
        reflection_upsert(
            author=author, content="x", reflection_date=D,
            scope_type="parish", scope_parish_id=parish_b.id,
        )


@pytest.mark.django_db
def test_upsert_is_idempotent_per_author_and_day():
    parish = ParishFactory()
    author = _parish_priest(parish)

    reflection_upsert(author=author, content="v1", reflection_date=D,
                      scope_type="parish", scope_parish_id=parish.id)
    r2 = reflection_upsert(author=author, content="v2", reflection_date=D,
                           scope_type="parish", scope_parish_id=parish.id)

    assert PastoralReflection.objects.filter(author=author, reflection_date=D).count() == 1
    assert r2.content == "v2"


@pytest.mark.django_db
def test_upsert_requires_scope_id_consistency():
    parish = ParishFactory()
    author = _parish_priest(parish)

    with pytest.raises(ApplicationError):
        reflection_upsert(author=author, content="x", reflection_date=D,
                          scope_type="parish", scope_parish_id=None)


@pytest.mark.django_db
def test_delete_only_by_author_or_admin():
    parish = ParishFactory()
    author = _parish_priest(parish)
    reflection = reflection_upsert(author=author, content="v1", reflection_date=D,
                                   scope_type="parish", scope_parish_id=parish.id)
    other = BaseUserFactory()

    with pytest.raises(ApplicationError):
        reflection_delete(reflection=reflection, editor=other)

    reflection_delete(reflection=reflection, editor=author)
    assert not PastoralReflection.objects.filter(pk=reflection.pk).exists()
