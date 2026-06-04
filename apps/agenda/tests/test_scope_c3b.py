"""
Chantier 3b — scope ÉGLISE + feed multi-appartenance sur l'agenda (Event).

Visibilité par appartenance, agrégation du feed, création scope église/paroisse
(résolution INT→FK), autorité CHURCH (church_admin), garde de la liste des inscrits,
et résolution/flag de la migration data.
"""

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.agenda.migration_ops import resolve_scope_fk
from apps.agenda.models import Event, EventRegistration
from apps.agenda.selectors import event_list_for_user
from apps.agenda.services import event_create
from apps.core.exceptions import ApplicationError
from apps.org.models import Diocese, Parish
from apps.org.tests.factories import ChurchFactory, DioceseFactory, ParishFactory
from apps.users.enums import RoleScope, UserRole
from apps.users.models import RoleAssignment
from apps.users.services_memberships import membership_create
from apps.users.tests.factories import BaseUserFactory


def _event(*, scope_type="global", scope_parish=None, scope_diocese=None, scope_church=None, organizer=None):
    now = timezone.now()
    return Event.objects.create(
        organizer=organizer,
        title="Évt",
        event_type="mass",
        start_at=now + datetime.timedelta(days=1),
        end_at=now + datetime.timedelta(days=1, hours=2),
        scope_type=scope_type,
        scope_parish=scope_parish,
        scope_diocese=scope_diocese,
        scope_church=scope_church,
    )


def _member_of_church(church):
    user = BaseUserFactory()
    membership_create(user=user, church=church, is_primary=True)
    return user


def _cure_of_parish(parish):
    user = BaseUserFactory(role=UserRole.PARISH_ADMIN)
    RoleAssignment.objects.create(
        user=user, role=UserRole.PARISH_ADMIN, scope=RoleScope.PARISH,
        parish=parish, is_active=True,
    )
    return user


def _church_admin(church):
    user = BaseUserFactory(role=UserRole.CHURCH_ADMIN)
    RoleAssignment.objects.create(
        user=user, role=UserRole.CHURCH_ADMIN, scope=RoleScope.CHURCH,
        church=church, is_active=True,
    )
    return user


def _feed_ids(user):
    return set(event_list_for_user(user=user).values_list("id", flat=True))


def _event_payload(**extra):
    now = timezone.now()
    return {
        "title": "Évt",
        "event_type": "mass",
        "start_at": (now + datetime.timedelta(days=1)).isoformat(),
        "end_at": (now + datetime.timedelta(days=1, hours=2)).isoformat(),
        **extra,
    }


# ---------------------------------------------------------------------------
# Visibilité / feed
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_event_church_scope_visible_to_church_members_only():
    church = ChurchFactory()
    other = ChurchFactory()
    ev_church = _event(scope_type="church", scope_church=church)
    ev_global = _event(scope_type="global")

    member = _member_of_church(church)
    outsider = _member_of_church(other)

    member_feed = _feed_ids(member)
    assert ev_church.id in member_feed
    assert ev_global.id in member_feed

    outsider_feed = _feed_ids(outsider)
    assert ev_church.id not in outsider_feed
    assert ev_global.id in outsider_feed


@pytest.mark.django_db
def test_event_feed_aggregates_all_memberships():
    church_a = ChurchFactory()
    church_b = ChurchFactory()
    parish_a, parish_b = church_a.parish, church_b.parish
    d1, d2 = parish_a.diocese, parish_b.diocese

    user = BaseUserFactory()
    membership_create(user=user, church=church_a, is_primary=True)
    membership_create(user=user, church=church_b)

    visible = [
        _event(scope_type="church", scope_church=church_a),
        _event(scope_type="parish", scope_parish=parish_a),
        _event(scope_type="diocese", scope_diocese=d1),
        _event(scope_type="church", scope_church=church_b),
        _event(scope_type="parish", scope_parish=parish_b),
        _event(scope_type="diocese", scope_diocese=d2),
        _event(scope_type="global"),
    ]
    hidden = _event(scope_type="parish", scope_parish=ParishFactory())

    feed = _feed_ids(user)
    assert {e.id for e in visible} <= feed
    assert hidden.id not in feed


@pytest.mark.django_db
def test_non_regression_global_diocese_parish_visibility():
    church = ChurchFactory()
    parish, diocese = church.parish, church.parish.diocese
    user = _member_of_church(church)

    g = _event(scope_type="global")
    d = _event(scope_type="diocese", scope_diocese=diocese)
    p = _event(scope_type="parish", scope_parish=parish)
    other = _event(scope_type="diocese", scope_diocese=DioceseFactory())

    feed = _feed_ids(user)
    assert {g.id, d.id, p.id} <= feed
    assert other.id not in feed


# ---------------------------------------------------------------------------
# Création scope église / paroisse (résolution INT→FK) + autorité
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_event_create_with_church_scope():
    parish = ParishFactory()
    church = ChurchFactory(parish=parish)
    cure = _cure_of_parish(parish)
    now = timezone.now()

    event = event_create(
        organizer=cure,
        title="Messe église",
        event_type="mass",
        start_at=now + datetime.timedelta(days=1),
        end_at=now + datetime.timedelta(days=1, hours=1),
        scope_type="church",
        scope_church_id=church.id,
    )

    assert event.scope_type == "church"
    assert event.scope_church_id == church.id
    assert event.scope_parish_id is None


@pytest.mark.django_db
def test_event_create_parish_scope_resolves_to_fk():
    parish = ParishFactory()
    cure = _cure_of_parish(parish)
    now = timezone.now()

    event = event_create(
        organizer=cure,
        title="Messe paroisse",
        event_type="mass",
        start_at=now + datetime.timedelta(days=1),
        end_at=now + datetime.timedelta(days=1, hours=1),
        scope_type="parish",
        scope_id=parish.id,  # contrat legacy : id unique désambiguïsé par scope_type
    )

    assert event.scope_parish_id == parish.id
    assert event.scope_parish == parish


@pytest.mark.django_db
def test_event_create_church_scope_other_parish_forbidden():
    parish_a = ParishFactory()
    church_b = ChurchFactory(parish=ParishFactory())
    cure_a = _cure_of_parish(parish_a)
    now = timezone.now()

    with pytest.raises(ApplicationError):
        event_create(
            organizer=cure_a,
            title="Injection",
            event_type="mass",
            start_at=now + datetime.timedelta(days=1),
            end_at=now + datetime.timedelta(days=1, hours=1),
            scope_type="church",
            scope_church_id=church_b.id,
        )


@pytest.mark.django_db
def test_church_admin_can_publish_church_scoped_to_own_church_event():
    church = ChurchFactory()
    admin = _church_admin(church)
    now = timezone.now()

    event = event_create(
        organizer=admin,
        title="Évt église",
        event_type="mass",
        start_at=now + datetime.timedelta(days=1),
        end_at=now + datetime.timedelta(days=1, hours=1),
        scope_type="church",
        scope_church_id=church.id,
    )
    assert event.scope_church_id == church.id


@pytest.mark.django_db
def test_church_admin_cannot_publish_church_scoped_to_other_church_event():
    church_x = ChurchFactory()
    church_y = ChurchFactory()
    admin = _church_admin(church_x)
    now = timezone.now()

    with pytest.raises(ApplicationError):
        event_create(
            organizer=admin,
            title="Injection",
            event_type="mass",
            start_at=now + datetime.timedelta(days=1),
            end_at=now + datetime.timedelta(days=1, hours=1),
            scope_type="church",
            scope_church_id=church_y.id,
        )


# ---------------------------------------------------------------------------
# Garde liste des inscrits
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_event_registrations_list_requires_event_parish_authority():
    parish = ParishFactory()
    organizer = _cure_of_parish(parish)
    event = _event(scope_type="parish", scope_parish=parish, organizer=organizer)
    EventRegistration.objects.create(event=event, user=BaseUserFactory())
    url = reverse("api:agenda:event-registrations", kwargs={"event_id": event.id})

    # Un fidèle quelconque ne peut PAS lire la liste des inscrits → 403.
    outsider = APIClient()
    outsider.force_authenticate(BaseUserFactory())
    assert outsider.get(url).status_code == 403

    # Un curé de la paroisse de l'événement → 200.
    cure = APIClient()
    cure.force_authenticate(_cure_of_parish(parish))
    assert cure.get(url).status_code == 200


# ---------------------------------------------------------------------------
# Migration data — résolution / flag
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_event_migration_resolves_scope_to_fk():
    parish = ParishFactory()
    diocese = DioceseFactory()
    assert resolve_scope_fk(value=parish.id, Model=Parish) == (parish.id, False)
    assert resolve_scope_fk(value=diocese.id, Model=Diocese) == (diocese.id, False)


@pytest.mark.django_db
def test_event_migration_flags_unresolvable():
    assert resolve_scope_fk(value=999999, Model=Parish) == (None, True)
    assert resolve_scope_fk(value=None, Model=Parish) == (None, False)
