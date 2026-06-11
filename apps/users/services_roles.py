"""Services d'écriture pour les affectations de rôle scopées (RoleAssignment)."""

from __future__ import annotations

from datetime import date

from django.db import transaction

from apps.core.exceptions import ApplicationError
from apps.users.enums import RoleScope
from apps.users.models import RoleAssignment

_SCOPE_REQUIRED_FK: dict[str, str] = {
    RoleScope.PROVINCE: "province",
    RoleScope.DIOCESE: "diocese",
    RoleScope.PARISH: "parish",
    RoleScope.CHURCH: "church",
}


@transaction.atomic
def role_assignment_create(
    *,
    user,
    role: str,
    scope: str,
    province=None,
    diocese=None,
    parish=None,
    church=None,
    is_principal: bool = False,
    granted_by=None,
    start_date=None,
    end_date=None,
    note: str = "",
) -> RoleAssignment:
    # Cohérence scope ↔ entité territoriale.
    if scope != RoleScope.GLOBAL:
        required = _SCOPE_REQUIRED_FK[scope]
        provided = {"province": province, "diocese": diocese, "parish": parish, "church": church}[required]
        if provided is None:
            raise ApplicationError(f"Le niveau '{scope}' requiert de renseigner la {required}.")

    # Un seul curé principal actif par paroisse (respecte la contrainte d'unicité).
    if is_principal and scope == RoleScope.PARISH and parish is not None:
        RoleAssignment.objects.filter(
            parish=parish, scope=RoleScope.PARISH, is_principal=True, is_active=True
        ).update(is_principal=False)

    return RoleAssignment.objects.create(
        user=user,
        role=role,
        scope=scope,
        province=province,
        diocese=diocese,
        parish=parish,
        church=church,
        is_principal=is_principal,
        granted_by=granted_by,
        start_date=start_date,
        end_date=end_date,
        note=note,
        is_active=True,
    )


@transaction.atomic
def role_assignment_revoke(*, role_assignment: RoleAssignment) -> RoleAssignment:
    role_assignment.is_active = False
    if role_assignment.end_date is None:
        role_assignment.end_date = date.today()
    role_assignment.save(update_fields=["is_active", "end_date", "updated_at"])
    return role_assignment
