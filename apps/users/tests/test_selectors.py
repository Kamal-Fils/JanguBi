"""
Tests des selectors utilisateurs.

Couvre :
  - user_get_login_data : avec et sans profil
  - user_get : trouvé / non trouvé
  - user_get_by_email : trouvé / non trouvé (insensible à la casse)
  - user_get_with_profile : trouvé avec select_related / non trouvé
  - user_list : sans filtre, filtre role, filtre is_active, filtre email
  - user_list_for_admin : liste complète (actifs + inactifs)
  - profile_get : trouvé / non trouvé
  - audit_log_list : renvoie les logs du bon utilisateur, tri desc, limit
"""

import pytest

from apps.users.enums import AuditEvent, UserRole
from apps.users.models import SecurityAuditLog
from apps.users.selectors import (
    audit_log_list,
    profile_get,
    user_get,
    user_get_by_email,
    user_get_login_data,
    user_get_with_profile,
    user_list,
    user_list_for_admin,
)
from apps.users.tests.factories import (
    AdminUserFactory,
    BaseUserFactory,
    InactiveUserFactory,
    ProfileFactory,
)


# ---------------------------------------------------------------------------
# user_get_login_data
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_user_get_login_data_returns_expected_keys():
    # Arrange
    user = BaseUserFactory()

    # Act
    data = user_get_login_data(user=user)

    # Assert
    assert data["id"] == user.id
    assert data["email"] == user.email
    assert data["role"] == user.role
    assert data["is_active"] is True
    assert data["is_verified"] is True
    assert "profile" in data


@pytest.mark.django_db
def test_user_get_login_data_includes_profile_fields_when_profile_exists():
    # Arrange
    user = BaseUserFactory()
    ProfileFactory(user=user, first_name="Jean", last_name="Dupont")

    # Act
    data = user_get_login_data(user=user)

    # Assert
    assert data["profile"]["first_name"] == "Jean"
    assert data["profile"]["last_name"] == "Dupont"


@pytest.mark.django_db
def test_user_get_login_data_returns_empty_profile_dict_when_no_profile():
    # Arrange
    user = BaseUserFactory()
    # No profile attached

    # Act
    data = user_get_login_data(user=user)

    # Assert
    assert data["profile"] == {}


# ---------------------------------------------------------------------------
# user_get
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_user_get_returns_user_when_found():
    # Arrange
    user = BaseUserFactory()

    # Act
    result = user_get(user.id)

    # Assert
    assert result is not None
    assert result.id == user.id


@pytest.mark.django_db
def test_user_get_returns_none_when_not_found():
    # Act
    result = user_get(999999)

    # Assert
    assert result is None


# ---------------------------------------------------------------------------
# user_get_by_email
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_user_get_by_email_returns_user_when_found():
    # Arrange
    user = BaseUserFactory(email="cible@example.com")

    # Act
    result = user_get_by_email("cible@example.com")

    # Assert
    assert result is not None
    assert result.id == user.id


@pytest.mark.django_db
def test_user_get_by_email_is_case_insensitive():
    # Arrange
    BaseUserFactory(email="cible@example.com")

    # Act
    result = user_get_by_email("CIBLE@EXAMPLE.COM")

    # Assert
    assert result is not None
    assert result.email == "cible@example.com"


@pytest.mark.django_db
def test_user_get_by_email_returns_none_when_not_found():
    # Act
    result = user_get_by_email("nobody@example.com")

    # Assert
    assert result is None


# ---------------------------------------------------------------------------
# user_get_with_profile
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_user_get_with_profile_returns_user_with_select_related():
    # Arrange
    user = BaseUserFactory()
    ProfileFactory(user=user, first_name="Sophie")

    # Act
    result = user_get_with_profile(user.id)

    # Assert
    assert result is not None
    assert result.id == user.id
    assert result.profile.first_name == "Sophie"


@pytest.mark.django_db
def test_user_get_with_profile_returns_none_when_not_found():
    # Act
    result = user_get_with_profile(999999)

    # Assert
    assert result is None


# ---------------------------------------------------------------------------
# user_list
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_user_list_returns_all_users_without_filters():
    # Arrange
    BaseUserFactory()
    BaseUserFactory()
    BaseUserFactory()

    # Act
    result = user_list()

    # Assert
    assert result.count() >= 3


@pytest.mark.django_db
def test_user_list_filtered_by_role():
    # Arrange
    BaseUserFactory(role=UserRole.FIDELE)
    BaseUserFactory(role=UserRole.FIDELE)
    AdminUserFactory()  # super_admin — should not appear in fidele filter

    # Act
    result = user_list(filters={"role": UserRole.FIDELE})

    # Assert
    assert result.count() >= 2
    assert all(u.role == UserRole.FIDELE for u in result)


@pytest.mark.django_db
def test_user_list_filtered_by_is_active_true():
    # Arrange
    active = BaseUserFactory()
    InactiveUserFactory()

    # Act
    result = user_list(filters={"is_active": True})

    # Assert
    assert all(u.is_active for u in result)
    assert any(u.id == active.id for u in result)


@pytest.mark.django_db
def test_user_list_filtered_by_is_active_false():
    # Arrange
    BaseUserFactory()
    inactive = InactiveUserFactory()

    # Act
    result = user_list(filters={"is_active": False})

    # Assert
    assert all(not u.is_active for u in result)
    assert any(u.id == inactive.id for u in result)


@pytest.mark.django_db
def test_user_list_filtered_by_exact_email():
    # Arrange
    target = BaseUserFactory(email="search@example.com")
    BaseUserFactory(email="other@example.com")

    # Act
    result = user_list(filters={"email": "search@example.com"})

    # Assert
    assert result.count() == 1
    assert result.first().id == target.id


@pytest.mark.django_db
def test_user_list_returns_empty_queryset_when_no_match():
    # Arrange
    BaseUserFactory(email="someone@example.com")

    # Act
    result = user_list(filters={"email": "nobody@example.com"})

    # Assert
    assert result.count() == 0


@pytest.mark.django_db
def test_user_list_with_none_filters_behaves_like_no_filters():
    # Arrange
    BaseUserFactory()

    # Act
    result = user_list(filters=None)

    # Assert
    assert result.count() >= 1


# ---------------------------------------------------------------------------
# user_list_for_admin
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_user_list_for_admin_includes_inactive_users():
    # Arrange
    BaseUserFactory()
    InactiveUserFactory()

    # Act
    result = user_list_for_admin()

    # Assert
    has_inactive = any(not u.is_active for u in result)
    assert has_inactive


@pytest.mark.django_db
def test_user_list_for_admin_filter_by_is_verified_false():
    # Arrange
    BaseUserFactory(is_verified=True)
    InactiveUserFactory()  # is_verified=False by factory default

    # Act
    result = user_list_for_admin(filters={"is_verified": False})

    # Assert
    assert result.count() >= 1
    assert all(not u.is_verified for u in result)


# ---------------------------------------------------------------------------
# profile_get
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_profile_get_returns_profile_when_exists():
    # Arrange
    user = BaseUserFactory()
    ProfileFactory(user=user, first_name="Luc")

    # Act
    result = profile_get(user=user)

    # Assert
    assert result is not None
    assert result.first_name == "Luc"


@pytest.mark.django_db
def test_profile_get_returns_none_when_no_profile():
    # Arrange
    user = BaseUserFactory()
    # No ProfileFactory called

    # Act
    result = profile_get(user=user)

    # Assert
    assert result is None


# ---------------------------------------------------------------------------
# audit_log_list
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_audit_log_list_returns_logs_for_correct_user():
    # Arrange
    user = BaseUserFactory()
    other = BaseUserFactory()
    SecurityAuditLog.objects.create(user=user, event=AuditEvent.LOGIN)
    SecurityAuditLog.objects.create(user=user, event=AuditEvent.LOGOUT)
    SecurityAuditLog.objects.create(user=other, event=AuditEvent.LOGIN)

    # Act
    result = list(audit_log_list(user=user))

    # Assert
    assert len(result) == 2
    assert all(log.user_id == user.id for log in result)


@pytest.mark.django_db
def test_audit_log_list_ordered_by_created_at_desc():
    # Arrange
    user = BaseUserFactory()
    SecurityAuditLog.objects.create(user=user, event=AuditEvent.LOGIN)
    SecurityAuditLog.objects.create(user=user, event=AuditEvent.LOGOUT)

    # Act
    result = list(audit_log_list(user=user))

    # Assert — most recent first
    assert result[0].created_at >= result[1].created_at


@pytest.mark.django_db
def test_audit_log_list_respects_limit():
    # Arrange
    user = BaseUserFactory()
    for _ in range(10):
        SecurityAuditLog.objects.create(user=user, event=AuditEvent.LOGIN)

    # Act
    result = list(audit_log_list(user=user, limit=3))

    # Assert
    assert len(result) == 3


@pytest.mark.django_db
def test_audit_log_list_returns_empty_list_when_no_logs():
    # Arrange
    user = BaseUserFactory()

    # Act
    result = list(audit_log_list(user=user))

    # Assert
    assert result == []
