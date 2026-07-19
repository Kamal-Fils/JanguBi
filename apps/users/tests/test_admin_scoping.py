"""Cloisonnement territorial de la gestion des comptes.

Sans ces gardes, un administrateur diocésain pouvait lister toute la
plateforme, désactiver ou anonymiser n'importe quel compte — y compris hors de
son diocèse. Le module `apps/documents/` sert de référence : fail-CLOSED, un
admin sans affectation territoriale n'a autorité sur personne.
"""

import pytest

from apps.core.exceptions import ApplicationError
from apps.org.tests.factories import DioceseFactory, ParishFactory
from apps.users.enums import RoleScope, UserRole
from apps.users.selectors import user_is_in_scope_of, user_list
from apps.users.services import user_soft_delete, user_toggle_active

from .factories import (
    BaseUserFactory,
    ProfileFactory,
    RoleAssignmentFactory,
    SuperAdminFactory,
)

pytestmark = pytest.mark.django_db


def _fidele(parish):
    """Fidèle rattaché à une paroisse (onboarding terminé)."""
    user = BaseUserFactory(role=UserRole.FIDELE)
    ProfileFactory(user=user, primary_parish=parish)
    return user


def _parish_admin(parish):
    """Admin réellement affecté à une paroisse."""
    admin = BaseUserFactory(role=UserRole.PARISH_ADMIN)
    ProfileFactory(user=admin, primary_parish=parish)
    RoleAssignmentFactory(
        user=admin,
        role=UserRole.PARISH_ADMIN,
        scope=RoleScope.PARISH,
        parish=parish,
        is_active=True,
    )
    return admin


def _admin_sans_affectation():
    """Le cas produit par `user_create_by_admin` : rôle admin, zéro périmètre."""
    admin = BaseUserFactory(role=UserRole.DIOCESE_ADMIN)
    ProfileFactory(user=admin)
    return admin


# ---------------------------------------------------------------------------
# Autorité territoriale
# ---------------------------------------------------------------------------


def test_admin_a_autorite_sur_sa_paroisse():
    parish = ParishFactory()
    admin = _parish_admin(parish)

    assert user_is_in_scope_of(target=_fidele(parish), admin=admin) is True


def test_admin_n_a_pas_autorite_sur_une_autre_paroisse():
    admin = _parish_admin(ParishFactory())

    assert user_is_in_scope_of(target=_fidele(ParishFactory()), admin=admin) is False


def test_admin_sans_affectation_n_a_autorite_sur_personne():
    """Fail-closed : l'ancien repli donnait autorité sur TOUT le monde."""
    admin = _admin_sans_affectation()

    assert user_is_in_scope_of(target=_fidele(ParishFactory()), admin=admin) is False


def test_admin_garde_autorite_sur_son_propre_compte():
    admin = _admin_sans_affectation()

    assert user_is_in_scope_of(target=admin, admin=admin) is True


def test_admin_global_a_autorite_partout():
    superadmin = SuperAdminFactory()

    assert user_is_in_scope_of(target=_fidele(ParishFactory()), admin=superadmin) is True


def test_utilisateur_sans_paroisse_hors_perimetre_d_un_admin_scope():
    """Onboarding non terminé : rattaché à aucun territoire."""
    admin = _parish_admin(ParishFactory())
    orphelin = BaseUserFactory(role=UserRole.FIDELE)
    ProfileFactory(user=orphelin, primary_parish=None)

    assert user_is_in_scope_of(target=orphelin, admin=admin) is False


# ---------------------------------------------------------------------------
# Liste des utilisateurs
# ---------------------------------------------------------------------------


def test_liste_limitee_a_la_paroisse_de_l_admin():
    parish = ParishFactory()
    admin = _parish_admin(parish)
    interne = _fidele(parish)
    externe = _fidele(ParishFactory())

    ids = set(user_list(for_user=admin).values_list("id", flat=True))

    assert interne.id in ids
    assert externe.id not in ids


def test_liste_fail_closed_pour_un_admin_sans_affectation():
    """Sans cette garde, la liste renvoyait TOUTE la plateforme."""
    admin = _admin_sans_affectation()
    autre = _fidele(ParishFactory())

    ids = set(user_list(for_user=admin).values_list("id", flat=True))

    assert autre.id not in ids
    assert ids == {admin.id}  # il se voit lui-même, rien d'autre


def test_liste_complete_pour_un_admin_global():
    superadmin = SuperAdminFactory()
    fidele = _fidele(ParishFactory())

    ids = set(user_list(for_user=superadmin).values_list("id", flat=True))

    assert fidele.id in ids


# ---------------------------------------------------------------------------
# Actions destructives
# ---------------------------------------------------------------------------


def test_desactivation_refusee_hors_perimetre():
    admin = _parish_admin(ParishFactory())
    cible = _fidele(ParishFactory())

    with pytest.raises(ApplicationError):
        user_toggle_active(user=cible, is_active=False, performed_by=admin)

    cible.refresh_from_db()
    assert cible.is_active is True


def test_desactivation_autorisee_dans_le_perimetre():
    parish = ParishFactory()
    admin = _parish_admin(parish)
    cible = _fidele(parish)

    user_toggle_active(user=cible, is_active=False, performed_by=admin)

    cible.refresh_from_db()
    assert cible.is_active is False


def test_anonymisation_refusee_hors_perimetre():
    """Le cas le plus grave : opération irréversible sur l'identité."""
    admin = _parish_admin(ParishFactory())
    cible = _fidele(ParishFactory())
    email_initial = cible.email

    with pytest.raises(ApplicationError):
        user_soft_delete(user=cible, performed_by=admin)

    cible.refresh_from_db()
    assert cible.email == email_initial
    assert cible.is_active is True


def test_anonymisation_refusee_a_un_admin_sans_affectation():
    admin = _admin_sans_affectation()
    cible = _fidele(ParishFactory())
    email_initial = cible.email

    with pytest.raises(ApplicationError):
        user_soft_delete(user=cible, performed_by=admin)

    cible.refresh_from_db()
    assert cible.email == email_initial


def test_chacun_peut_supprimer_son_propre_compte():
    """Un fidèle reste maître de son compte, sans rôle admin."""
    user = _fidele(ParishFactory())

    user_soft_delete(user=user, performed_by=user)

    user.refresh_from_db()
    assert user.is_active is False
    assert user.email.startswith("deleted_")


def test_admin_diocesain_couvre_les_paroisses_de_son_diocese():
    diocese = DioceseFactory()
    parish = ParishFactory(diocese=diocese)
    admin = BaseUserFactory(role=UserRole.DIOCESE_ADMIN)
    ProfileFactory(user=admin)
    RoleAssignmentFactory(
        user=admin,
        role=UserRole.DIOCESE_ADMIN,
        scope=RoleScope.DIOCESE,
        diocese=diocese,
        parish=None,
        is_active=True,
    )

    assert user_is_in_scope_of(target=_fidele(parish), admin=admin) is True
    assert user_is_in_scope_of(target=_fidele(ParishFactory()), admin=admin) is False
