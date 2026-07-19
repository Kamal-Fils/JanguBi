"""Cloisonnement territorial des intentions de messe (correctif de sécurité).

Faille corrigée : le contrôle de rôle des endpoints (`pretre`/`eveque`/
`archeveque`) est **global**. Sans garde territoriale, n'importe quel prêtre du
pays pouvait accepter, refuser, dater ou marquer célébrée l'intention d'un
fidèle d'une AUTRE paroisse — et lire au passage ``intention_text``, qui
contient souvent une confidence personnelle (maladie, deuil).

Invariants vérifiés ici :
  * un prêtre de la paroisse B ne peut ni lire ni traiter une intention de A ;
  * le prêtre de la bonne paroisse le peut toujours ;
  * le fidèle auteur lit toujours la sienne ;
  * un prêtre sans périmètre déterminable ne peut RIEN traiter (fail-closed).
"""

import itertools

import pytest
from django.http import Http404
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.core.exceptions import ApplicationError
from apps.mass_intentions.models import MassIntention
from apps.mass_intentions.selectors import mass_intention_get, mass_intention_list_pending
from apps.mass_intentions.services import (
    mass_intention_accept,
    mass_intention_celebrate,
    mass_intention_decline,
    mass_intention_propose_date,
)
from apps.users.enums import UserOnboardingState
from apps.users.models import BaseUser, Profile

_phone_seq = itertools.count(1)


def _user(email, pastoral_role="fidele", parish=None):
    user = BaseUser.objects.create_user(
        email=email,
        password="StrongPassw0rd!",
        role="fidele",
        phone_number=f"+2217712{next(_phone_seq):05d}",
        is_active=True,
        is_verified=True,
    )
    user.pastoral_role = pastoral_role
    user.onboarding_state = UserOnboardingState.COMPLETED
    user.save(update_fields=["pastoral_role", "onboarding_state"])
    if parish is not None:
        Profile.objects.update_or_create(user=user, defaults={"primary_parish": parish})
    return user


@pytest.fixture
def parishes(db):
    """Deux paroisses de diocèses DISTINCTS : un prêtre de B ne doit hériter
    d'aucune autorité sur A par la chaîne diocèse → province."""
    from apps.org.tests.factories import ParishFactory

    return ParishFactory(), ParishFactory()


@pytest.fixture
def scenario(db, parishes):
    """Fidèle + intention en paroisse A, prêtre légitime en A, prêtre intrus en B."""
    parish_a, parish_b = parishes
    fidele = _user("fidele.a@test.com", "fidele", parish=parish_a)
    intention = MassIntention.objects.create(
        requestor=fidele,
        intention_type="for_deceased",
        intention_text="Pour ma mère décédée d'un cancer — confidence personnelle.",
        parish=parish_a,
    )
    return {
        "parish_a": parish_a,
        "parish_b": parish_b,
        "fidele": fidele,
        "intention": intention,
        "pretre_a": _user("pretre.a@test.com", "pretre", parish=parish_a),
        "pretre_b": _user("pretre.b@test.com", "pretre", parish=parish_b),
    }


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_pretre_autre_paroisse_ne_peut_pas_lire_intention(scenario):
    # EXPLOIT : lecture par ID d'une intention d'une autre paroisse.
    # 404 (et non 403) : ne pas révéler l'existence de l'intention.
    with pytest.raises(Http404):
        mass_intention_get(
            intention_id=scenario["intention"].pk, user=scenario["pretre_b"]
        )


@pytest.mark.django_db
def test_pretre_de_la_paroisse_peut_lire_intention(scenario):
    obj = mass_intention_get(intention_id=scenario["intention"].pk, user=scenario["pretre_a"])
    assert obj.pk == scenario["intention"].pk


@pytest.mark.django_db
def test_fidele_auteur_peut_toujours_lire_la_sienne(scenario):
    # Non-régression : le cloisonnement ne doit pas fermer la porte au demandeur,
    # y compris si son propre périmètre clergé est vide.
    obj = mass_intention_get(intention_id=scenario["intention"].pk, user=scenario["fidele"])
    assert obj.pk == scenario["intention"].pk


@pytest.mark.django_db
def test_fidele_ne_peut_pas_lire_intention_d_autrui(scenario):
    autre = _user("autre.fidele@test.com", "fidele", parish=scenario["parish_a"])
    with pytest.raises(Http404):
        mass_intention_get(intention_id=scenario["intention"].pk, user=autre)


# ---------------------------------------------------------------------------
# Les 4 actions — prêtre d'une autre paroisse (via l'API, bout en bout)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
@pytest.mark.parametrize(
    "route,payload",
    [
        ("accept", None),
        ("propose-date", {"proposed_date": "2026-09-14"}),
        ("celebrate", None),
        ("decline", {"notes": "Agenda complet."}),
    ],
)
def test_pretre_autre_paroisse_ne_peut_traiter_aucune_action(scenario, route, payload):
    # EXPLOIT bout en bout : le rôle pastoral passe (c'est bien un prêtre), mais
    # l'autorité territoriale bloque → 404, et l'intention reste intacte.
    intention = scenario["intention"]
    url = reverse(f"api:mass-intentions:{route}", kwargs={"intention_id": intention.pk})

    resp = _client(scenario["pretre_b"]).post(url, payload or {}, format="json")

    assert resp.status_code == status.HTTP_404_NOT_FOUND
    intention.refresh_from_db()
    assert intention.status == "pending"
    assert intention.pretre_id is None


@pytest.mark.django_db
def test_pretre_de_la_paroisse_peut_accepter(scenario):
    intention = scenario["intention"]
    url = reverse("api:mass-intentions:accept", kwargs={"intention_id": intention.pk})

    resp = _client(scenario["pretre_a"]).post(url)

    assert resp.status_code == status.HTTP_200_OK
    intention.refresh_from_db()
    assert intention.status == "accepted"
    assert intention.pretre_id == scenario["pretre_a"].pk


# ---------------------------------------------------------------------------
# Couche service — défense en profondeur (hors HTTP)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_services_refusent_un_pretre_hors_perimetre(scenario):
    # Les services doivent rester sûrs appelés directement (tâche Celery,
    # commande de gestion) : la garde n'est pas seulement dans l'API.
    intention = scenario["intention"]
    intrus = scenario["pretre_b"]

    for call in (
        lambda: mass_intention_accept(intention=intention, pretre=intrus),
        lambda: mass_intention_propose_date(
            intention=intention, proposed_date="2026-09-14", pretre=intrus
        ),
        lambda: mass_intention_celebrate(intention=intention, pretre=intrus),
        lambda: mass_intention_decline(intention=intention, pretre=intrus, notes="x"),
    ):
        with pytest.raises(ApplicationError) as exc:
            call()
        # Message user-safe : ne divulgue pas la paroisse d'autrui.
        assert scenario["parish_a"].name not in str(exc.value)

    intention.refresh_from_db()
    assert intention.status == "pending"


# ---------------------------------------------------------------------------
# Fail-closed — clergé sans périmètre déterminable
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_pretre_sans_perimetre_ne_peut_rien_traiter(scenario):
    # Ni RoleAssignment, ni paroisse principale → aucun périmètre.
    # Il ne doit PAS hériter de « tout » : il n'a droit à rien.
    orphelin = _user("pretre.sans.paroisse@test.com", "pretre", parish=None)

    with pytest.raises(Http404):
        mass_intention_get(intention_id=scenario["intention"].pk, user=orphelin)

    with pytest.raises(ApplicationError):
        mass_intention_accept(intention=scenario["intention"], pretre=orphelin)


@pytest.mark.django_db
def test_pretre_sans_perimetre_ne_voit_aucune_intention_en_attente(scenario):
    # Régression du fail-open : avant, l'absence de primary_parish retirait tout
    # filtre et exposait les intentions en attente de tout le pays.
    orphelin = _user("pretre.orphelin2@test.com", "pretre", parish=None)

    assert mass_intention_list_pending(pretre=orphelin).count() == 0


@pytest.mark.django_db
def test_liste_en_attente_est_scopee_a_la_paroisse(scenario):
    assert mass_intention_list_pending(pretre=scenario["pretre_b"]).count() == 0

    visibles = mass_intention_list_pending(pretre=scenario["pretre_a"])
    assert [o.pk for o in visibles] == [scenario["intention"].pk]


@pytest.mark.django_db
def test_intention_sans_paroisse_n_est_traitable_par_aucun_pretre(scenario):
    # Donnée legacy (parish nullable) : fail-closed plutôt que « accessible à tous ».
    orpheline = MassIntention.objects.create(
        requestor=scenario["fidele"],
        intention_type="for_living",
        intention_text="Sans paroisse rattachée",
    )

    with pytest.raises(Http404):
        mass_intention_get(intention_id=orpheline.pk, user=scenario["pretre_a"])
    with pytest.raises(ApplicationError):
        mass_intention_accept(intention=orpheline, pretre=scenario["pretre_a"])


@pytest.mark.django_db
def test_admin_global_conserve_l_acces(scenario):
    from apps.users.enums import UserRole

    admin = _user("super@test.com", "fidele", parish=None)
    admin.role = UserRole.SUPER_ADMIN
    admin.save(update_fields=["role"])

    obj = mass_intention_get(intention_id=scenario["intention"].pk, user=admin)
    assert obj.pk == scenario["intention"].pk
