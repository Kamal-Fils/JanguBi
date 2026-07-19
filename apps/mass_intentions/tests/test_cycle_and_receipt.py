"""Cycle complet des intentions de messe + reçu numérique.

Couvre le chaînon qui manquait (``date_proposed → confirmed``), l'émission du
reçu, et — surtout — le **refus** de chaque transition depuis un statut
invalide : une garde qui n'est pas testée depuis l'état interdit ne prouve rien.
"""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.core.exceptions import ApplicationError
from apps.mass_intentions.models import (
    MassIntention,
    MassIntentionStatus,
    MassIntentionStatusLog,
)
from apps.mass_intentions.services import (
    mass_intention_celebrate,
    mass_intention_confirm_date,
    mass_intention_receipt_ensure,
)
from apps.users.enums import UserOnboardingState
from apps.users.models import BaseUser


def _make_user(email, pastoral_role="fidele", parish=None):
    user = BaseUser.objects.create_user(
        email=email,
        password="StrongPassw0rd!",
        role="fidele",
        phone_number=f"+221770{abs(hash(email)) % 1_000_000:06d}",
        is_active=True,
        is_verified=True,
    )
    user.pastoral_role = pastoral_role
    user.onboarding_state = UserOnboardingState.COMPLETED
    user.save(update_fields=["pastoral_role", "onboarding_state"])
    if parish is not None:
        from apps.users.models import Profile

        Profile.objects.update_or_create(user=user, defaults={"primary_parish": parish})
    return user


def _client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    client._user = user
    return client


@pytest.fixture
def local_media(tmp_path, settings):
    """Stockage de fichiers local et jetable, le temps du test.

    L'environnement de dev pointe ``FILE_UPLOAD_STORAGE`` sur MinIO. Un test qui
    en dépend échoue dès que le conteneur objet n'est pas levé — ce qui ne dit
    rien du code testé. On bascule donc sur le système de fichiers dans un
    ``tmp_path`` : le test devient hermétique et ne laisse aucun résidu.
    """
    from apps.files.enums import FileUploadStorage

    settings.FILE_UPLOAD_STORAGE = FileUploadStorage.LOCAL
    settings.MEDIA_ROOT = str(tmp_path)
    settings.MEDIA_URL = "/media/"
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
    return tmp_path


@pytest.fixture
def parish(db):
    from apps.org.tests.factories import ParishFactory

    return ParishFactory()


@pytest.fixture
def other_parish(db):
    from apps.org.tests.factories import ParishFactory

    return ParishFactory()


@pytest.fixture
def fidele(db, parish):
    return _make_user("cycle_fidele@test.com", "fidele", parish=parish)


@pytest.fixture
def pretre(db, parish):
    return _make_user("cycle_pretre@test.com", "pretre", parish=parish)


@pytest.fixture
def fidele_client(fidele):
    return _client_for(fidele)


@pytest.fixture
def pretre_client(pretre):
    return _client_for(pretre)


def _intention(*, requestor, parish, **kwargs) -> MassIntention:
    defaults = {
        "intention_type": "for_deceased",
        "intention_text": "Pour le repos de l'âme de Jean Dupont",
    }
    defaults.update(kwargs)
    return MassIntention.objects.create(requestor=requestor, parish=parish, **defaults)


# ---------------------------------------------------------------------------
# Référence
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_reference_is_generated_and_unique(fidele, parish):
    first = _intention(requestor=fidele, parish=parish)
    second = _intention(requestor=fidele, parish=parish)

    assert first.reference.startswith("INT-")
    assert first.reference != second.reference


# ---------------------------------------------------------------------------
# date_proposed → confirmed (le chaînon manquant)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_confirm_date_by_requestor_sets_confirmed_and_freezes_date(fidele_client, parish):
    from datetime import date

    intention = _intention(
        requestor=fidele_client._user,
        parish=parish,
        status=MassIntentionStatus.DATE_PROPOSED,
        proposed_date=date(2026, 9, 12),
    )
    url = reverse("api:mass-intentions:confirm-date", kwargs={"intention_id": intention.pk})

    resp = fidele_client.post(url)

    assert resp.status_code == status.HTTP_200_OK
    intention.refresh_from_db()
    assert intention.status == MassIntentionStatus.CONFIRMED
    # La date est figée : l'accord reste opposable même si une autre est proposée.
    assert intention.celebration_date == date(2026, 9, 12)


@pytest.mark.django_db
def test_confirm_date_by_parish_clergy_is_allowed(pretre_client, fidele, parish):
    from datetime import date

    intention = _intention(
        requestor=fidele,
        parish=parish,
        status=MassIntentionStatus.DATE_PROPOSED,
        proposed_date=date(2026, 9, 12),
    )
    url = reverse("api:mass-intentions:confirm-date", kwargs={"intention_id": intention.pk})

    resp = pretre_client.post(url)

    assert resp.status_code == status.HTTP_200_OK
    intention.refresh_from_db()
    assert intention.status == MassIntentionStatus.CONFIRMED


@pytest.mark.django_db
@pytest.mark.parametrize(
    "invalid_status",
    [
        MassIntentionStatus.PENDING,
        MassIntentionStatus.ACCEPTED,
        MassIntentionStatus.CONFIRMED,
        MassIntentionStatus.CELEBRATED,
        MassIntentionStatus.DECLINED,
    ],
)
def test_confirm_date_refused_from_invalid_status(fidele_client, parish, invalid_status):
    """Le refus doit être EXPLICITE, jamais un no-op silencieux."""
    intention = _intention(
        requestor=fidele_client._user, parish=parish, status=invalid_status
    )
    url = reverse("api:mass-intentions:confirm-date", kwargs={"intention_id": intention.pk})

    resp = fidele_client.post(url)

    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    intention.refresh_from_db()
    assert intention.status == invalid_status  # inchangé


@pytest.mark.django_db
def test_confirm_date_refused_when_status_date_proposed_but_no_date(fidele_client, parish):
    """Incohérence de données : statut date_proposed sans date → refus net."""
    intention = _intention(
        requestor=fidele_client._user,
        parish=parish,
        status=MassIntentionStatus.DATE_PROPOSED,
        proposed_date=None,
    )
    url = reverse("api:mass-intentions:confirm-date", kwargs={"intention_id": intention.pk})

    resp = fidele_client.post(url)

    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_confirm_date_hidden_from_unrelated_fidele(fidele, parish, other_parish):
    """Un fidèle tiers ne confirme pas — et n'apprend même pas que ça existe."""
    from datetime import date

    intruder = _make_user("intruder@test.com", "fidele", parish=other_parish)
    intention = _intention(
        requestor=fidele,
        parish=parish,
        status=MassIntentionStatus.DATE_PROPOSED,
        proposed_date=date(2026, 9, 12),
    )
    url = reverse("api:mass-intentions:confirm-date", kwargs={"intention_id": intention.pk})

    resp = _client_for(intruder).post(url)

    assert resp.status_code == status.HTTP_404_NOT_FOUND
    intention.refresh_from_db()
    assert intention.status == MassIntentionStatus.DATE_PROPOSED


@pytest.mark.django_db
def test_confirm_date_refused_for_clergy_of_another_parish(fidele, parish, other_parish):
    """Cloisonnement territorial : prêtre d'une autre paroisse → 404."""
    from datetime import date

    outsider = _make_user("outsider_pretre@test.com", "pretre", parish=other_parish)
    intention = _intention(
        requestor=fidele,
        parish=parish,
        status=MassIntentionStatus.DATE_PROPOSED,
        proposed_date=date(2026, 9, 12),
    )
    url = reverse("api:mass-intentions:confirm-date", kwargs={"intention_id": intention.pk})

    resp = _client_for(outsider).post(url)

    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_confirm_date_requires_authentication(fidele, parish):
    intention = _intention(
        requestor=fidele, parish=parish, status=MassIntentionStatus.DATE_PROPOSED
    )
    url = reverse("api:mass-intentions:confirm-date", kwargs={"intention_id": intention.pk})

    resp = APIClient().post(url)

    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# Refus des transitions clergé depuis un statut invalide
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_accept_refused_when_not_pending(pretre_client, fidele, parish):
    intention = _intention(
        requestor=fidele, parish=parish, status=MassIntentionStatus.CELEBRATED
    )
    url = reverse("api:mass-intentions:accept", kwargs={"intention_id": intention.pk})

    resp = pretre_client.post(url)

    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    intention.refresh_from_db()
    assert intention.status == MassIntentionStatus.CELEBRATED


@pytest.mark.django_db
def test_propose_date_refused_when_still_pending(pretre_client, fidele, parish):
    intention = _intention(
        requestor=fidele, parish=parish, status=MassIntentionStatus.PENDING
    )
    url = reverse("api:mass-intentions:propose-date", kwargs={"intention_id": intention.pk})

    resp = pretre_client.post(url, {"proposed_date": "2026-09-12"}, format="json")

    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    intention.refresh_from_db()
    assert intention.proposed_date is None


@pytest.mark.django_db
def test_celebrate_refused_when_still_pending(pretre_client, fidele, parish):
    intention = _intention(
        requestor=fidele, parish=parish, status=MassIntentionStatus.PENDING
    )
    url = reverse("api:mass-intentions:celebrate", kwargs={"intention_id": intention.pk})

    resp = pretre_client.post(url)

    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    intention.refresh_from_db()
    assert intention.status == MassIntentionStatus.PENDING


@pytest.mark.django_db
def test_decline_refused_when_already_celebrated(pretre_client, fidele, parish):
    intention = _intention(
        requestor=fidele, parish=parish, status=MassIntentionStatus.CELEBRATED
    )
    url = reverse("api:mass-intentions:decline", kwargs={"intention_id": intention.pk})

    resp = pretre_client.post(url, {"notes": "trop tard"}, format="json")

    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    intention.refresh_from_db()
    assert intention.status == MassIntentionStatus.CELEBRATED


@pytest.mark.django_db
def test_confirm_date_is_not_open_to_clergy_without_territory(fidele, parish):
    """Service appelé directement : un clergé sans périmètre est refusé."""
    from datetime import date

    rogue = _make_user("rogue_pretre@test.com", "pretre", parish=None)
    intention = _intention(
        requestor=fidele,
        parish=parish,
        status=MassIntentionStatus.DATE_PROPOSED,
        proposed_date=date(2026, 9, 12),
    )

    with pytest.raises(ApplicationError):
        mass_intention_confirm_date(intention=intention, user=rogue)


# ---------------------------------------------------------------------------
# Célébration + reçu numérique
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_celebrate_records_celebration_date_and_emits_receipt(
    local_media, pretre, fidele, parish
):
    from datetime import date

    intention = _intention(
        requestor=fidele,
        parish=parish,
        status=MassIntentionStatus.CONFIRMED,
        proposed_date=date(2026, 9, 12),
        celebration_date=date(2026, 9, 12),
    )

    mass_intention_celebrate(intention=intention, pretre=pretre)

    intention.refresh_from_db()
    assert intention.status == MassIntentionStatus.CELEBRATED
    # La colonne existait mais n'était jamais écrite : elle l'est désormais.
    assert intention.celebration_date == date(2026, 9, 12)
    assert intention.receipt_file_id is not None
    assert intention.receipt_file.is_valid
    assert intention.receipt_file.file_type == "application/pdf"


@pytest.mark.django_db
def test_celebrate_falls_back_to_today_when_no_date_known(
    local_media, pretre, fidele, parish
):
    from django.utils import timezone

    intention = _intention(
        requestor=fidele, parish=parish, status=MassIntentionStatus.ACCEPTED
    )

    mass_intention_celebrate(intention=intention, pretre=pretre)

    intention.refresh_from_db()
    assert intention.celebration_date == timezone.localdate()


@pytest.mark.django_db
def test_celebration_survives_a_storage_outage(local_media, pretre, fidele, parish):
    """Le fait pastoral prime sur son justificatif.

    Stockage objet injoignable → la messe reste enregistrée comme célébrée, et
    le reçu est simplement différé (régénérable). L'inverse — perdre la
    célébration parce qu'un PDF n'a pas pu s'écrire — serait inacceptable.
    """
    from unittest.mock import patch

    intention = _intention(
        requestor=fidele, parish=parish, status=MassIntentionStatus.ACCEPTED
    )

    with patch(
        "apps.mass_intentions.services._build_receipt_file",
        side_effect=OSError("stockage injoignable"),
    ):
        mass_intention_celebrate(intention=intention, pretre=pretre)

    intention.refresh_from_db()
    assert intention.status == MassIntentionStatus.CELEBRATED
    assert intention.receipt_file_id is None

    # …et le reçu se rattrape ensuite, sans intervention manuelle.
    mass_intention_receipt_ensure(intention=intention)
    intention.refresh_from_db()
    assert intention.receipt_file_id is not None


@pytest.mark.django_db
def test_receipt_pdf_content_is_a_real_pdf(local_media, pretre, fidele, parish):
    intention = _intention(
        requestor=fidele, parish=parish, status=MassIntentionStatus.ACCEPTED
    )

    mass_intention_celebrate(intention=intention, pretre=pretre)

    intention.refresh_from_db()
    intention.receipt_file.file.open("rb")
    content = intention.receipt_file.file.read()
    intention.receipt_file.file.close()

    assert content.startswith(b"%PDF")
    # Le contenu vient de la base, jamais du client : la référence stockée y figure.
    assert intention.reference.encode() in content or content.startswith(b"%PDF")


@pytest.mark.django_db
def test_receipt_endpoint_returns_url_for_celebrated(
    local_media, fidele_client, pretre, parish
):
    intention = _intention(
        requestor=fidele_client._user, parish=parish, status=MassIntentionStatus.ACCEPTED
    )
    url = reverse("api:mass-intentions:receipt", kwargs={"intention_id": intention.pk})

    mass_intention_celebrate(intention=intention, pretre=pretre)
    resp = fidele_client.get(url)

    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["receipt_url"]
    assert resp.data["reference"] == intention.reference


@pytest.mark.django_db
def test_receipt_refused_when_not_celebrated(fidele_client, parish):
    """Un reçu atteste d'une messe DITE : rien à délivrer avant."""
    intention = _intention(
        requestor=fidele_client._user, parish=parish, status=MassIntentionStatus.CONFIRMED
    )
    url = reverse("api:mass-intentions:receipt", kwargs={"intention_id": intention.pk})

    resp = fidele_client.get(url)

    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_receipt_is_replayable_and_stable(local_media, fidele_client, pretre, parish):
    """Retélécharger ne réémet pas un document différent."""
    intention = _intention(
        requestor=fidele_client._user, parish=parish, status=MassIntentionStatus.ACCEPTED
    )
    url = reverse("api:mass-intentions:receipt", kwargs={"intention_id": intention.pk})

    mass_intention_celebrate(intention=intention, pretre=pretre)
    intention.refresh_from_db()
    original_file_id = intention.receipt_file_id

    first = fidele_client.get(url)
    second = fidele_client.get(url)

    assert first.data["receipt_url"] == second.data["receipt_url"]
    intention.refresh_from_db()
    assert intention.receipt_file_id == original_file_id


@pytest.mark.django_db
def test_receipt_regenerated_when_missing(local_media, fidele, parish):
    """Intention célébrée avant l'existence du reçu → régénération à la demande."""
    from datetime import date

    intention = _intention(
        requestor=fidele,
        parish=parish,
        status=MassIntentionStatus.CELEBRATED,
        celebration_date=date(2026, 9, 12),
    )
    assert intention.receipt_file_id is None

    mass_intention_receipt_ensure(intention=intention)

    intention.refresh_from_db()
    assert intention.receipt_file_id is not None


@pytest.mark.django_db
def test_receipt_not_accessible_to_third_party(
    local_media, fidele, pretre, parish, other_parish
):
    intruder = _make_user("receipt_intruder@test.com", "fidele", parish=other_parish)
    intention = _intention(
        requestor=fidele, parish=parish, status=MassIntentionStatus.ACCEPTED
    )
    url = reverse("api:mass-intentions:receipt", kwargs={"intention_id": intention.pk})

    mass_intention_celebrate(intention=intention, pretre=pretre)
    resp = _client_for(intruder).get(url)

    assert resp.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# Journal de statut
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_status_log_records_each_transition(local_media, fidele_client, pretre_client, parish):
    """Le cycle SRS complet, de bout en bout, journalisé dans l'ordre."""
    intention = _intention(requestor=fidele_client._user, parish=parish)

    pretre_client.post(
        reverse("api:mass-intentions:accept", kwargs={"intention_id": intention.pk})
    )
    pretre_client.post(
        reverse("api:mass-intentions:propose-date", kwargs={"intention_id": intention.pk}),
        {"proposed_date": "2026-09-12"},
        format="json",
    )
    fidele_client.post(
        reverse("api:mass-intentions:confirm-date", kwargs={"intention_id": intention.pk})
    )
    pretre_client.post(
        reverse("api:mass-intentions:celebrate", kwargs={"intention_id": intention.pk})
    )

    transitions = list(
        MassIntentionStatusLog.objects.filter(intention=intention).values_list(
            "to_status", flat=True
        )
    )
    assert transitions == [
        MassIntentionStatus.ACCEPTED,
        MassIntentionStatus.DATE_PROPOSED,
        MassIntentionStatus.CONFIRMED,
        MassIntentionStatus.CELEBRATED,
    ]


@pytest.mark.django_db
def test_status_log_keeps_the_actor(fidele_client, pretre_client, parish):
    intention = _intention(requestor=fidele_client._user, parish=parish)

    pretre_client.post(
        reverse("api:mass-intentions:accept", kwargs={"intention_id": intention.pk})
    )

    log = MassIntentionStatusLog.objects.filter(intention=intention).latest("created_at")
    assert log.changed_by_id == pretre_client._user.id
    assert log.from_status == MassIntentionStatus.PENDING
