"""Tests services apps/spiritual — reflection_upsert / reflection_delete."""

from datetime import date

import pytest

from apps.core.exceptions import ApplicationError
from apps.org.tests.factories import ChurchFactory, DioceseFactory, ParishFactory
from apps.spiritual.models import PastoralReflection
from apps.spiritual.services import reflection_delete, reflection_upsert
from apps.users.enums import PastoralRole, RoleScope, UserRole
from apps.users.models import RoleAssignment
from apps.users.services_memberships import membership_create
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


def _clergy_attached_to(church, pastoral_role):
    """Clergé « nu » : rôle PASTORAL + appartenance réelle, AUCUNE RoleAssignment.

    C'est l'état d'un curé validé sans cible territoriale exploitable (cf.
    ``services_clergy._resolve_capacity``) — le cas majoritaire en production.
    """
    user = BaseUserFactory(pastoral_role=pastoral_role)
    membership_create(user=user, church=church, is_primary=True)
    user.refresh_from_db()  # diocese/province sont remplis par signal via .update()
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


# ---------------------------------------------------------------------------
# Autorité PASTORALE — publier sans RoleAssignment (dimension orthogonale)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_priest_without_role_assignment_publishes_on_his_own_parish():
    """Régression : l'autorité n'était résolue que par ``RoleAssignment``
    (dimension ADMINISTRATIVE). Un prêtre validé n'en porte pas nécessairement —
    il se voyait donc refuser la réflexion pastorale, qui est pourtant son acte
    propre. La voie PASTORALE la lui rend sur SA paroisse."""
    church = ChurchFactory()
    author = _clergy_attached_to(church, PastoralRole.PRETRE)

    reflection = reflection_upsert(
        author=author, content="Méditez l'Évangile du jour.", reflection_date=D,
        scope_type="parish", scope_parish_id=church.parish_id,
    )

    assert reflection.scope_parish_id == church.parish_id


@pytest.mark.django_db
def test_priest_without_role_assignment_is_refused_on_a_foreign_parish():
    """Fail-closed : la charge pastorale ne vaut que sur SON territoire. Un
    identifiant de paroisse arbitraire envoyé par le client n'ouvre aucun droit."""
    church = ChurchFactory()
    author = _clergy_attached_to(church, PastoralRole.PRETRE)

    with pytest.raises(ApplicationError):
        reflection_upsert(
            author=author, content="Injection", reflection_date=D,
            scope_type="parish", scope_parish_id=ParishFactory().id,
        )


@pytest.mark.django_db
def test_priest_without_any_membership_has_no_territory():
    # Rôle pastoral SANS appartenance → aucun territoire, donc aucun droit.
    author = BaseUserFactory(pastoral_role=PastoralRole.PRETRE)

    with pytest.raises(ApplicationError):
        reflection_upsert(
            author=author, content="x", reflection_date=D,
            scope_type="parish", scope_parish_id=ParishFactory().id,
        )


@pytest.mark.django_db
def test_priest_without_role_assignment_cannot_reach_the_diocese_scope():
    # Matrice §16 : le prêtre publie au niveau PAROISSE, l'évêque au diocèse.
    church = ChurchFactory()
    author = _clergy_attached_to(church, PastoralRole.PRETRE)

    with pytest.raises(ApplicationError):
        reflection_upsert(
            author=author, content="x", reflection_date=D,
            scope_type="diocese", scope_diocese_id=church.parish.diocese_id,
        )


@pytest.mark.django_db
def test_bishop_without_role_assignment_covers_his_diocese_but_not_a_foreign_one():
    church = ChurchFactory()
    bishop = _clergy_attached_to(church, PastoralRole.EVEQUE)

    reflection = reflection_upsert(
        author=bishop, content="Lettre du jour", reflection_date=D,
        scope_type="diocese", scope_diocese_id=church.parish.diocese_id,
    )
    assert reflection.scope_diocese_id == church.parish.diocese_id

    with pytest.raises(ApplicationError):
        reflection_upsert(
            author=bishop, content="Hors diocèse", reflection_date=D,
            scope_type="diocese", scope_diocese_id=DioceseFactory().id,
        )


@pytest.mark.django_db
def test_pastoral_route_never_opens_the_global_scope():
    # La portée globale reste réservée aux administrateurs province / national.
    church = ChurchFactory()
    author = _clergy_attached_to(church, PastoralRole.PRETRE)

    with pytest.raises(ApplicationError):
        reflection_upsert(
            author=author, content="x", reflection_date=D, scope_type="global",
        )


@pytest.mark.django_db
def test_deacon_has_no_pastoral_publishing_authority():
    # Matrice §16 : le diacre ORGANISE (agenda) mais ne PUBLIE pas de réflexion.
    # Les deux apps partagent le même helper avec des `allowed_roles` distincts.
    church = ChurchFactory()
    deacon = _clergy_attached_to(church, PastoralRole.DIACRE)

    with pytest.raises(ApplicationError):
        reflection_upsert(
            author=deacon, content="x", reflection_date=D,
            scope_type="parish", scope_parish_id=church.parish_id,
        )


@pytest.mark.django_db
def test_religious_has_no_pastoral_publishing_authority():
    church = ChurchFactory()
    religious = _clergy_attached_to(church, PastoralRole.RELIGIEUX)

    with pytest.raises(ApplicationError):
        reflection_upsert(
            author=religious, content="x", reflection_date=D,
            scope_type="parish", scope_parish_id=church.parish_id,
        )


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
