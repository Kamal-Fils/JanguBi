"""
Tests for purge_expired_unactivated_admin_accounts service.
Pattern AAA (Arrange / Act / Assert).
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.users.enums import UserRole
from apps.users.models import BaseUser
from apps.users.services import purge_expired_unactivated_admin_accounts
from apps.users.tests.factories import BaseUserFactory, StaffUserFactory, SuperAdminFactory


# ---------------------------------------------------------------------------
# purge_expired_unactivated_admin_accounts
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_purge_deletes_expired_unactivated_admin_accounts():
    # Arrange — admin created 30 days ago, never logged in
    user = SuperAdminFactory(last_login=None)
    past = timezone.now() - timedelta(days=30)
    BaseUser.objects.filter(id=user.id).update(created_at=past)

    # Act
    count = purge_expired_unactivated_admin_accounts(expiry_days=7)

    # Assert
    assert count == 1
    assert not BaseUser.objects.filter(id=user.id).exists()


@pytest.mark.django_db
def test_purge_returns_correct_count():
    # Arrange — 3 expired admins, all never logged in
    past = timezone.now() - timedelta(days=30)
    users = [SuperAdminFactory(last_login=None) for _ in range(3)]
    BaseUser.objects.filter(id__in=[u.id for u in users]).update(created_at=past)

    # Act
    count = purge_expired_unactivated_admin_accounts(expiry_days=7)

    # Assert
    assert count == 3


@pytest.mark.django_db
def test_purge_does_not_delete_recently_created_admins():
    # Arrange — admin created today, never logged in (within expiry window)
    SuperAdminFactory(last_login=None)

    # Act
    count = purge_expired_unactivated_admin_accounts(expiry_days=7)

    # Assert
    assert count == 0


@pytest.mark.django_db
def test_purge_does_not_delete_admins_who_have_logged_in():
    # Arrange — admin created long ago but has logged in
    user = SuperAdminFactory(last_login=timezone.now())
    past = timezone.now() - timedelta(days=30)
    BaseUser.objects.filter(id=user.id).update(created_at=past)

    # Act
    count = purge_expired_unactivated_admin_accounts(expiry_days=7)

    # Assert
    assert count == 0
    assert BaseUser.objects.filter(id=user.id).exists()


@pytest.mark.django_db
def test_purge_does_not_delete_fidele_accounts():
    # Arrange — regular user created long ago, never logged in
    user = BaseUserFactory(last_login=None)
    past = timezone.now() - timedelta(days=30)
    BaseUser.objects.filter(id=user.id).update(created_at=past)

    # Act
    count = purge_expired_unactivated_admin_accounts(expiry_days=7)

    # Assert
    assert count == 0
    assert BaseUser.objects.filter(id=user.id).exists()


@pytest.mark.django_db
def test_purge_deletes_all_admin_role_types():
    # Arrange — one of each admin role, all expired and never logged in
    from apps.users.enums import UserRole

    past = timezone.now() - timedelta(days=30)
    admin_roles = [
        UserRole.SUPER_ADMIN,
        UserRole.PROVINCE_ADMIN,
        UserRole.DIOCESE_ADMIN,
        UserRole.PARISH_ADMIN,
        UserRole.CHURCH_ADMIN,
    ]
    users = []
    for role in admin_roles:
        u = BaseUserFactory(role=role, last_login=None, is_staff=True, is_admin=True)
        users.append(u)
    BaseUser.objects.filter(id__in=[u.id for u in users]).update(created_at=past)

    # Act
    count = purge_expired_unactivated_admin_accounts(expiry_days=7)

    # Assert — all 5 admin role types were deleted
    assert count == 5


@pytest.mark.django_db
def test_purge_returns_zero_when_no_accounts_match():
    # Arrange — no admin accounts at all
    BaseUserFactory()  # fidele user

    # Act
    count = purge_expired_unactivated_admin_accounts(expiry_days=7)

    # Assert
    assert count == 0
