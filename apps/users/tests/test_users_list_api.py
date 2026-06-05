"""BUG-B1 — /api/v1/users/ 500 « Object of type Parish is not JSON serializable ».

`primary_parish` (FK Parish) était émis en objet brut dans la sortie de la liste
users → le renderer JSON de DRF plantait. Doit être sérialisé en {id, name} | null.
"""

import pytest
from rest_framework.test import APIClient

from apps.org.tests.factories import ParishFactory
from apps.users.tests.factories import (
    BaseUserFactory,
    ProfileFactory,
    SuperAdminFactory,
)


def _admin_client():
    client = APIClient()
    client.force_authenticate(user=SuperAdminFactory())
    return client


@pytest.mark.django_db
def test_users_list_serializes_primary_parish_as_object():
    parish = ParishFactory(name="Cathédrale du Souvenir")
    fidele = BaseUserFactory()
    ProfileFactory(user=fidele, primary_parish=parish)

    resp = _admin_client().get("/api/v1/users/?limit=50&offset=0")

    # ROUGE avant le fix : 500 (Parish non sérialisable au rendu JSON).
    assert resp.status_code == 200
    item = next(r for r in resp.data["results"] if r["email"] == fidele.email)
    assert item["user_profile"]["primary_parish"] == {
        "id": parish.id,
        "name": parish.name,
    }


@pytest.mark.django_db
def test_users_list_primary_parish_null_when_absent():
    user = BaseUserFactory()
    ProfileFactory(user=user)  # profil sans paroisse principale

    resp = _admin_client().get("/api/v1/users/?limit=50&offset=0")

    assert resp.status_code == 200
    item = next(r for r in resp.data["results"] if r["email"] == user.email)
    assert item["user_profile"]["primary_parish"] is None


@pytest.mark.django_db
def test_users_list_exposes_pastoral_role():
    # F3b : le clergé a role='fidele' (dimension admin) + pastoral_role pour
    # l'identité. La liste admin doit exposer pastoral_role (badge « Prêtre »).
    pretre = BaseUserFactory(role="fidele", pastoral_role="pretre")

    resp = _admin_client().get("/api/v1/users/?limit=50&offset=0")

    assert resp.status_code == 200
    item = next(r for r in resp.data["results"] if r["email"] == pretre.email)
    assert item["pastoral_role"] == "pretre"


@pytest.mark.django_db
def test_users_list_filters_by_pastoral_role():
    # F3b : ?pastoral_role=pretre ne renvoie QUE le clergé prêtre, pas les laïcs
    # ni les autres rôles pastoraux.
    pretre = BaseUserFactory(role="fidele", pastoral_role="pretre")
    BaseUserFactory(role="fidele", pastoral_role="eveque")
    BaseUserFactory(role="fidele", pastoral_role="")  # laïc

    resp = _admin_client().get("/api/v1/users/?pastoral_role=pretre&limit=50")

    assert resp.status_code == 200
    emails = {r["email"] for r in resp.data["results"]}
    assert emails == {pretre.email}
