from itertools import count

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.tv.models import Category, Video
from apps.users.enums import UserRole
from apps.users.models import BaseUser

# `phone_number` est unique en base : un numéro figé empêchait deux acteurs de
# coexister dans un même test (indispensable pour une matrice d'accès).
_phone_sequence = count(1)


def _make_user(email, role=UserRole.FIDELE, pastoral_role=None):
    user = BaseUser.objects.create_user(
        email=email,
        password="pwd",
        role=role,
        phone_number=f"+336{next(_phone_sequence):08d}",
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


class TvCatalogAccessMatrixTests(APITestCase):
    """Matrice d'accès du catalogue TV, acteur par acteur.

    Ces tests figent le contrat : la LECTURE du catalogue est publique (le
    catalogue est une vitrine ouverte aux visiteurs non connectés) et
    l'ÉCRITURE est réservée au Super Admin. Ils existent pour qu'un ajout de
    garde d'authentification ne referme pas le catalogue par accident.
    """

    def setUp(self):
        self.public_category = Category.objects.create(name="Messes", slug="messes", order=1)
        self.public_video = Video.objects.create(
            title="Messe du dimanche",
            youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            category=self.public_category,
        )
        self.reserved_category = Category.objects.create(
            name="Formation", slug="formation", order=2, is_clergy_only=True
        )
        self.reserved_video = Video.objects.create(
            title="Formation prêtres",
            youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            category=self.reserved_category,
        )
        self.fidele = _make_user("matrix-fidele@test.com")
        self.clergy = _make_user("matrix-pretre@test.com", pastoral_role="pretre")
        self.admin = BaseUser.objects.create_superuser(email="matrix-admin@test.com", password="pwd")

        self.category_list_url = reverse("api:tv:tv-category-list")
        self.category_detail_url = reverse("api:tv:tv-category-detail", args=["messes"])
        self.video_list_url = reverse("api:tv:tv-video-list")
        self.video_detail_url = reverse("api:tv:tv-video-detail", args=[self.public_video.id])

    # --- Lecture publique : volontairement ouverte aux visiteurs anonymes. ---

    def test_anonymous_can_read_the_public_catalog(self):
        for url in (
            self.category_list_url,
            self.category_detail_url,
            self.video_list_url,
            self.video_detail_url,
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, status.HTTP_200_OK)

    def test_fidele_can_read_the_public_catalog(self):
        self.client.force_authenticate(user=self.fidele)
        for url in (
            self.category_list_url,
            self.category_detail_url,
            self.video_list_url,
            self.video_detail_url,
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, status.HTTP_200_OK)

    # --- Écriture : Super Admin uniquement. ---

    def _write_attempts(self):
        return (
            ("post", self.category_list_url, {"name": "Reportages", "order": 5}),
            ("patch", self.category_detail_url, {"name": "Messes dominicales"}),
            ("delete", self.category_detail_url, None),
            (
                "post",
                self.video_list_url,
                {"youtube_url": "https://youtu.be/5NV6Rdv1a3I", "category_slug": "messes"},
            ),
            ("patch", self.video_detail_url, {"title": "Renommée"}),
            ("delete", self.video_detail_url, None),
        )

    def test_anonymous_cannot_write(self):
        for method, url, payload in self._write_attempts():
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url, payload, format="json")
                self.assertIn(
                    response.status_code,
                    [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
                )

    def test_fidele_cannot_write(self):
        self.client.force_authenticate(user=self.fidele)
        for method, url, payload in self._write_attempts():
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url, payload, format="json")
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_clergy_cannot_write(self):
        # Le clergé LIT le catalogue réservé, il ne l'ADMINISTRE pas : la gestion
        # du catalogue TV reste une configuration globale (Super Admin).
        self.client.force_authenticate(user=self.clergy)
        for method, url, payload in self._write_attempts():
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url, payload, format="json")
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_super_admin_can_write(self):
        self.client.force_authenticate(user=self.admin)

        created = self.client.post(self.category_list_url, {"name": "Reportages", "order": 5}, format="json")
        renamed = self.client.patch(self.category_detail_url, {"order": 7}, format="json")
        video_created = self.client.post(
            self.video_list_url,
            {"youtube_url": "https://youtu.be/5NV6Rdv1a3I", "category_slug": "messes"},
            format="json",
        )
        video_removed = self.client.delete(self.video_detail_url)

        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(renamed.status_code, status.HTTP_200_OK)
        self.assertEqual(video_created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(video_removed.status_code, status.HTTP_204_NO_CONTENT)

    # --- Cloisonnement clergé : doit tenir après tout ajout de garde. ---

    def test_reserved_catalog_stays_hidden_from_anonymous_and_fidele(self):
        reserved_category_url = reverse("api:tv:tv-category-detail", args=["formation"])
        reserved_video_url = reverse("api:tv:tv-video-detail", args=[self.reserved_video.id])

        for actor in (None, self.fidele):
            with self.subTest(actor=actor):
                self.client.force_authenticate(user=actor)

                categories = self.client.get(self.category_list_url)
                videos = self.client.get(self.video_list_url)

                self.assertNotIn("formation", [c["slug"] for c in categories.data["results"]])
                self.assertNotIn("Formation prêtres", [v["title"] for v in videos.data["results"]])
                self.assertEqual(self.client.get(reserved_category_url).status_code, status.HTTP_404_NOT_FOUND)
                self.assertEqual(self.client.get(reserved_video_url).status_code, status.HTTP_404_NOT_FOUND)

    def test_clergy_sees_the_reserved_catalog(self):
        self.client.force_authenticate(user=self.clergy)

        categories = self.client.get(self.category_list_url)
        videos = self.client.get(self.video_list_url)

        self.assertIn("formation", [c["slug"] for c in categories.data["results"]])
        self.assertIn("Formation prêtres", [v["title"] for v in videos.data["results"]])

    def test_super_admin_sees_the_reserved_catalog_in_listings(self):
        # Le Super Admin administre le catalogue mais n'a pas de pastoral_role :
        # filtré comme un fidèle, il ne pouvait plus voir « Formation » dans la
        # liste — donc plus l'affecter à une vidéo depuis l'UI d'admin, alors
        # même que la route de détail lui reste ouverte. Incohérent.
        self.client.force_authenticate(user=self.admin)

        categories = self.client.get(self.category_list_url)
        videos = self.client.get(self.video_list_url)

        self.assertIn("formation", [c["slug"] for c in categories.data["results"]])
        self.assertIn("Formation prêtres", [v["title"] for v in videos.data["results"]])

    def test_super_admin_reaches_the_reserved_catalog_by_identifier(self):
        self.client.force_authenticate(user=self.admin)

        category = self.client.get(reverse("api:tv:tv-category-detail", args=["formation"]))
        video = self.client.get(reverse("api:tv:tv-video-detail", args=[self.reserved_video.id]))

        self.assertEqual(category.status_code, status.HTTP_200_OK)
        self.assertEqual(video.status_code, status.HTTP_200_OK)


class TvCategorySlugTests(APITestCase):
    """Le slug est un IDENTIFIANT STABLE, attribué une fois à la création.

    Il sert de clé d'URL (``/categories/<slug>/``) et de référence dans les
    payloads d'écriture des vidéos (``category_slug``) : le régénérer à chaque
    renommage invaliderait l'URL de la ressource au milieu du cycle d'édition.
    """

    def setUp(self):
        self.admin = BaseUser.objects.create_superuser(email="slug-admin@test.com", password="pwd")
        self.client.force_authenticate(user=self.admin)

    def test_renaming_a_category_keeps_its_slug(self):
        category = Category.objects.create(name="Messes", slug="messes", order=1)
        url = reverse("api:tv:tv-category-detail", args=["messes"])

        response = self.client.patch(url, {"name": "Célébrations"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        category.refresh_from_db()
        self.assertEqual(category.name, "Célébrations")
        self.assertEqual(category.slug, "messes")
        self.assertEqual(response.data["slug"], "messes")

    def test_renamed_category_stays_reachable_at_its_original_url(self):
        # Conséquence directe du choix : l'URL survit au renommage, donc un
        # formulaire d'édition peut enchaîner deux enregistrements.
        Category.objects.create(name="Messes", slug="messes", order=1)
        url = reverse("api:tv:tv-category-detail", args=["messes"])

        self.client.patch(url, {"name": "Célébrations"}, format="json")
        second = self.client.patch(url, {"order": 4}, format="json")

        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second.data["name"], "Célébrations")

    def test_videos_keep_pointing_at_the_renamed_category(self):
        category = Category.objects.create(name="Messes", slug="messes", order=1)
        Video.objects.create(
            title="Messe du dimanche",
            youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            category=category,
        )
        self.client.patch(reverse("api:tv:tv-category-detail", args=["messes"]), {"name": "Célébrations"}, format="json")

        response = self.client.get(reverse("api:tv:tv-video-list"), {"category": "messes"})

        self.assertEqual(response.data["count"], 1)

    def test_creating_a_category_whose_name_collides_returns_a_user_safe_error(self):
        # Deux noms distincts peuvent produire le même slug (« Messes » /
        # « messes ! »). Sans garde, c'est l'unicité DB qui parle, dans un
        # vocabulaire (« slug ») que le client n'a jamais employé.
        Category.objects.create(name="Messes", slug="messes", order=1)
        url = reverse("api:tv:tv-category-list")

        response = self.client.post(url, {"name": "Messes !", "order": 2}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIsInstance(response.data["detail"], str)
        self.assertIn("Messes !", response.data["detail"])

    def test_creating_a_category_with_an_unsluggable_name_is_rejected_cleanly(self):
        url = reverse("api:tv:tv-category-list")

        response = self.client.post(url, {"name": "!!!", "order": 2}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIsInstance(response.data["detail"], str)
