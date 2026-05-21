"""
Factories factory_boy pour les tests users.
Alignées sur apps/users/enums.py (UserRole, Title) et models.py réels.
"""

import factory
from factory.django import DjangoModelFactory

from apps.users.enums import Title, UserRole
from apps.users.models import BaseUser, Profile


class BaseUserFactory(DjangoModelFactory):
    """Crée un utilisateur fidèle actif et vérifié par défaut."""

    class Meta:
        model = BaseUser
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    phone_number = factory.Sequence(lambda n: f"+2217700{n:05d}")
    role = UserRole.FIDELE
    is_active = True
    is_verified = True
    is_staff = False
    is_admin = False

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop("password", "StrongPassw0rd!")
        manager = model_class.objects
        user = manager.create_user(password=password, **kwargs)
        return user


class SuperAdminFactory(BaseUserFactory):
    """Crée un compte super_admin (accès total)."""

    role = UserRole.SUPER_ADMIN
    is_staff = True
    is_admin = True


# Alias large utilisé dans tous les tests existants
AdminUserFactory = SuperAdminFactory


class StaffUserFactory(BaseUserFactory):
    """Crée un compte admin paroisse (is_staff=True, is_admin=True)."""

    role = UserRole.PARISH_ADMIN
    is_staff = True
    is_admin = True


class InactiveUserFactory(BaseUserFactory):
    """Crée un compte non vérifié / inactif (juste inscrit, avant activation email)."""

    is_active = False
    is_verified = False


class ProfileFactory(DjangoModelFactory):
    """Crée un profil basique lié à un BaseUser fidèle."""

    class Meta:
        model = Profile

    user = factory.SubFactory(BaseUserFactory)
    first_name = factory.Sequence(lambda n: f"Prénom{n}")
    last_name = factory.Sequence(lambda n: f"Nom{n}")
    title = Title.MR
