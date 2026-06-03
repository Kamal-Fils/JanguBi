import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.org.tests.factories import (
    ChurchFactory,
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
    assert len(response.data) == 3


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
