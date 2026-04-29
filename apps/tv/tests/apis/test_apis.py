from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.tv.models import Category, Video
from apps.users.models import BaseUser


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
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["slug"], "messes")

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
