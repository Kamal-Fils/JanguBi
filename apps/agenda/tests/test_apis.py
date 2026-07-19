import datetime

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.agenda.models import Event
from apps.users.enums import UserOnboardingState
from apps.users.models import BaseUser


def _make_user(email, pastoral_role="fidele", role="fidele"):
    user = BaseUser.objects.create_user(
        email=email,
        password="StrongPassw0rd!",
        role=role,
        phone_number=f"+221770{abs(hash(email)) % 1_000_000:06d}",
        is_active=True,
        is_verified=True,
    )
    user.pastoral_role = pastoral_role
    user.onboarding_state = UserOnboardingState.COMPLETED  # onboardé → peut écrire (A1)
    user.save(update_fields=["pastoral_role", "onboarding_state"])
    return user


def _event_data():
    now = timezone.now()
    return {
        "title": "Messe dominicale",
        "event_type": "mass",
        "start_at": (now + datetime.timedelta(hours=2)).isoformat(),
        "end_at": (now + datetime.timedelta(hours=3)).isoformat(),
        "scope_type": "global",
    }


@pytest.fixture
def pretre_client(db):
    client = APIClient()
    user = _make_user("pretre@example.com", "pretre")
    client.force_authenticate(user=user)
    client._user = user
    return client


@pytest.fixture
def fidele_client(db):
    client = APIClient()
    user = _make_user("fidele@example.com", "fidele")
    client.force_authenticate(user=user)
    client._user = user
    return client


@pytest.mark.django_db
def test_event_create_clergy_201():
    # Un curé (RoleAssignment parish_admin) crée un événement scopé à SA paroisse.
    # (La portée globale est désormais réservée aux admins province/national.)
    from apps.org.tests.factories import ParishFactory
    from apps.users.enums import RoleScope, UserRole
    from apps.users.models import RoleAssignment

    parish = ParishFactory()
    cure = _make_user("cure-agenda@example.com", "pretre")
    RoleAssignment.objects.create(
        user=cure, role=UserRole.PARISH_ADMIN, scope=RoleScope.PARISH,
        parish=parish, is_active=True,
    )
    client = APIClient()
    client.force_authenticate(user=cure)
    url = reverse("api:agenda:event-list-create")
    data = {**_event_data(), "scope_type": "parish", "scope_id": parish.id}

    resp = client.post(url, data, format="json")

    assert resp.status_code == status.HTTP_201_CREATED
    assert Event.objects.filter(organizer=cure).count() == 1


@pytest.mark.django_db
def test_event_create_fidele_400(fidele_client):
    url = reverse("api:agenda:event-list-create")
    resp = fidele_client.post(url, _event_data(), format="json")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_event_list(fidele_client, pretre_client):
    now = timezone.now()
    Event.objects.create(
        organizer=pretre_client._user,
        title="Test",
        event_type="mass",
        start_at=now + datetime.timedelta(hours=1),
        end_at=now + datetime.timedelta(hours=2),
        scope_type="global",
    )
    url = reverse("api:agenda:event-list-create")
    resp = fidele_client.get(url)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["count"] == 1


@pytest.mark.django_db
def test_event_register(fidele_client, pretre_client):
    now = timezone.now()
    event = Event.objects.create(
        organizer=pretre_client._user,
        title="Retraite",
        event_type="retreat",
        start_at=now + datetime.timedelta(days=1),
        end_at=now + datetime.timedelta(days=2),
        scope_type="global",
    )
    url = reverse("api:agenda:event-register", kwargs={"event_id": event.pk})
    resp = fidele_client.post(url)
    assert resp.status_code == status.HTTP_201_CREATED
    assert event.registrations.count() == 1


@pytest.mark.django_db
def test_event_register_full(fidele_client, pretre_client):
    now = timezone.now()
    event = Event.objects.create(
        organizer=pretre_client._user,
        title="Petite messe",
        event_type="mass",
        start_at=now + datetime.timedelta(hours=1),
        end_at=now + datetime.timedelta(hours=2),
        scope_type="global",
        max_participants=0,
    )
    url = reverse("api:agenda:event-register", kwargs={"event_id": event.pk})
    resp = fidele_client.post(url)
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_event_requires_auth():
    client = APIClient()
    url = reverse("api:agenda:event-list-create")
    resp = client.get(url)
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_event_register_pending_parish_blocked_returns_403():
    # EXPLOIT A1 : un fidèle pur en pending_parish (paroisse non choisie) ne peut
    # PAS s'inscrire à un événement. Même endpoint que test_event_register
    # (completed → 201) : seul l'onboarding_state change → le 403 vient de la garde.
    # La garde (has_permission) précède la résolution de l'objet, d'où l'event_id factice.
    user = BaseUser.objects.create_user(
        email="pending_ag@test.com",
        password="StrongPassw0rd!",
        role="fidele",
        phone_number="+221770999333",
        is_active=True,
        is_verified=True,
    )
    user.onboarding_state = UserOnboardingState.PENDING_PARISH_SELECTION
    user.save(update_fields=["onboarding_state"])
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse("api:agenda:event-register", kwargs={"event_id": 999999})

    resp = client.post(url)

    assert resp.status_code == status.HTTP_403_FORBIDDEN


def _make_global_event(organizer, title="Évènement"):
    now = timezone.now()
    return Event.objects.create(
        organizer=organizer,
        title=title,
        event_type="mass",
        start_at=now + datetime.timedelta(hours=1),
        end_at=now + datetime.timedelta(hours=2),
        scope_type="global",
    )


@pytest.mark.django_db
def test_event_list_includes_is_registered(fidele_client, pretre_client):
    # Anti-régression Flux 2 : le back DOIT exposer is_registered pour le user courant,
    # sinon le front (event-card) ne bascule jamais le bouton et re-poste → 400.
    registered = _make_global_event(pretre_client._user, "Inscrit")
    _make_global_event(pretre_client._user, "Pas inscrit")
    reg_url = reverse("api:agenda:event-register", kwargs={"event_id": registered.pk})
    assert fidele_client.post(reg_url).status_code == status.HTTP_201_CREATED

    resp = fidele_client.get(reverse("api:agenda:event-list-create"))

    assert resp.status_code == status.HTTP_200_OK
    by_title = {e["title"]: e for e in resp.data["results"]}
    assert by_title["Inscrit"]["is_registered"] is True
    assert by_title["Pas inscrit"]["is_registered"] is False


@pytest.mark.django_db
def test_event_list_query_count_does_not_grow_with_the_number_of_events(
    fidele_client, pretre_client
):
    """N+1 : le coût d'une page ne doit pas dépendre du nombre d'événements qu'elle
    contient.

    ``registration_count`` était calculé par le serializer via
    ``obj.registrations.count()`` — un COUNT par événement, sur un feed paginé.
    On compare donc une page à 1 événement et une page à 12, et on exige
    l'ÉGALITÉ du nombre de requêtes. On ne fige PAS un nombre absolu : il dépend
    de l'authentification et du scoping, et un tel test se périmerait au premier
    changement sans rien prouver de plus.
    """
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from apps.agenda.models import EventRegistration

    # limit=50 : les 12 événements tiennent sur UNE page (PAGE_SIZE vaut 10).
    url = f"{reverse('api:agenda:event-list-create')}?limit=50"
    organizer = pretre_client._user

    def _register_on(event):
        # Des inscrits réels : c'est bien le comptage par événement qu'on mesure.
        EventRegistration.objects.create(event=event, user=organizer)

    def _query_count():
        with CaptureQueriesContext(connection) as ctx:
            resp = fidele_client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        return len(ctx.captured_queries)

    _register_on(_make_global_event(organizer, "Évt 00"))
    fidele_client.get(url)  # requête de chauffe (caches paresseux du framework)
    baseline = _query_count()

    for i in range(1, 12):
        _register_on(_make_global_event(organizer, f"Évt {i:02d}"))

    assert fidele_client.get(url).data["count"] == 12
    assert _query_count() == baseline


@pytest.mark.django_db
def test_event_list_reports_the_registration_count(fidele_client, pretre_client):
    """Garde-fou de l'annotation : optimiser le comptage ne doit pas fausser sa
    valeur (une annotation muette qui renverrait 0 passerait le test de N+1)."""
    event = _make_global_event(pretre_client._user, "Compté")
    assert fidele_client.post(
        reverse("api:agenda:event-register", kwargs={"event_id": event.pk})
    ).status_code == status.HTTP_201_CREATED

    listing = fidele_client.get(reverse("api:agenda:event-list-create"))
    detail = fidele_client.get(
        reverse("api:agenda:event-detail", kwargs={"event_id": event.pk})
    )

    assert listing.data["results"][0]["registration_count"] == 1
    assert detail.data["registration_count"] == 1


@pytest.mark.django_db
def test_event_detail_includes_is_registered(fidele_client, pretre_client):
    event = _make_global_event(pretre_client._user)
    reg_url = reverse("api:agenda:event-register", kwargs={"event_id": event.pk})
    fidele_client.post(reg_url)

    resp = fidele_client.get(
        reverse("api:agenda:event-detail", kwargs={"event_id": event.pk})
    )

    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["is_registered"] is True


@pytest.mark.django_db
def test_event_unregister_204(fidele_client, pretre_client):
    # Anti-régression Flux 2 : l'annulation (DELETE) renvoyait 405 (méthode absente).
    event = _make_global_event(pretre_client._user)
    url = reverse("api:agenda:event-register", kwargs={"event_id": event.pk})
    assert fidele_client.post(url).status_code == status.HTTP_201_CREATED

    resp = fidele_client.delete(url)

    assert resp.status_code == status.HTTP_204_NO_CONTENT
    assert event.registrations.count() == 0


@pytest.mark.django_db
def test_event_unregister_not_registered_returns_400(fidele_client, pretre_client):
    event = _make_global_event(pretre_client._user)
    url = reverse("api:agenda:event-register", kwargs={"event_id": event.pk})

    resp = fidele_client.delete(url)

    assert resp.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Autorité PASTORALE de création (dimension orthogonale au UserRole admin)
# ---------------------------------------------------------------------------

def _priest_of_church(church, email="cure-pastoral@example.com"):
    """Curé « nu » : rôle PASTORAL prêtre + appartenance réelle, AUCUNE
    RoleAssignment admin. C'est l'état d'un curé validé par invitation sans cible
    territoriale, ou par auto-déclaration (cf. clergy_accounts._resolve_capacity)."""
    from apps.users.enums import PastoralRole
    from apps.users.services_memberships import membership_create

    user = _make_user(email, PastoralRole.PRETRE)
    membership_create(user=user, church=church, is_primary=True)
    return user


@pytest.mark.django_db
def test_event_create_by_priest_without_role_assignment_201():
    # Régression : le curé est l'acteur naturel d'un événement paroissial, mais
    # l'autorité n'était résolue que par RoleAssignment (dimension admin) → 400.
    from apps.org.tests.factories import ChurchFactory

    church = ChurchFactory()
    cure = _priest_of_church(church)
    client = APIClient()
    client.force_authenticate(user=cure)
    data = {**_event_data(), "scope_type": "parish", "scope_id": church.parish_id}

    resp = client.post(reverse("api:agenda:event-list-create"), data, format="json")

    assert resp.status_code == status.HTTP_201_CREATED
    assert Event.objects.get(organizer=cure).scope_parish_id == church.parish_id


@pytest.mark.django_db
def test_event_create_by_priest_on_foreign_parish_400():
    # Fail-closed : l'autorité pastorale ne vaut que sur SON territoire, jamais
    # sur un identifiant arbitraire envoyé par le client.
    from apps.org.tests.factories import ChurchFactory, ParishFactory

    church = ChurchFactory()
    foreign_parish = ParishFactory()
    cure = _priest_of_church(church, "cure-a@example.com")
    client = APIClient()
    client.force_authenticate(user=cure)
    data = {**_event_data(), "scope_type": "parish", "scope_id": foreign_parish.id}

    resp = client.post(reverse("api:agenda:event-list-create"), data, format="json")

    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_event_create_by_priest_on_diocese_scope_400():
    # Matrice §16 AGENDA : le prêtre crée au niveau PAROISSE, l'évêque au diocèse.
    from apps.org.tests.factories import ChurchFactory

    church = ChurchFactory()
    cure = _priest_of_church(church, "cure-diocese@example.com")
    client = APIClient()
    client.force_authenticate(user=cure)
    data = {**_event_data(), "scope_type": "diocese", "scope_id": church.parish.diocese_id}

    resp = client.post(reverse("api:agenda:event-list-create"), data, format="json")

    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_event_create_by_bishop_on_own_diocese_201():
    from apps.org.tests.factories import ChurchFactory
    from apps.users.enums import PastoralRole
    from apps.users.services_memberships import membership_create

    church = ChurchFactory()
    bishop = _make_user("eveque-agenda@example.com", PastoralRole.EVEQUE)
    membership_create(user=bishop, church=church, is_primary=True)
    client = APIClient()
    client.force_authenticate(user=bishop)
    data = {**_event_data(), "scope_type": "diocese", "scope_id": church.parish.diocese_id}

    resp = client.post(reverse("api:agenda:event-list-create"), data, format="json")

    assert resp.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_event_create_by_priest_on_global_scope_400():
    # La portée globale reste réservée aux administrateurs province / national :
    # la voie pastorale ne l'ouvre jamais.
    from apps.org.tests.factories import ChurchFactory

    church = ChurchFactory()
    cure = _priest_of_church(church, "cure-global@example.com")
    client = APIClient()
    client.force_authenticate(user=cure)

    resp = client.post(reverse("api:agenda:event-list-create"), _event_data(), format="json")

    assert resp.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Suppression d'un événement (annulation douce)
# ---------------------------------------------------------------------------

def _parish_event(organizer, parish):
    now = timezone.now()
    return Event.objects.create(
        organizer=organizer,
        title="Messe de rentrée",
        event_type="mass",
        start_at=now + datetime.timedelta(days=1),
        end_at=now + datetime.timedelta(days=1, hours=2),
        scope_type="parish",
        scope_parish=parish,
    )


@pytest.mark.django_db
def test_event_delete_by_organizer_cancels_and_notifies(fidele_client):
    from apps.emails.models import Email
    from apps.org.tests.factories import ChurchFactory

    church = ChurchFactory()
    cure = _priest_of_church(church, "cure-del@example.com")
    event = _parish_event(cure, church.parish)
    assert fidele_client.post(
        reverse("api:agenda:event-register", kwargs={"event_id": event.pk})
    ).status_code == status.HTTP_201_CREATED
    client = APIClient()
    client.force_authenticate(user=cure)

    resp = client.delete(reverse("api:agenda:event-detail", kwargs={"event_id": event.pk}))

    assert resp.status_code == status.HTTP_204_NO_CONTENT
    event.refresh_from_db()
    assert event.cancelled_at is not None
    assert event.cancelled_by_id == cure.id
    # L'inscription survit (trace) et l'inscrit est prévenu par email.
    assert event.registrations.count() == 1
    assert Email.objects.filter(to=fidele_client._user.email).exists()


@pytest.mark.django_db
def test_event_delete_by_stranger_403():
    from apps.org.tests.factories import ChurchFactory

    church = ChurchFactory()
    cure = _priest_of_church(church, "cure-del2@example.com")
    event = _parish_event(cure, church.parish)
    intruder = _make_user("intrus@example.com", "pretre")
    client = APIClient()
    client.force_authenticate(user=intruder)

    resp = client.delete(reverse("api:agenda:event-detail", kwargs={"event_id": event.pk}))

    assert resp.status_code == status.HTTP_403_FORBIDDEN
    event.refresh_from_db()
    assert event.cancelled_at is None


@pytest.mark.django_db
def test_cancelled_event_leaves_the_feed_and_refuses_registration(fidele_client):
    from apps.agenda.services import event_cancel
    from apps.org.tests.factories import ChurchFactory

    church = ChurchFactory()
    cure = _priest_of_church(church, "cure-del3@example.com")
    event = _parish_event(cure, church.parish)
    event_cancel(event=event, actor=cure)

    listing = fidele_client.get(reverse("api:agenda:event-list-create"))
    register = fidele_client.post(
        reverse("api:agenda:event-register", kwargs={"event_id": event.pk})
    )

    assert event.pk not in [e["id"] for e in listing.data["results"]]
    assert register.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_event_delete_is_idempotent():
    from apps.org.tests.factories import ChurchFactory

    church = ChurchFactory()
    cure = _priest_of_church(church, "cure-del4@example.com")
    event = _parish_event(cure, church.parish)
    client = APIClient()
    client.force_authenticate(user=cure)
    url = reverse("api:agenda:event-detail", kwargs={"event_id": event.pk})

    assert client.delete(url).status_code == status.HTTP_204_NO_CONTENT
    second = client.delete(url)

    assert second.status_code == status.HTTP_400_BAD_REQUEST
