"""Tests API apps/spiritual — /api/v1/spiritual/reflections/* (fix du 404 live)."""

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.org.tests.factories import ChurchFactory, ParishFactory
from apps.spiritual.models import PastoralReflection
from apps.users.enums import PastoralRole, RoleScope, UserRole
from apps.users.models import RoleAssignment
from apps.users.services_memberships import membership_create
from apps.users.tests.factories import BaseUserFactory

TODAY_URL = "/api/v1/spiritual/reflections/today/"
LIST_URL = "/api/v1/spiritual/reflections/"


def _parish_priest(parish):
    user = BaseUserFactory(pastoral_role=PastoralRole.PRETRE)
    RoleAssignment.objects.create(
        user=user, role=UserRole.PARISH_ADMIN, scope=RoleScope.PARISH,
        parish=parish, is_active=True,
    )
    return user


@pytest.mark.django_db
def test_today_route_exists_and_returns_200_null_when_none():
    client = APIClient()
    client.force_authenticate(user=BaseUserFactory())

    resp = client.get(TODAY_URL)

    # Avant ce fix : 404 (route absente). Désormais : 200 + null si aucune réflexion.
    assert resp.status_code == 200
    assert resp.data is None


@pytest.mark.django_db
def test_today_returns_parish_reflection_for_member():
    church = ChurchFactory()
    parish = church.parish
    priest = _parish_priest(parish)
    PastoralReflection.objects.create(
        author=priest, reflection_date=timezone.localdate(),
        content="Paix et joie.", scope_type="parish", scope_parish=parish,
    )
    fidele = BaseUserFactory()
    membership_create(user=fidele, church=church, is_primary=True)

    client = APIClient()
    client.force_authenticate(user=fidele)
    resp = client.get(TODAY_URL)

    assert resp.status_code == 200
    assert resp.data["content"] == "Paix et joie."


@pytest.mark.django_db
def test_post_create_forbidden_for_fidele():
    parish = ParishFactory()
    client = APIClient()
    client.force_authenticate(user=BaseUserFactory())

    resp = client.post(
        LIST_URL,
        {"content": "x", "scope_type": "parish", "scope_parish_id": parish.id},
        format="json",
    )

    assert resp.status_code == 403


@pytest.mark.django_db
def test_post_create_succeeds_for_priest():
    parish = ParishFactory()
    priest = _parish_priest(parish)
    client = APIClient()
    client.force_authenticate(user=priest)

    resp = client.post(
        LIST_URL,
        {"content": "Aimez-vous les uns les autres.", "scope_type": "parish", "scope_parish_id": parish.id},
        format="json",
    )

    assert resp.status_code == 201
    assert resp.data["content"] == "Aimez-vous les uns les autres."
    assert resp.data["scope_parish_id"] == parish.id


@pytest.mark.django_db
def test_my_today_returns_authors_own():
    parish = ParishFactory()
    priest = _parish_priest(parish)
    PastoralReflection.objects.create(
        author=priest, reflection_date=timezone.localdate(),
        content="Ma méditation.", scope_type="parish", scope_parish=parish,
    )

    client = APIClient()
    client.force_authenticate(user=priest)
    resp = client.get("/api/v1/spiritual/reflections/my-today/")

    assert resp.status_code == 200
    assert resp.data["content"] == "Ma méditation."


# ---------------------------------------------------------------------------
# Édition d'une réflexion existante (PATCH) — le front l'appelait, 405 en face.
# ---------------------------------------------------------------------------

def _detail_url(reflection):
    return f"/api/v1/spiritual/reflections/{reflection.id}/"


@pytest.mark.django_db
def test_patch_by_author_updates_content():
    parish = ParishFactory()
    priest = _parish_priest(parish)
    reflection = PastoralReflection.objects.create(
        author=priest, reflection_date=timezone.localdate(),
        content="Version 1", scope_type="parish", scope_parish=parish,
    )
    client = APIClient()
    client.force_authenticate(user=priest)

    resp = client.patch(_detail_url(reflection), {"content": "Version 2"}, format="json")

    assert resp.status_code == 200
    assert resp.data["content"] == "Version 2"
    reflection.refresh_from_db()
    assert reflection.content == "Version 2"


@pytest.mark.django_db
def test_patch_leaves_untouched_fields_intact():
    parish = ParishFactory()
    priest = _parish_priest(parish)
    reflection = PastoralReflection.objects.create(
        author=priest, reflection_date=timezone.localdate(),
        title="Titre d'origine", content="Contenu",
        scope_type="parish", scope_parish=parish,
    )
    client = APIClient()
    client.force_authenticate(user=priest)

    resp = client.patch(_detail_url(reflection), {"content": "Nouveau"}, format="json")

    assert resp.status_code == 200
    reflection.refresh_from_db()
    assert reflection.title == "Titre d'origine"
    assert reflection.scope_parish_id == parish.id


@pytest.mark.django_db
def test_patch_by_stranger_is_refused():
    parish = ParishFactory()
    priest = _parish_priest(parish)
    reflection = PastoralReflection.objects.create(
        author=priest, reflection_date=timezone.localdate(),
        content="Intouchable", scope_type="parish", scope_parish=parish,
    )
    other_priest = _parish_priest(ParishFactory())  # autorité sur une AUTRE paroisse
    client = APIClient()
    client.force_authenticate(user=other_priest)

    resp = client.patch(_detail_url(reflection), {"content": "piraté"}, format="json")

    assert resp.status_code == 400
    reflection.refresh_from_db()
    assert reflection.content == "Intouchable"


@pytest.mark.django_db
def test_patch_by_diocesan_authority_allowed():
    # Modération descendante (matrice §16) : l'évêque du diocèse peut corriger une
    # réflexion publiée sur une paroisse de SON diocèse.
    parish = ParishFactory()
    priest = _parish_priest(parish)
    reflection = PastoralReflection.objects.create(
        author=priest, reflection_date=timezone.localdate(),
        content="À corriger", scope_type="parish", scope_parish=parish,
    )
    bishop = BaseUserFactory(pastoral_role=PastoralRole.EVEQUE)
    RoleAssignment.objects.create(
        user=bishop, role=UserRole.DIOCESE_ADMIN, scope=RoleScope.DIOCESE,
        diocese=parish.diocese, is_active=True,
    )
    client = APIClient()
    client.force_authenticate(user=bishop)

    resp = client.patch(_detail_url(reflection), {"content": "Corrigé"}, format="json")

    assert resp.status_code == 200
    reflection.refresh_from_db()
    assert reflection.content == "Corrigé"


@pytest.mark.django_db
def test_patch_cannot_move_reflection_to_a_foreign_parish():
    # Fail-closed : changer la portée exige l'autorité sur la NOUVELLE portée.
    parish = ParishFactory()
    foreign = ParishFactory()
    priest = _parish_priest(parish)
    reflection = PastoralReflection.objects.create(
        author=priest, reflection_date=timezone.localdate(),
        content="Chez moi", scope_type="parish", scope_parish=parish,
    )
    client = APIClient()
    client.force_authenticate(user=priest)

    resp = client.patch(
        _detail_url(reflection),
        {"scope_type": "parish", "scope_parish_id": foreign.id},
        format="json",
    )

    assert resp.status_code == 400
    reflection.refresh_from_db()
    assert reflection.scope_parish_id == parish.id


@pytest.mark.django_db
def test_patch_rejects_empty_content():
    parish = ParishFactory()
    priest = _parish_priest(parish)
    reflection = PastoralReflection.objects.create(
        author=priest, reflection_date=timezone.localdate(),
        content="Contenu", scope_type="parish", scope_parish=parish,
    )
    client = APIClient()
    client.force_authenticate(user=priest)

    resp = client.patch(_detail_url(reflection), {"content": "   "}, format="json")

    assert resp.status_code == 400
    reflection.refresh_from_db()
    assert reflection.content == "Contenu"


@pytest.mark.django_db
def test_patch_unknown_reflection_404():
    import uuid

    parish = ParishFactory()
    client = APIClient()
    client.force_authenticate(user=_parish_priest(parish))

    resp = client.patch(
        f"/api/v1/spiritual/reflections/{uuid.uuid4()}/", {"content": "x"}, format="json"
    )

    assert resp.status_code == 404


@pytest.mark.django_db
def test_patch_scope_change_clears_the_previous_level_fk():
    # Une réflexion qui monte au diocèse ne doit pas garder de scope_parish
    # résiduel : elle continuerait sinon d'apparaître dans le feed d'une paroisse.
    from apps.org.tests.factories import DioceseFactory

    diocese = DioceseFactory()
    parish = ParishFactory(diocese=diocese)
    priest = _parish_priest(parish)
    reflection = PastoralReflection.objects.create(
        author=priest, reflection_date=timezone.localdate(),
        content="Portée paroisse", scope_type="parish", scope_parish=parish,
    )
    bishop = BaseUserFactory(pastoral_role=PastoralRole.EVEQUE)
    RoleAssignment.objects.create(
        user=bishop, role=UserRole.DIOCESE_ADMIN, scope=RoleScope.DIOCESE,
        diocese=diocese, is_active=True,
    )
    client = APIClient()
    client.force_authenticate(user=bishop)

    resp = client.patch(
        _detail_url(reflection),
        # Le client renvoie l'ancien scope_parish_id en plus du nouveau niveau.
        {"scope_type": "diocese", "scope_diocese_id": diocese.id, "scope_parish_id": parish.id},
        format="json",
    )

    assert resp.status_code == 200
    reflection.refresh_from_db()
    assert reflection.scope_type == "diocese"
    assert reflection.scope_diocese_id == diocese.id
    assert reflection.scope_parish_id is None
