"""
Agrégats de tableaux de bord par rôle (lecture seule).

Chaque fonction renvoie un ``dict`` prêt à sérialiser. Le cloisonnement
territorial est appliqué par les vues via ``apps.users.scoping``.
"""

from __future__ import annotations

from django.db.models import Q, Sum
from django.utils import timezone

from apps.documents.models import DocumentRequest
from apps.donations.models import Donation
from apps.donations.selectors import donation_flow_for_parish
from apps.mass_intentions.models import MassIntention
from apps.org.models import Church, Diocese, Parish
from apps.users.enums import RoleScope
from apps.users.models import Membership, Profile, RoleAssignment
from apps.users.scoping import clergy_of_parish, parish_principal_cure

_ACTIVE_DOC_STATUSES = ["submitted", "under_verification", "info_requested", "validated"]


def _start_of_year():
    now = timezone.now()
    return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)


def _start_of_month():
    now = timezone.now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _parish_pending_documents(parish_id: int) -> int:
    # Cohérent avec la visibilité (confidentialité) : on compte les demandes dont la
    # paroisse CIBLE est celle-ci ; repli sur la paroisse principale du demandeur
    # seulement pour les demandes orphelines (target_parish NULL).
    return DocumentRequest.objects.filter(
        Q(target_parish_id=parish_id)
        | Q(
            target_parish_id__isnull=True,
            requester__profile__primary_parish_id=parish_id,
        ),
        status__in=_ACTIVE_DOC_STATUSES,
    ).count()


def cure_dashboard(*, parish_id: int) -> dict | None:
    """Tableau de bord du curé : sa paroisse, toutes églises confondues."""
    parish = Parish.objects.select_related("diocese").filter(id=parish_id).first()
    if parish is None:
        return None

    principal = parish_principal_cure(parish_id)
    principal_id = principal.id if principal else None
    clergy = [
        {
            "id": str(u.id),
            "email": u.email,
            "pastoral_role": u.pastoral_role,
            "is_principal": principal_id is not None and u.id == principal_id,
        }
        for u in clergy_of_parish(parish_id)
    ]

    return {
        "parish": {
            "id": parish.id,
            "name": parish.name,
            "city": parish.city,
            "diocese": parish.diocese.name,
        },
        "total_fideles": Profile.objects.filter(primary_parish_id=parish_id).count(),
        # Membres de la paroisse via appartenance (ex-followed_parishes retiré au 3a) :
        # fidèles distincts rattachés à une église de cette paroisse.
        "followers": (
            Membership.objects.filter(church__parish_id=parish_id)
            .values("user")
            .distinct()
            .count()
        ),
        "donation_flow_year": donation_flow_for_parish(parish_id=parish_id, since=_start_of_year()),
        "donation_flow_month": donation_flow_for_parish(parish_id=parish_id, since=_start_of_month()),
        "pending_documents": _parish_pending_documents(parish_id),
        "pending_intentions": MassIntention.objects.filter(
            parish_id=parish_id, status="pending"
        ).count(),
        "churches": list(
            Church.objects.filter(parish_id=parish_id).values(
                "id", "name", "church_type", "is_main", "is_active"
            )
        ),
        "clergy": clergy,
    }


def fidele_dashboard(*, user) -> dict:
    """Vue personnelle du fidèle : sa paroisse, ses demandes, ses dons."""
    parish_id = getattr(getattr(user, "profile", None), "primary_parish_id", None)
    parish = Parish.objects.filter(id=parish_id).first() if parish_id else None
    principal = parish_principal_cure(parish_id) if parish_id else None

    my_docs = DocumentRequest.objects.filter(requester=user)
    my_donations = Donation.objects.filter(donor=user, status="confirmed")

    return {
        "parish": (
            {"id": parish.id, "name": parish.name, "city": parish.city} if parish else None
        ),
        "principal_cure_email": principal.email if principal else None,
        "documents": {
            "total": my_docs.count(),
            "in_progress": my_docs.filter(status__in=_ACTIVE_DOC_STATUSES).count(),
            "deposited": my_docs.filter(status="document_deposited").count(),
        },
        "mass_intentions": MassIntention.objects.filter(requestor=user).count(),
        "donations": {
            "total": my_donations.aggregate(t=Sum("amount"))["t"] or 0,
            "count": my_donations.count(),
        },
    }


def diocese_dashboard(*, diocese_id: int) -> dict | None:
    """Consolidation diocésaine pour l'évêque."""
    diocese = Diocese.objects.select_related("province").filter(id=diocese_id).first()
    if diocese is None:
        return None

    parishes = Parish.objects.filter(diocese_id=diocese_id)
    donations_total = (
        Donation.objects.filter(status="confirmed", parish__diocese_id=diocese_id).aggregate(
            t=Sum("amount")
        )["t"]
        or 0
    )

    return {
        "diocese": {"id": diocese.id, "name": diocese.name, "province": diocese.province.name},
        "parishes_count": parishes.count(),
        "total_fideles": Profile.objects.filter(primary_parish__diocese_id=diocese_id).count(),
        "donations_total": donations_total,
        # Alerte qualité de données : paroisses sans église principale.
        "parishes_without_main_church": parishes.exclude(churches__is_main=True).count(),
        "pending_documents": DocumentRequest.objects.filter(
            Q(target_parish__diocese_id=diocese_id)
            | Q(
                target_parish_id__isnull=True,
                requester__profile__primary_parish__diocese_id=diocese_id,
            ),
            status__in=_ACTIVE_DOC_STATUSES,
        ).count(),
    }


def user_principal_parish_id(*, user) -> int | None:
    """Paroisse où l'utilisateur est administrateur (curé), principale en priorité."""
    ra = (
        RoleAssignment.objects.filter(user=user, scope=RoleScope.PARISH, is_active=True)
        .order_by("-is_principal")
        .first()
    )
    return ra.parish_id if ra else None


def user_principal_diocese_id(*, user) -> int | None:
    """Diocèse où l'utilisateur est administrateur (évêque / admin diocèse)."""
    ra = RoleAssignment.objects.filter(
        user=user, scope=RoleScope.DIOCESE, is_active=True
    ).first()
    if ra and ra.diocese_id:
        return ra.diocese_id
    if getattr(user, "pastoral_role", None) in ("eveque", "archeveque"):
        return getattr(user, "diocese_id", None)
    return None
