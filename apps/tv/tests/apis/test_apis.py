from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.tv.models import Category, Video
from apps.users.enums import UserRole
from apps.users.models import BaseUser


def _make_user(email, role=UserRole.FIDELE, pastoral_role=None):
    user = BaseUser.objects.create_user(
        email=email,
        password="pwd",
        role=role,
        phone_number="+33600000001",
        is_active=True,
        is_verified=True,
    )
    if pastoral_role:
        user.pastoral_role = pastoral_role
        user.save(update_fields=["pastoral_role"])
    return user


class TvApiTests(APITestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Messes", slug="messes", order=1)
        self.video = Video.objects.create(
            title="Homelie du jour",
            youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            category=self.category,
        )
        self.admin = BaseUser.objects.create_superuser(email="admin-tv@test.com", password="pwd")

    def test_list_categories_public(self):
        url = reverse("api:tv:tv-category-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["slug"], "messes")

    def test_create_category_requires_admin(self):
        url = reverse("api:tv:tv-category-list")
        response = self.client.post(url, {"name": "Documentaires", "order": 3}, format="json")
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

        self.client.force_authenticate(user=self.admin)
        response = self.client.post(url, {"name": "Documentaires", "order": 3}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_get_video_detail(self):
        url = reverse("api:tv:tv-video-detail", args=[self.video.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.video.id)
        self.assertEqual(response.data["category"]["slug"], "messes")

    def test_video_not_found_returns_clear_message(self):
        url = reverse("api:tv:tv-video-detail", args=[999999])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data, {"error": "Video not found."})

    def test_create_video_with_category_slug_admin(self):
        self.client.force_authenticate(user=self.admin)
        url = reverse("api:tv:tv-video-list")
        payload = {
            "title": "Enseignement",
            "youtube_url": "https://youtu.be/5NV6Rdv1a3I",
            "category_slug": "messes",
            "is_live": False,
            "is_pinned_live": False,
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["youtube_id"], "5NV6Rdv1a3I")
        self.assertEqual(response.data["category"]["slug"], "messes")

    def test_create_video_invalid_category_slug(self):
        self.client.force_authenticate(user=self.admin)
        url = reverse("api:tv:tv-video-list")
        payload = {
            "title": "Video test",
            "youtube_url": "https://youtu.be/5NV6Rdv1a3I",
            "category_slug": "unknown-category",
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)

    def test_update_video_requires_admin(self):
        url = reverse("api:tv:tv-video-detail", args=[self.video.id])
        payload = {
            "title": "Updated",
            "youtube_url": "https://youtu.be/5NV6Rdv1a3I",
            "category_slug": "messes",
        }

        response = self.client.patch(url, payload, format="json")
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Updated")

    def test_clergy_only_category_hidden_from_fidele(self):
        clergy_cat = Category.objects.create(name="Formation", slug="formation", order=2, is_clergy_only=True)
        Video.objects.create(
            title="Formation prêtres",
            youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            category=clergy_cat,
        )
        url = reverse("api:tv:tv-category-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = [c["slug"] for c in response.data["results"]]
        self.assertIn("messes", slugs)
        self.assertNotIn("formation", slugs)

    def test_clergy_only_category_visible_to_clergy(self):
        Category.objects.create(name="Formation", slug="formation", order=2, is_clergy_only=True)
        pretre = _make_user("pretre@test.com", pastoral_role="pretre")
        self.client.force_authenticate(user=pretre)
        url = reverse("api:tv:tv-category-list")
        response = self.client.get(url)
        slugs = [c["slug"] for c in response.data["results"]]
        self.assertIn("formation", slugs)

    def test_clergy_only_videos_hidden_from_fidele(self):
        clergy_cat = Category.objects.create(name="Formation", slug="formation", order=2, is_clergy_only=True)
        Video.objects.create(
            title="Formation prêtres",
            youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            category=clergy_cat,
        )
        url = reverse("api:tv:tv-video-list")
        response = self.client.get(url)
        titles = [v["title"] for v in response.data["results"]]
        self.assertNotIn("Formation prêtres", titles)
        self.assertIn("Homelie du jour", titles)

    def test_clergy_only_videos_visible_to_clergy(self):
        clergy_cat = Category.objects.create(name="Formation", slug="formation", order=2, is_clergy_only=True)
        Video.objects.create(
            title="Formation prêtres",
            youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            category=clergy_cat,
        )
        pretre = _make_user("pretre2@test.com", pastoral_role="pretre")
        self.client.force_authenticate(user=pretre)
        url = reverse("api:tv:tv-video-list")
        response = self.client.get(url)
        titles = [v["title"] for v in response.data["results"]]
        self.assertIn("Formation prêtres", titles)

    def test_category_serializer_includes_is_clergy_only(self):
        url = reverse("api:tv:tv-category-list")
        response = self.client.get(url)
        self.assertIn("is_clergy_only", response.data["results"][0])

    def test_create_clergy_only_category_persists_the_flag(self):
        # Régression : le serializer expose `is_clergy_only` en écriture mais le
        # service ne l'acceptait pas → TypeError → 500 sur toute création de
        # catégorie réservée au clergé (la seule qui compte : « Formation »).
        self.client.force_authenticate(user=self.admin)
        url = reverse("api:tv:tv-category-list")

        response = self.client.post(
            url, {"name": "Formation", "order": 9, "is_clergy_only": True}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["is_clergy_only"])
        self.assertTrue(Category.objects.get(slug="formation").is_clergy_only)

    def test_create_category_defaults_to_public(self):
        self.client.force_authenticate(user=self.admin)
        url = reverse("api:tv:tv-category-list")

        response = self.client.post(url, {"name": "Reportages", "order": 4}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(Category.objects.get(slug="reportages").is_clergy_only)

    def test_update_category_toggles_clergy_only(self):
        # Même rupture côté écriture partielle : PATCH is_clergy_only doit prendre.
        self.client.force_authenticate(user=self.admin)
        url = reverse("api:tv:tv-category-detail", args=[self.category.slug])

        response = self.client.patch(url, {"is_clergy_only": True}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.category.refresh_from_db()
        self.assertTrue(self.category.is_clergy_only)

    def test_clergy_only_category_visible_to_religieux(self):
        # `religieux` fait partie du clergé canonique (CLERGY_PASTORAL_ROLES) :
        # il doit voir les catégories réservées, comme un prêtre.
        Category.objects.create(name="Formation", slug="formation", order=2, is_clergy_only=True)
        religieux = _make_user("religieux-tv@test.com", pastoral_role="religieux")
        self.client.force_authenticate(user=religieux)

        response = self.client.get(reverse("api:tv:tv-category-list"))

        self.assertIn("formation", [c["slug"] for c in response.data["results"]])

    def test_clergy_only_video_not_reachable_by_id_for_fidele(self):
        # Cloisonnement clergé : la liste filtrait, PAS la route de détail — une
        # vidéo « Formation » restait lisible en devinant son id.
        clergy_cat = Category.objects.create(name="Formation", slug="formation", order=2, is_clergy_only=True)
        clergy_video = Video.objects.create(
            title="Formation prêtres",
            youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            category=clergy_cat,
        )
        url = reverse("api:tv:tv-video-detail", args=[clergy_video.id])

        anonymous = self.client.get(url)
        self.client.force_authenticate(user=_make_user("fidele-tv@test.com"))
        fidele = self.client.get(url)

        self.assertEqual(anonymous.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(fidele.status_code, status.HTTP_404_NOT_FOUND)

    def test_clergy_only_video_reachable_by_id_for_clergy(self):
        clergy_cat = Category.objects.create(name="Formation", slug="formation", order=2, is_clergy_only=True)
        clergy_video = Video.objects.create(
            title="Formation prêtres",
            youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            category=clergy_cat,
        )
        self.client.force_authenticate(user=_make_user("pretre-detail@test.com", pastoral_role="pretre"))

        response = self.client.get(reverse("api:tv:tv-video-detail", args=[clergy_video.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Formation prêtres")

    def test_clergy_only_category_not_reachable_by_slug_for_fidele(self):
        Category.objects.create(name="Formation", slug="formation", order=2, is_clergy_only=True)
        url = reverse("api:tv:tv-category-detail", args=["formation"])

        anonymous = self.client.get(url)

        self.assertEqual(anonymous.status_code, status.HTTP_404_NOT_FOUND)

    def test_super_admin_can_still_manage_clergy_only_category(self):
        # Le filtre de lecture ne doit pas enfermer le Super Admin hors de la
        # catégorie réservée (il n'a pas de pastoral_role).
        Category.objects.create(name="Formation", slug="formation", order=2, is_clergy_only=True)
        self.client.force_authenticate(user=self.admin)
        url = reverse("api:tv:tv-category-detail", args=["formation"])

        renamed = self.client.patch(url, {"name": "Formation continue"}, format="json")
        removed = self.client.delete(url)

        self.assertEqual(renamed.status_code, status.HTTP_200_OK)
        self.assertEqual(removed.status_code, status.HTTP_204_NO_CONTENT)
