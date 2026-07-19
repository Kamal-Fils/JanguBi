"""Tests services apps/agenda — autorité pastorale, annulation douce.

Ces fonctions décident QUI peut créer et annuler un événement : elles sont testées
au niveau service (et pas seulement via l'API) parce qu'un appelant interne
(tâche Celery, commande d'administration) doit se heurter aux mêmes garde-fous.
"""

import datetime

import pytest
from django.utils import timezone

from apps.agenda.models import Event
from apps.agenda.services import can_manage_event, event_cancel, event_create, event_register
from apps.core.exceptions import ApplicationError
from apps.org.tests.factories import ChurchFactory, DioceseFactory, ParishFactory, ProvinceFactory
from apps.users.enums import PastoralRole
from apps.users.services_memberships import membership_create
from apps.users.tests.factories import BaseUserFactory


def _clergy_attached_to(church, pastoral_role):
    """Clergé « nu » : rôle pastoral + appartenance réelle, AUCUNE RoleAssignment."""
    user = BaseUserFactory(pastoral_role=pastoral_role)
    membership_create(user=user, church=church, is_primary=True)
    user.refresh_from_db()  # diocese/province sont remplis par signal via .update()
    return user


def _times():
    now = timezone.now()
    return now + datetime.timedelta(days=1), now + datetime.timedelta(days=1, hours=2)


def _create_parish_event(organizer, parish):
    start_at, end_at = _times()
    return event_create(
        organizer=organizer,
        title="Messe paroissiale",
        event_type="mass",
        start_at=start_at,
        end_at=end_at,
        scope_type="parish",
        scope_id=parish.id,
    )


# ---------------------------------------------------------------------------
# Autorité pastorale — fail-closed
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_priest_creates_on_his_own_parish():
    church = ChurchFactory()
    priest = _clergy_attached_to(church, PastoralRole.PRETRE)

    event = _create_parish_event(priest, church.parish)

    assert event.scope_parish_id == church.parish_id


@pytest.mark.django_db
def test_priest_cannot_create_on_a_foreign_parish():
    church = ChurchFactory()
    priest = _clergy_attached_to(church, PastoralRole.PRETRE)
    foreign = ParishFactory()

    with pytest.raises(ApplicationError):
        _create_parish_event(priest, foreign)


@pytest.mark.django_db
def test_priest_cannot_create_on_a_church_of_a_foreign_parish():
    church = ChurchFactory()
    priest = _clergy_attached_to(church, PastoralRole.PRETRE)
    foreign_church = ChurchFactory()
    start_at, end_at = _times()

    with pytest.raises(ApplicationError):
        event_create(
            organizer=priest, title="x", event_type="other",
            start_at=start_at, end_at=end_at,
            scope_type="church", scope_church_id=foreign_church.id,
        )


@pytest.mark.django_db
def test_priest_can_create_on_another_church_of_his_own_parish():
    church = ChurchFactory()
    sibling = ChurchFactory(parish=church.parish)
    priest = _clergy_attached_to(church, PastoralRole.PRETRE)
    start_at, end_at = _times()

    event = event_create(
        organizer=priest, title="Chapelet", event_type="other",
        start_at=start_at, end_at=end_at,
        scope_type="church", scope_church_id=sibling.id,
    )

    assert event.scope_church_id == sibling.id


@pytest.mark.django_db
def test_religieux_has_no_pastoral_organizing_authority():
    # Matrice §16 — AGENDA : le religieux ne crée pas d'événement.
    church = ChurchFactory()
    religieux = _clergy_attached_to(church, PastoralRole.RELIGIEUX)

    with pytest.raises(ApplicationError):
        _create_parish_event(religieux, church.parish)


@pytest.mark.django_db
def test_bishop_covers_his_diocese_but_not_a_foreign_one():
    church = ChurchFactory()
    bishop = _clergy_attached_to(church, PastoralRole.EVEQUE)
    foreign_diocese = DioceseFactory()
    start_at, end_at = _times()

    event = event_create(
        organizer=bishop, title="Synode", event_type="conference",
        start_at=start_at, end_at=end_at,
        scope_type="diocese", scope_id=church.parish.diocese_id,
    )

    assert event.scope_diocese_id == church.parish.diocese_id
    with pytest.raises(ApplicationError):
        event_create(
            organizer=bishop, title="Synode", event_type="conference",
            start_at=start_at, end_at=end_at,
            scope_type="diocese", scope_id=foreign_diocese.id,
        )


@pytest.mark.django_db
def test_archbishop_covers_every_diocese_of_his_province():
    province = ProvinceFactory()
    home_diocese = DioceseFactory(province=province)
    sister_diocese = DioceseFactory(province=province)
    outside_diocese = DioceseFactory()  # autre province
    church = ChurchFactory(parish=ParishFactory(diocese=home_diocese))
    archbishop = _clergy_attached_to(church, PastoralRole.ARCHEVEQUE)
    start_at, end_at = _times()

    event = event_create(
        organizer=archbishop, title="Assemblée provinciale", event_type="conference",
        start_at=start_at, end_at=end_at,
        scope_type="diocese", scope_id=sister_diocese.id,
    )

    assert event.scope_diocese_id == sister_diocese.id
    with pytest.raises(ApplicationError):
        event_create(
            organizer=archbishop, title="Hors province", event_type="conference",
            start_at=start_at, end_at=end_at,
            scope_type="diocese", scope_id=outside_diocese.id,
        )


@pytest.mark.django_db
def test_pastoral_route_never_opens_the_global_scope():
    church = ChurchFactory()
    start_at, end_at = _times()

    for role in (PastoralRole.PRETRE, PastoralRole.EVEQUE, PastoralRole.ARCHEVEQUE):
        clergy = _clergy_attached_to(ChurchFactory(parish=church.parish), role)
        with pytest.raises(ApplicationError):
            event_create(
                organizer=clergy, title="Global", event_type="other",
                start_at=start_at, end_at=end_at, scope_type="global",
            )


@pytest.mark.django_db
def test_unattached_priest_has_no_territory():
    # Fail-closed : sans appartenance, aucun territoire — donc aucun droit.
    priest = BaseUserFactory(pastoral_role=PastoralRole.PRETRE)
    parish = ParishFactory()

    with pytest.raises(ApplicationError):
        _create_parish_event(priest, parish)


# ---------------------------------------------------------------------------
# Annulation douce
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_cancel_keeps_registrations_and_queues_one_email_per_registrant():
    from apps.emails.models import Email

    church = ChurchFactory()
    priest = _clergy_attached_to(church, PastoralRole.PRETRE)
    event = _create_parish_event(priest, church.parish)
    first = BaseUserFactory()
    second = BaseUserFactory()
    event_register(event=event, user=first)
    event_register(event=event, user=second)

    event_cancel(event=event, actor=priest)

    event.refresh_from_db()
    assert event.is_cancelled
    assert event.registrations.count() == 2  # la trace de l'engagement survit
    assert Email.objects.filter(to__in=[first.email, second.email]).count() == 2


@pytest.mark.django_db
def test_cancel_refuses_a_stranger_even_when_called_directly():
    # L'invariant d'autorité vit dans le SERVICE, pas seulement dans la vue.
    church = ChurchFactory()
    priest = _clergy_attached_to(church, PastoralRole.PRETRE)
    event = _create_parish_event(priest, church.parish)
    stranger = _clergy_attached_to(ChurchFactory(), PastoralRole.PRETRE)

    with pytest.raises(ApplicationError):
        event_cancel(event=event, actor=stranger)

    event.refresh_from_db()
    assert not event.is_cancelled


@pytest.mark.django_db
def test_cancel_is_not_repeatable():
    church = ChurchFactory()
    priest = _clergy_attached_to(church, PastoralRole.PRETRE)
    event = _create_parish_event(priest, church.parish)
    event_cancel(event=event, actor=priest)

    with pytest.raises(ApplicationError):
        event_cancel(event=event, actor=priest)


@pytest.mark.django_db
def test_registration_is_closed_on_a_cancelled_event():
    church = ChurchFactory()
    priest = _clergy_attached_to(church, PastoralRole.PRETRE)
    event = _create_parish_event(priest, church.parish)
    event_cancel(event=event, actor=priest)

    with pytest.raises(ApplicationError):
        event_register(event=event, user=BaseUserFactory())


@pytest.mark.django_db
def test_diocesan_authority_can_cancel_a_parish_event():
    church = ChurchFactory()
    priest = _clergy_attached_to(church, PastoralRole.PRETRE)
    event = _create_parish_event(priest, church.parish)
    bishop = _clergy_attached_to(church, PastoralRole.EVEQUE)

    assert can_manage_event(user=bishop, event=event) is True
    event_cancel(event=event, actor=bishop)

    event.refresh_from_db()
    assert event.cancelled_by_id == bishop.id


@pytest.mark.django_db
def test_cancelled_event_is_out_of_the_feed_but_still_readable():
    from apps.agenda.selectors import event_get, event_list_for_user

    church = ChurchFactory()
    priest = _clergy_attached_to(church, PastoralRole.PRETRE)
    event = _create_parish_event(priest, church.parish)
    event_cancel(event=event, actor=priest)

    assert event.pk not in [e.pk for e in event_list_for_user(user=priest)]
    assert event_get(event_id=event.pk).pk == event.pk  # lien profond préservé


@pytest.mark.django_db
def test_event_create_still_rejects_an_end_before_start():
    church = ChurchFactory()
    priest = _clergy_attached_to(church, PastoralRole.PRETRE)
    start_at, _ = _times()

    with pytest.raises(ApplicationError):
        event_create(
            organizer=priest, title="Incohérent", event_type="other",
            start_at=start_at, end_at=start_at - datetime.timedelta(hours=1),
            scope_type="parish", scope_id=church.parish_id,
        )


@pytest.mark.django_db
def test_event_model_reports_cancellation():
    event = Event(title="x", event_type="other", start_at=timezone.now(), end_at=timezone.now())
    assert event.is_cancelled is False
    event.cancelled_at = timezone.now()
    assert event.is_cancelled is True
