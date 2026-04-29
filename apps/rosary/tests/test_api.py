import pytest
from rest_framework.test import APIClient
from apps.rosary.models import MysteryGroup

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def setup_data():
    MysteryGroup.objects.create(name="Sorrowful", slug="sorrowful")

@pytest.mark.django_db
def test_group_list_api(api_client, setup_data):
    response = api_client.get("/api/v1/rosary/groups/")
    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["name"] == "Sorrowful"

@pytest.mark.django_db
def test_group_detail_api(api_client, setup_data):
    response = api_client.get("/api/v1/rosary/groups/sorrowful/")
    assert response.status_code == 200
    assert response.data["name"] == "Sorrowful"
