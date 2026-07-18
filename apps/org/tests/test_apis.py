import pytest
from rest_framework.test import APIClient

from apps.org.tests.factories import (
    ChurchFactory,
    DeaneryFactory,
    DioceseFactory,
    ParishFactory,
    ProvinceFactory,
)
from apps.users.tests.factories import BaseUserFactory, SuperAdminFactory


@pytest.fixture
def auth_client():
    client = APIClient()
    user = BaseUserFactory()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def admin_client():
    client = APIClient()
    user = SuperAdminFactory()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_province_list_authenticated(auth_client):
    ProvinceFactory.create_batch(3)
    response = auth_client.get("/api/v1/org/provinces/")
    assert response.status_code == 200
    # Enveloppe paginée {count, results} (le front get-provinces.ts déballe .results).
    assert response.data["count"] == 3
    assert len(response.data["results"]) == 3


@pytest.mark.django_db
def test_province_list_requires_auth():
    ProvinceFactory()
    client = APIClient()
    response = client.get("/api/v1/org/provinces/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_province_create_super_admin(admin_client):
    response = admin_client.post(
        "/api/v1/org/provinces/",
        {"name": "Dakar", "code": "DAK"},
        format="json",
    )
    assert response.status_code == 201
    assert response.data["name"] == "Dakar"


@pytest.mark.django_db
def test_province_create_forbidden_for_fidele(auth_client):
    response = auth_client.post(
        "/api/v1/org/provinces/",
        {"name": "Dakar", "code": "DAK"},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_diocese_list_filtered_by_province(auth_client):
    province = ProvinceFactory()
    DioceseFactory(province=province)
    DioceseFactory()  # autre province
    response = auth_client.get(f"/api/v1/org/dioceses/?province={province.id}")
    assert response.status_code == 200
    # Réponse paginée {count, results} (cohérence avec parishes) — PAS une liste nue.
    assert response.data["count"] == 1
    assert len(response.data["results"]) == 1


@pytest.mark.django_db
def test_diocese_list_returns_paginated_envelope(auth_client):
    # Anti-régression Flux 1 : le front (get-dioceses.ts) déballe `.results` et lit
    # la FK sous la clé `province`. Une liste nue casserait la cascade.
    DioceseFactory.create_batch(2)
    response = auth_client.get("/api/v1/org/dioceses/")
    assert response.status_code == 200
    assert {"count", "results"}.issubset(response.data.keys())
    assert response.data["count"] == 2
    assert "province" in response.data["results"][0]


@pytest.mark.django_db
def test_church_list_returns_paginated_envelope(auth_client):
    # Anti-régression Flux 1 : idem côté églises (get-churches.ts déballe `.results`).
    parish = ParishFactory()
    ChurchFactory.create_batch(2, parish=parish)
    response = auth_client.get(f"/api/v1/org/churches/?parish={parish.id}")
    assert response.status_code == 200
    assert {"count", "results"}.issubset(response.data.keys())
    assert response.data["count"] == 2
    assert "parish" in response.data["results"][0]


@pytest.mark.django_db
def test_parish_list_with_search(auth_client):
    diocese = DioceseFactory()
    ParishFactory(name="Cathédrale Saint-Joseph", diocese=diocese, city="Dakar")
    ParishFactory(name="Sainte-Marie", diocese=diocese, city="Thiès")
    response = auth_client.get("/api/v1/org/parishes/?search=Joseph")
    assert response.status_code == 200
    assert response.data["count"] == 1


@pytest.mark.django_db
def test_parish_detail(auth_client):
    parish = ParishFactory()
    response = auth_client.get(f"/api/v1/org/parishes/{parish.id}/")
    assert response.status_code == 200
    assert response.data["id"] == parish.id


@pytest.mark.django_db
def test_parish_update_super_admin(admin_client):
    parish = ParishFactory(name="Ancien nom", city="Dakar")
    response = admin_client.patch(
        f"/api/v1/org/parishes/{parish.id}/",
        {"name": "Nouveau nom", "city": "Thiès"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["name"] == "Nouveau nom"
    assert response.data["city"] == "Thiès"
    parish.refresh_from_db()
    assert parish.name == "Nouveau nom"


@pytest.mark.django_db
def test_parish_update_forbidden_for_fidele(auth_client):
    parish = ParishFactory()
    response = auth_client.patch(
        f"/api/v1/org/parishes/{parish.id}/", {"name": "X"}, format="json"
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_parish_delete_super_admin(admin_client):
    parish = ParishFactory()  # paroisse vide (la factory ne crée pas d'église)
    response = admin_client.delete(f"/api/v1/org/parishes/{parish.id}/")
    assert response.status_code == 204
    from apps.org.models import Parish

    assert not Parish.objects.filter(id=parish.id).exists()


@pytest.mark.django_db
def test_parish_delete_blocked_by_membership(admin_client):
    # Une paroisse avec une appartenance ne peut pas être supprimée (intégrité).
    parish = ParishFactory()
    church = ChurchFactory(parish=parish)
    from apps.users.models import Membership

    Membership.objects.create(user=BaseUserFactory(), church=church, is_primary=True)

    response = admin_client.delete(f"/api/v1/org/parishes/{parish.id}/")

    assert response.status_code == 400
    from apps.org.models import Parish

    assert Parish.objects.filter(id=parish.id).exists()


# ---------------------------------------------------------------------------
# Provinces — détail / update / delete
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_province_detail(auth_client):
    province = ProvinceFactory()
    response = auth_client.get(f"/api/v1/org/provinces/{province.id}/")
    assert response.status_code == 200
    assert response.data["id"] == province.id


@pytest.mark.django_db
def test_province_detail_404(auth_client):
    response = auth_client.get("/api/v1/org/provinces/999999/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_province_patch_partial_super_admin(admin_client):
    province = ProvinceFactory(name="Ancien nom", code="ANC")
    response = admin_client.patch(
        f"/api/v1/org/provinces/{province.id}/",
        {"name": "Nouveau nom"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["name"] == "Nouveau nom"
    province.refresh_from_db()
    assert province.name == "Nouveau nom"
    assert province.code == "ANC"  # PATCH partiel : le code n'est pas touché


@pytest.mark.django_db
def test_province_patch_forbidden_for_fidele(auth_client):
    province = ProvinceFactory()
    response = auth_client.patch(
        f"/api/v1/org/provinces/{province.id}/", {"name": "X"}, format="json"
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_province_patch_404(admin_client):
    response = admin_client.patch(
        "/api/v1/org/provinces/999999/", {"name": "X"}, format="json"
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_province_delete_super_admin(admin_client):
    province = ProvinceFactory()
    response = admin_client.delete(f"/api/v1/org/provinces/{province.id}/")
    assert response.status_code == 204
    from apps.org.models import Province

    assert not Province.objects.filter(id=province.id).exists()


@pytest.mark.django_db
def test_province_delete_forbidden_for_fidele(auth_client):
    province = ProvinceFactory()
    response = auth_client.delete(f"/api/v1/org/provinces/{province.id}/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_province_delete_blocked_by_dioceses(admin_client):
    province = ProvinceFactory()
    DioceseFactory(province=province)

    response = admin_client.delete(f"/api/v1/org/provinces/{province.id}/")

    assert response.status_code == 400
    from apps.org.models import Province

    assert Province.objects.filter(id=province.id).exists()


# ---------------------------------------------------------------------------
# Diocèses — détail / update / delete
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_diocese_detail(auth_client):
    diocese = DioceseFactory()
    response = auth_client.get(f"/api/v1/org/dioceses/{diocese.id}/")
    assert response.status_code == 200
    assert response.data["id"] == diocese.id
    assert "province_name" in response.data


@pytest.mark.django_db
def test_diocese_detail_404(auth_client):
    response = auth_client.get("/api/v1/org/dioceses/999999/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_diocese_patch_partial_super_admin(admin_client):
    diocese = DioceseFactory(name="Ancien nom", code="AND")
    response = admin_client.patch(
        f"/api/v1/org/dioceses/{diocese.id}/",
        {"name": "Nouveau nom"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["name"] == "Nouveau nom"
    diocese.refresh_from_db()
    assert diocese.code == "AND"  # PATCH partiel


@pytest.mark.django_db
def test_diocese_patch_forbidden_for_fidele(auth_client):
    diocese = DioceseFactory()
    response = auth_client.patch(
        f"/api/v1/org/dioceses/{diocese.id}/", {"name": "X"}, format="json"
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_diocese_delete_super_admin(admin_client):
    diocese = DioceseFactory()
    response = admin_client.delete(f"/api/v1/org/dioceses/{diocese.id}/")
    assert response.status_code == 204
    from apps.org.models import Diocese

    assert not Diocese.objects.filter(id=diocese.id).exists()


@pytest.mark.django_db
def test_diocese_delete_blocked_by_parishes(admin_client):
    diocese = DioceseFactory()
    ParishFactory(diocese=diocese)

    response = admin_client.delete(f"/api/v1/org/dioceses/{diocese.id}/")

    assert response.status_code == 400
    from apps.org.models import Diocese

    assert Diocese.objects.filter(id=diocese.id).exists()


@pytest.mark.django_db
def test_diocese_delete_404(admin_client):
    response = admin_client.delete("/api/v1/org/dioceses/999999/")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Doyennés — détail / update / delete
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_deanery_detail(auth_client):
    deanery = DeaneryFactory()
    response = auth_client.get(f"/api/v1/org/deaneries/{deanery.id}/")
    assert response.status_code == 200
    assert response.data["id"] == deanery.id


@pytest.mark.django_db
def test_deanery_detail_404(auth_client):
    response = auth_client.get("/api/v1/org/deaneries/999999/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_deanery_patch_partial_super_admin(admin_client):
    dean = BaseUserFactory()
    deanery = DeaneryFactory(name="Ancien nom", dean=dean)
    response = admin_client.patch(
        f"/api/v1/org/deaneries/{deanery.id}/",
        {"name": "Nouveau nom"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["name"] == "Nouveau nom"
    deanery.refresh_from_db()
    assert deanery.dean == dean  # PATCH partiel : le doyen n'est pas touché


@pytest.mark.django_db
def test_deanery_patch_clears_dean_with_explicit_null(admin_client):
    dean = BaseUserFactory()
    deanery = DeaneryFactory(dean=dean)
    response = admin_client.patch(
        f"/api/v1/org/deaneries/{deanery.id}/",
        {"dean_id": None},
        format="json",
    )
    assert response.status_code == 200
    deanery.refresh_from_db()
    assert deanery.dean is None


@pytest.mark.django_db
def test_deanery_patch_forbidden_for_fidele(auth_client):
    deanery = DeaneryFactory()
    response = auth_client.patch(
        f"/api/v1/org/deaneries/{deanery.id}/", {"name": "X"}, format="json"
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_deanery_delete_super_admin(admin_client):
    # Parish.deanery est SET_NULL : la paroisse rattachée est détachée, pas supprimée.
    deanery = DeaneryFactory()
    parish = ParishFactory(deanery=deanery)

    response = admin_client.delete(f"/api/v1/org/deaneries/{deanery.id}/")

    assert response.status_code == 204
    from apps.org.models import Deanery

    assert not Deanery.objects.filter(id=deanery.id).exists()
    parish.refresh_from_db()
    assert parish.deanery is None


@pytest.mark.django_db
def test_deanery_delete_forbidden_for_fidele(auth_client):
    deanery = DeaneryFactory()
    response = auth_client.delete(f"/api/v1/org/deaneries/{deanery.id}/")
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Églises — update / delete
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_church_patch_partial_super_admin(admin_client):
    church = ChurchFactory(name="Ancien nom", city="Dakar")
    response = admin_client.patch(
        f"/api/v1/org/churches/{church.id}/",
        {"name": "Nouveau nom"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["name"] == "Nouveau nom"
    church.refresh_from_db()
    assert church.city == "Dakar"  # PATCH partiel


@pytest.mark.django_db
def test_church_patch_forbidden_for_fidele(auth_client):
    church = ChurchFactory()
    response = auth_client.patch(
        f"/api/v1/org/churches/{church.id}/", {"name": "X"}, format="json"
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_church_patch_404(admin_client):
    response = admin_client.patch(
        "/api/v1/org/churches/999999/", {"name": "X"}, format="json"
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_church_delete_super_admin(admin_client):
    church = ChurchFactory()
    response = admin_client.delete(f"/api/v1/org/churches/{church.id}/")
    assert response.status_code == 204
    from apps.org.models import Church

    assert not Church.objects.filter(id=church.id).exists()


@pytest.mark.django_db
def test_church_delete_forbidden_for_fidele(auth_client):
    church = ChurchFactory()
    response = auth_client.delete(f"/api/v1/org/churches/{church.id}/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_church_delete_blocked_by_membership(admin_client):
    church = ChurchFactory()
    from apps.users.models import Membership

    Membership.objects.create(user=BaseUserFactory(), church=church, is_primary=True)

    response = admin_client.delete(f"/api/v1/org/churches/{church.id}/")

    assert response.status_code == 400
    from apps.org.models import Church

    assert Church.objects.filter(id=church.id).exists()


@pytest.mark.django_db
def test_church_delete_main_blocked_when_others_exist(admin_client):
    parish = ParishFactory()
    main = ChurchFactory(parish=parish, is_main=True, church_type="paroissiale")
    ChurchFactory(parish=parish)  # succursale

    response = admin_client.delete(f"/api/v1/org/churches/{main.id}/")

    assert response.status_code == 400
    assert "principale" in response.data["detail"]
    from apps.org.models import Church

    assert Church.objects.filter(id=main.id).exists()
