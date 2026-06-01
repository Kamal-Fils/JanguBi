"""
Tests unitaires — gestion des comptes.

Couvre :
  - user_activate_account : token valide, invalide, idempotent
  - user_toggle_active : admin active/désactive, auto-modification bloquée
  - user_soft_delete : anonymisation, rotation jwt_key
  - user_hard_delete : admin seulement, audit préservé
  - user_update_profile : propriétaire ou admin
"""


from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.core.exceptions import ApplicationError, TokenInvalidError
from apps.org.tests.factories import ChurchFactory, ParishFactory
from apps.users.enums import UserOnboardingState
from apps.users.models import BaseUser, Profile, SecurityAuditLog
from apps.users.otp import VERIFY_TOKEN_TTL, generate_url_token, token_store
from apps.users.services import (
    user_activate_account,
    user_hard_delete,
    user_soft_delete,
    user_toggle_active,
    user_update_profile,
)
from apps.users.tests.factories import (
    AdminUserFactory,
    BaseUserFactory,
    InactiveUserFactory,
    ProfileFactory,
    StaffUserFactory,
)

CACHE_SETTINGS = {
    "CACHES": {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
}


@override_settings(**CACHE_SETTINGS)
class UserActivateAccountTests(TestCase):

    def setUp(self):
        cache.clear()
        self.user = InactiveUserFactory()
        self.token = generate_url_token()
        token_store("email_verify", self.token, {"user_id": self.user.id}, ttl=VERIFY_TOKEN_TTL)

    def tearDown(self):
        cache.clear()

    def test_activates_user(self):
        user = user_activate_account(token=self.token)
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_verified)

    def test_audit_log_created(self):
        user_activate_account(token=self.token)
        self.assertTrue(
            SecurityAuditLog.objects.filter(user=self.user).exists()
        )

    def test_invalid_token_raises(self):
        with self.assertRaises(TokenInvalidError):
            user_activate_account(token="bad_token_xyz")

    def test_token_consumed_anti_replay(self):
        user_activate_account(token=self.token)
        with self.assertRaises(TokenInvalidError):
            user_activate_account(token=self.token)

    def test_already_active_is_idempotent(self):
        active_user = BaseUserFactory()
        token2 = generate_url_token()
        token_store("email_verify", token2, {"user_id": active_user.id}, ttl=VERIFY_TOKEN_TTL)
        # Ne doit pas lever d'exception
        result = user_activate_account(token=token2)
        self.assertTrue(result.is_active)

    def test_unknown_user_id_raises(self):
        bad_token = generate_url_token()
        token_store("email_verify", bad_token, {"user_id": 999999}, ttl=VERIFY_TOKEN_TTL)
        with self.assertRaises(TokenInvalidError):
            user_activate_account(token=bad_token)

    def test_activation_advances_onboarding_to_pending_parish(self):
        # InactiveUserFactory part de pending_email → après vérif email → pending_parish
        user = user_activate_account(token=self.token)
        self.assertEqual(
            user.onboarding_state, UserOnboardingState.PENDING_PARISH_SELECTION
        )


@override_settings(**CACHE_SETTINGS)
class UserToggleActiveTests(TestCase):

    def setUp(self):
        self.admin = AdminUserFactory()
        self.staff = StaffUserFactory()
        self.user = BaseUserFactory()

    def test_admin_can_deactivate_user(self):
        result = user_toggle_active(user=self.user, is_active=False, performed_by=self.admin)
        self.assertFalse(result.is_active)

    def test_admin_can_activate_user(self):
        inactive = InactiveUserFactory()
        result = user_toggle_active(user=inactive, is_active=True, performed_by=self.admin)
        self.assertTrue(result.is_active)

    def test_staff_can_toggle(self):
        result = user_toggle_active(user=self.user, is_active=False, performed_by=self.staff)
        self.assertFalse(result.is_active)

    def test_customer_cannot_toggle(self):
        customer = BaseUserFactory()
        with self.assertRaises(ApplicationError):
            user_toggle_active(user=self.user, is_active=False, performed_by=customer)

    def test_cannot_toggle_own_account(self):
        with self.assertRaises(ApplicationError) as ctx:
            user_toggle_active(user=self.admin, is_active=False, performed_by=self.admin)
        self.assertIn("propre", str(ctx.exception))

    def test_audit_log_created_on_deactivate(self):
        user_toggle_active(user=self.user, is_active=False, performed_by=self.admin)
        logs = SecurityAuditLog.objects.filter(user=self.user)
        self.assertTrue(logs.exists())


@override_settings(**CACHE_SETTINGS)
class UserSoftDeleteTests(TestCase):

    def setUp(self):
        self.admin = AdminUserFactory()
        self.user = BaseUserFactory(email="victim@example.com")
        ProfileFactory(user=self.user, first_name="Jane", last_name="Doe")

    def test_account_deactivated(self):
        user_soft_delete(user=self.user, performed_by=self.admin)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_email_anonymized(self):
        original_id = self.user.id
        user_soft_delete(user=self.user, performed_by=self.admin)
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.email, "victim@example.com")
        self.assertIn("deleted", self.user.email)

    def test_password_set_unusable(self):
        user_soft_delete(user=self.user, performed_by=self.admin)
        self.user.refresh_from_db()
        self.assertFalse(self.user.has_usable_password())

    def test_jwt_key_rotated(self):
        old_jwt_key = self.user.jwt_key
        user_soft_delete(user=self.user, performed_by=self.admin)
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.jwt_key, old_jwt_key)

    def test_profile_anonymized(self):
        user_soft_delete(user=self.user, performed_by=self.admin)
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.first_name, "")
        self.assertEqual(profile.last_name, "")

    def test_audit_log_created(self):
        user_soft_delete(user=self.user, performed_by=self.admin)
        self.assertTrue(SecurityAuditLog.objects.filter(user=self.user).exists())

    def test_owner_can_self_soft_delete(self):
        user_soft_delete(user=self.user, performed_by=self.user)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_other_customer_cannot_delete(self):
        other = BaseUserFactory()
        with self.assertRaises(ApplicationError):
            user_soft_delete(user=self.user, performed_by=other)


@override_settings(**CACHE_SETTINGS)
class UserHardDeleteTests(TestCase):

    def setUp(self):
        self.admin = AdminUserFactory()

    def test_admin_can_hard_delete(self):
        user = BaseUserFactory()
        user_id = user.id
        user_hard_delete(user=user, performed_by=self.admin)
        self.assertFalse(BaseUser.objects.filter(id=user_id).exists())

    def test_audit_log_preserved_after_delete(self):
        user = BaseUserFactory()
        user_hard_delete(user=user, performed_by=self.admin)
        # Le log doit exister avec user=NULL (SET_NULL)
        log = SecurityAuditLog.objects.filter(user=None).last()
        self.assertIsNotNone(log)

    def test_non_admin_cannot_hard_delete(self):
        user = BaseUserFactory()
        staff = StaffUserFactory()
        with self.assertRaises(ApplicationError):
            user_hard_delete(user=user, performed_by=staff)

    def test_cannot_delete_own_account(self):
        with self.assertRaises(ApplicationError):
            user_hard_delete(user=self.admin, performed_by=self.admin)


@override_settings(**CACHE_SETTINGS)
class UserUpdateProfileTests(TestCase):

    def setUp(self):
        self.admin = AdminUserFactory()
        self.user = BaseUserFactory()
        ProfileFactory(user=self.user)

    def test_owner_can_update_own_profile(self):
        user_update_profile(
            user=self.user,
            data={"first_name": "Nouveau"},
            performed_by=self.user,
        )
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.first_name, "Nouveau")

    def test_admin_can_update_any_profile(self):
        user_update_profile(
            user=self.user,
            data={"last_name": "Modifié"},
            performed_by=self.admin,
        )
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.last_name, "Modifié")

    def test_other_customer_cannot_update(self):
        other = BaseUserFactory()
        with self.assertRaises(ApplicationError):
            user_update_profile(
                user=self.user,
                data={"first_name": "Hacker"},
                performed_by=other,
            )

    def test_audit_log_created(self):
        user_update_profile(
            user=self.user,
            data={"first_name": "Test"},
            performed_by=self.user,
        )
        self.assertTrue(SecurityAuditLog.objects.filter(user=self.user).exists())

    def test_setting_primary_parish_completes_onboarding(self):
        # Arrange — fidèle en attente de sélection de paroisse. Le PATCH legacy est
        # désormais routé (compat shim) vers une Membership sur l'église principale →
        # la paroisse doit posséder son église is_main.
        self.user.onboarding_state = UserOnboardingState.PENDING_PARISH_SELECTION
        self.user.save(update_fields=["onboarding_state"])
        parish = ParishFactory()
        ChurchFactory(parish=parish, is_main=True, church_type="paroissiale")

        # Act — sélection de la paroisse principale (id, comme l'envoie le front)
        user_update_profile(
            user=self.user,
            data={"primary_parish": parish.id},
            performed_by=self.user,
        )

        # Assert — onboarding terminé + hiérarchie territoriale auto-remplie (signal)
        self.user.refresh_from_db()
        self.assertEqual(self.user.onboarding_state, UserOnboardingState.COMPLETED)
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.primary_parish_id, parish.id)
        self.assertEqual(self.user.diocese_id, parish.diocese_id)
        self.assertEqual(self.user.province_id, parish.diocese.province_id)

    def test_setting_unknown_parish_raises(self):
        with self.assertRaises(ApplicationError):
            user_update_profile(
                user=self.user,
                data={"primary_parish": 999999},
                performed_by=self.user,
            )

    def test_update_profile_returns_fresh_territory_after_parish_selection(self):
        # 🟠 /me périmé : le signal remplit diocese/province via queryset .update()
        # (ne touche pas l'objet en mémoire). Le service DOIT renvoyer l'objet
        # rafraîchi, sinon PATCH /me renvoie diocese/province = null juste après
        # la sélection de paroisse.
        parish = ParishFactory()
        ChurchFactory(parish=parish, is_main=True, church_type="paroissiale")

        user = user_update_profile(
            user=self.user,
            data={"primary_parish": parish.id},
            performed_by=self.user,
        )

        # Pas de refresh_from_db manuel ici : le service doit déjà l'avoir fait.
        self.assertEqual(user.diocese_id, parish.diocese_id)
        self.assertEqual(user.province_id, parish.diocese.province_id)
