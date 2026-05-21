import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.bible.models import HomilieNote, LectioDivinaSession, ReadingPlan, Verse
from apps.users.models import BaseUser


@pytest.fixture
def verse(db):
    from apps.bible.models import Book, Chapter, Testament

    testament = Testament.objects.create(slug="at-adv", name="AT Avancé", order=99)
    book = Book.objects.create(name="TestBook", slug="test-book-adv", testament=testament, order=99)
    chapter = Chapter.objects.create(book=book, number=1)
    return Verse.objects.create(chapter=chapter, number=1, text="Verset test")


def _make_user(email, pastoral_role):
    user = BaseUser.objects.create_user(
        email=email,
        password="StrongPassw0rd!",
        role="fidele",
        phone_number=f"+221770{abs(hash(email)) % 1_000_000:06d}",
        is_active=True,
        is_verified=True,
    )
    user.pastoral_role = pastoral_role
    user.save(update_fields=["pastoral_role"])
    return user


@pytest.fixture
def clergy_client(db):
    client = APIClient()
    user = _make_user("pretre@example.com", "pretre")
    client.force_authenticate(user=user)
    client._user = user
    return client


@pytest.fixture
def diacre_client(db):
    client = APIClient()
    user = _make_user("diacre@example.com", "diacre")
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
def test_homilenote_create_clergy_201(diacre_client, verse):
    url = reverse("api:bible:homilenote-list-create")
    resp = diacre_client.post(url, {"passage_start_id": verse.pk, "content": "Réflexion"}, format="json")
    assert resp.status_code == status.HTTP_201_CREATED
    assert HomilieNote.objects.filter(author=diacre_client._user).count() == 1


@pytest.mark.django_db
def test_homilenote_create_fidele_400(fidele_client, verse):
    url = reverse("api:bible:homilenote-list-create")
    resp = fidele_client.post(url, {"passage_start_id": verse.pk, "content": "Réflexion"}, format="json")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_homilenote_list_own(diacre_client, verse):
    HomilieNote.objects.create(author=diacre_client._user, passage_start=verse, content="Note")
    url = reverse("api:bible:homilenote-list-create")
    resp = diacre_client.get(url)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["count"] == 1


@pytest.mark.django_db
def test_homilenote_requires_auth(verse):
    client = APIClient()
    url = reverse("api:bible:homilenote-list-create")
    resp = client.get(url)
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_lectio_divina_upsert(fidele_client, verse):
    url = reverse("api:bible:lectio-divina")
    data = {"passage_id": verse.pk, "lectio": "Je lis", "meditatio": "Je médite"}
    resp = fidele_client.post(url, data, format="json")
    assert resp.status_code == status.HTTP_200_OK
    assert LectioDivinaSession.objects.filter(user=fidele_client._user).count() == 1


@pytest.mark.django_db
def test_lectio_divina_list(fidele_client, verse):
    LectioDivinaSession.objects.create(user=fidele_client._user, passage=verse, lectio="abc")
    url = reverse("api:bible:lectio-divina")
    resp = fidele_client.get(url)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["count"] == 1


@pytest.mark.django_db
def test_reading_plan_create_pretre_201(clergy_client, db):
    url = reverse("api:bible:reading-plan-list-create")
    resp = clergy_client.post(url, {"title": "Plan Avent", "description": "30 jours"}, format="json")
    assert resp.status_code == status.HTTP_201_CREATED
    assert ReadingPlan.objects.filter(author=clergy_client._user).count() == 1


@pytest.mark.django_db
def test_reading_plan_create_fidele_400(fidele_client, db):
    url = reverse("api:bible:reading-plan-list-create")
    resp = fidele_client.post(url, {"title": "Plan Avent"}, format="json")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_reading_plan_list_public(clergy_client, db):
    ReadingPlan.objects.create(author=clergy_client._user, title="Plan pub", is_published=True)
    ReadingPlan.objects.create(author=clergy_client._user, title="Plan priv", is_published=False)
    url = reverse("api:bible:reading-plan-list-create")
    resp = clergy_client.get(url)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["count"] == 1
