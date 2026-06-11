"""
Analytique scopée par rôle (lecture seule) — flux de dons + fidèles.

Un seul moteur d'agrégation, adaptatif selon le NIVEAU du demandeur :
- curé        → niveau « paroisse », classement spatial par ÉGLISE de sa/ses paroisse(s) ;
- évêque      → niveau « diocèse »,  classement par PAROISSE de son diocèse ;
- archevêque  → niveau « province », classement par DIOCÈSE de sa province ;
- super_admin → vue globale (niveau province, tous diocèses).

Le cloisonnement s'appuie sur les RoleAssignment actifs (province > diocèse > paroisse :
on prend le périmètre le plus large dont dispose l'utilisateur). Toutes les requêtes
restent bornées à ce périmètre — aucune donnée hors scope.
"""

from __future__ import annotations

from django.db.models import Count, Q, QuerySet, Sum
from django.db.models.functions import TruncDay, TruncMonth, TruncWeek

from apps.documents.models import DocumentRequest
from apps.donations.models import Donation, DonationType, PaymentProvider
from apps.mass_intentions.models import MassIntention, MassIntentionStatus
from apps.org.models import Church, Diocese, Parish, Province
from apps.users.enums import RoleScope
from apps.users.models import Membership, RoleAssignment
from apps.users.scoping import is_global_admin

_PENDING_DOC_STATUSES = ["submitted", "under_verification", "info_requested"]
_DOC_STATUS_LABELS = dict(DocumentRequest.Status.choices)
_INTENTION_STATUS_LABELS = dict(MassIntentionStatus.choices)

_TRUNC = {"day": TruncDay, "week": TruncWeek, "month": TruncMonth}
_TYPE_LABELS = dict(DonationType.choices)
_PROVIDER_LABELS = dict(PaymentProvider.choices)


# ---------------------------------------------------------------------------
# Résolution du contexte analytique (niveau + périmètre autorisé)
# ---------------------------------------------------------------------------

def resolve_analytics_context(user) -> dict | None:
    """Niveau analytique + périmètre du demandeur. ``None`` si aucune autorité
    territoriale (le fidèle n'a pas accès à l'analytique scopée)."""
    if is_global_admin(user):
        return {"level": "province", "entity": None, "scope": {}}

    ras = RoleAssignment.objects.filter(user=user, is_active=True)

    prov = ras.filter(scope=RoleScope.PROVINCE, province__isnull=False).first()
    if prov and prov.province_id is not None:
        p = Province.objects.filter(id=prov.province_id).first()
        return {
            "level": "province",
            "entity": {"id": p.id, "name": p.name} if p else None,
            "scope": {"province_ids": [prov.province_id]},
        }

    dio = ras.filter(scope=RoleScope.DIOCESE, diocese__isnull=False).first()
    if dio and dio.diocese_id is not None:
        d = Diocese.objects.filter(id=dio.diocese_id).first()
        return {
            "level": "diocese",
            "entity": {"id": d.id, "name": d.name} if d else None,
            "scope": {"diocese_ids": [dio.diocese_id]},
        }

    parish_ids = list(
        ras.filter(scope=RoleScope.PARISH, parish__isnull=False).values_list(
            "parish_id", flat=True
        )
    )
    church_ids = list(
        ras.filter(scope=RoleScope.CHURCH, church__isnull=False).values_list(
            "church_id", flat=True
        )
    )
    if church_ids:
        parish_ids += list(
            Church.objects.filter(id__in=church_ids).values_list("parish_id", flat=True)
        )
    parish_ids = sorted({pid for pid in parish_ids if pid})
    if parish_ids:
        entity = None
        if len(parish_ids) == 1:
            pa = Parish.objects.filter(id=parish_ids[0]).first()
            entity = {"id": pa.id, "name": pa.name} if pa else None
        return {"level": "parish", "entity": entity, "scope": {"parish_ids": parish_ids}}

    return None


# ---------------------------------------------------------------------------
# Helpers de scoping / filtrage
# ---------------------------------------------------------------------------

def _scope_donations(qs: QuerySet, scope: dict) -> QuerySet:
    if scope.get("province_ids"):
        return qs.filter(parish__diocese__province_id__in=scope["province_ids"])
    if scope.get("diocese_ids"):
        return qs.filter(parish__diocese_id__in=scope["diocese_ids"])
    if scope.get("parish_ids"):
        return qs.filter(parish_id__in=scope["parish_ids"])
    return qs  # global (super_admin)


def _filter_type(qs: QuerySet, donation_type: str | None) -> QuerySet:
    if not donation_type:
        return qs
    # Le « don libre » correspond aux dons SANS campagne (campaign NULL) en plus de
    # ceux explicitement typés free_donation (cf. donation_flow_for_parish existant).
    if donation_type == DonationType.FREE_DONATION:
        return qs.filter(
            Q(campaign__donation_type=donation_type) | Q(campaign__isnull=True)
        )
    return qs.filter(campaign__donation_type=donation_type)


def _ranking_fields(level: str) -> tuple[str, str, str]:
    """(id_field, name_field, ranking_level) selon le niveau."""
    return {
        "parish": ("church_id", "church__name", "church"),
        "diocese": ("parish_id", "parish__name", "parish"),
        "province": ("parish__diocese_id", "parish__diocese__name", "diocese"),
    }[level]


def _membership_scope_filter(scope: dict) -> Q:
    if scope.get("province_ids"):
        return Q(church__parish__diocese__province_id__in=scope["province_ids"])
    if scope.get("diocese_ids"):
        return Q(church__parish__diocese_id__in=scope["diocese_ids"])
    if scope.get("parish_ids"):
        return Q(church__parish_id__in=scope["parish_ids"])
    return Q()


def _total_units(level: str, scope: dict) -> int:
    """Nombre d'entités du grain de classement dans le périmètre (dénominateur
    du KPI « actives / total »)."""
    if level == "parish":
        qs_church = Church.objects.all()
        if scope.get("parish_ids"):
            qs_church = qs_church.filter(parish_id__in=scope["parish_ids"])
        return qs_church.count()
    if level == "diocese":
        qs_parish = Parish.objects.all()
        if scope.get("diocese_ids"):
            qs_parish = qs_parish.filter(diocese_id__in=scope["diocese_ids"])
        return qs_parish.count()
    qs_diocese = Diocese.objects.all()
    if scope.get("province_ids"):
        qs_diocese = qs_diocese.filter(province_id__in=scope["province_ids"])
    return qs_diocese.count()


# ---------------------------------------------------------------------------
# Moteur d'analytique
# ---------------------------------------------------------------------------

def donation_analytics(
    *,
    context: dict,
    since,
    until,
    granularity: str = "month",
    donation_type: str | None = None,
    status: str = "confirmed",
    provider: str | None = None,
) -> dict:
    """Renvoie un dict prêt à sérialiser : KPIs, série temporelle, ventilations
    (type, provider), classement spatial et flux de fidèles — bornés au périmètre."""
    level = context["level"]
    scope = context["scope"]
    granularity = granularity if granularity in _TRUNC else "month"

    scoped = _scope_donations(Donation.objects.filter(status=status), scope)
    base = scoped.filter(created_at__gte=since, created_at__lt=until)
    base = _filter_type(base, donation_type)
    if provider:
        base = base.filter(payment_provider=provider)

    total = base.aggregate(t=Sum("amount"))["t"] or 0
    count = base.count()

    # Période précédente de même durée (comparaison).
    span = until - since
    prev = _filter_type(
        scoped.filter(created_at__gte=since - span, created_at__lt=since),
        donation_type,
    )
    if provider:
        prev = prev.filter(payment_provider=provider)
    prev_total = prev.aggregate(t=Sum("amount"))["t"] or 0
    delta_pct = (
        round((float(total) - float(prev_total)) / float(prev_total) * 100, 1)
        if prev_total
        else None
    )

    denier_total = (
        base.filter(campaign__donation_type=DonationType.CHURCH_TITHE).aggregate(
            t=Sum("amount")
        )["t"]
        or 0
    )
    denier_rate = round(float(denier_total) / float(total) * 100, 1) if total else 0.0

    trunc = _TRUNC[granularity]
    series = [
        {
            "bucket": row["b"].date().isoformat() if row["b"] else None,
            "total": row["total"] or 0,
            "count": row["count"],
        }
        for row in base.annotate(b=trunc("created_at"))
        .values("b")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("b")
    ]

    by_type = [
        {
            "donation_type": row["campaign__donation_type"] or DonationType.FREE_DONATION,
            "label": _TYPE_LABELS.get(
                row["campaign__donation_type"] or DonationType.FREE_DONATION,
                "Don libre",
            ),
            "total": row["total"] or 0,
            "count": row["count"],
        }
        for row in base.values("campaign__donation_type").annotate(
            total=Sum("amount"), count=Count("id")
        )
    ]

    by_provider = [
        {
            "provider": row["payment_provider"],
            "label": _PROVIDER_LABELS.get(row["payment_provider"], row["payment_provider"]),
            "total": row["total"] or 0,
            "count": row["count"],
        }
        for row in base.values("payment_provider").annotate(
            total=Sum("amount"), count=Count("id")
        )
    ]

    id_field, name_field, ranking_level = _ranking_fields(level)
    ranking = [
        {
            "id": row[id_field],
            "name": row[name_field],
            "total": row["total"] or 0,
            "count": row["count"],
        }
        for row in base.values(id_field, name_field)
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("-total")
        if row[id_field] is not None
    ]

    total_units = _total_units(level, scope)
    active_units = sum(1 for r in ranking if r["total"])

    # Flux de fidèles (appartenances) sur le périmètre + nouveaux sur la période.
    memberships = Membership.objects.filter(_membership_scope_filter(scope))
    fideles = memberships.values("user").distinct().count()
    fideles_new = (
        memberships.filter(created_at__gte=since, created_at__lt=until)
        .values("user")
        .distinct()
        .count()
    )

    return {
        "level": level,
        "entity": context.get("entity"),
        "ranking_level": ranking_level,
        "period": {
            "from": since.isoformat(),
            "to": until.isoformat(),
            "granularity": granularity,
        },
        "kpis": {
            "donations_total": total,
            "donations_count": count,
            "donations_total_prev": prev_total,
            "delta_pct": delta_pct,
            "denier_rate": denier_rate,
            "fideles": fideles,
            "fideles_new": fideles_new,
            "active_units": active_units,
            "total_units": total_units,
        },
        "series": series,
        "by_type": by_type,
        "by_provider": by_provider,
        "ranking": ranking,
    }


# ---------------------------------------------------------------------------
# Matrice d'activité + files en souffrance (documents / intentions)
# ---------------------------------------------------------------------------

def _scope_docs(qs: QuerySet, scope: dict) -> QuerySet:
    if scope.get("province_ids"):
        return qs.filter(target_parish__diocese__province_id__in=scope["province_ids"])
    if scope.get("diocese_ids"):
        return qs.filter(target_parish__diocese_id__in=scope["diocese_ids"])
    if scope.get("parish_ids"):
        return qs.filter(target_parish_id__in=scope["parish_ids"])
    return qs


def _scope_intentions(qs: QuerySet, scope: dict) -> QuerySet:
    if scope.get("province_ids"):
        return qs.filter(parish__diocese__province_id__in=scope["province_ids"])
    if scope.get("diocese_ids"):
        return qs.filter(parish__diocese_id__in=scope["diocese_ids"])
    if scope.get("parish_ids"):
        return qs.filter(parish_id__in=scope["parish_ids"])
    return qs


def _scope_units(level: str, scope: dict) -> list[dict]:
    """Entités {id, name} du grain de classement présentes dans le périmètre
    (incluses même sans activité → on voit les unités « dormantes »)."""
    if level == "parish":
        qs_church = Church.objects.all()
        if scope.get("parish_ids"):
            qs_church = qs_church.filter(parish_id__in=scope["parish_ids"])
        return [{"id": c.id, "name": c.name} for c in qs_church.order_by("name")]
    if level == "diocese":
        qs_parish = Parish.objects.all()
        if scope.get("diocese_ids"):
            qs_parish = qs_parish.filter(diocese_id__in=scope["diocese_ids"])
        return [{"id": p.id, "name": p.name} for p in qs_parish.order_by("name")]
    qs_diocese = Diocese.objects.all()
    if scope.get("province_ids"):
        qs_diocese = qs_diocese.filter(province_id__in=scope["province_ids"])
    return [{"id": d.id, "name": d.name} for d in qs_diocese.order_by("name")]


def _by_status(qs: QuerySet, status_field: str, labels: dict) -> list[dict]:
    return [
        {
            "status": row[status_field],
            "label": labels.get(row[status_field], row[status_field]),
            "count": row["c"],
        }
        for row in qs.values(status_field).annotate(c=Count("id")).order_by("-c")
    ]


def activity_matrix(*, context: dict, since, until) -> dict:
    """Matrice d'activité par sous-entité du périmètre (paroisse pour l'évêque,
    diocèse pour l'archevêque, église pour le curé) + files EN SOUFFRANCE
    (documents/intentions courants, indépendants de la période). Croise tous les
    flux par unité → repérer la paroisse « rouge » qui décroche partout."""
    level = context["level"]
    scope = context["scope"]
    id_field, _name_field, grain = _ranking_fields(level)
    units = _scope_units(level, scope)

    don_qs = _scope_donations(
        Donation.objects.filter(status="confirmed"), scope
    ).filter(created_at__gte=since, created_at__lt=until)
    don_by = {
        r[id_field]: r["total"] or 0
        for r in don_qs.values(id_field).annotate(total=Sum("amount"))
        if r[id_field] is not None
    }

    memb_group = {
        "church": "church_id",
        "parish": "church__parish_id",
        "diocese": "church__parish__diocese_id",
    }[grain]
    memb_by = {
        r[memb_group]: r["c"]
        for r in Membership.objects.filter(_membership_scope_filter(scope))
        .values(memb_group)
        .annotate(c=Count("user", distinct=True))
        if r[memb_group] is not None
    }

    # Documents / intentions n'ont pas de dimension « église » → seulement aux
    # grains paroisse/diocèse (au grain église, ces colonnes restent à None).
    docs_by: dict = {}
    inten_by: dict = {}
    if grain in ("parish", "diocese"):
        doc_group = {"parish": "target_parish_id", "diocese": "target_parish__diocese_id"}[grain]
        docs_by = {
            r[doc_group]: r["c"]
            for r in _scope_docs(
                DocumentRequest.objects.filter(status__in=_PENDING_DOC_STATUSES), scope
            )
            .values(doc_group)
            .annotate(c=Count("id"))
            if r[doc_group] is not None
        }
        inten_group = {"parish": "parish_id", "diocese": "parish__diocese_id"}[grain]
        inten_by = {
            r[inten_group]: r["c"]
            for r in _scope_intentions(
                MassIntention.objects.filter(status=MassIntentionStatus.PENDING), scope
            )
            .values(inten_group)
            .annotate(c=Count("id"))
            if r[inten_group] is not None
        }

    rows = [
        {
            "id": u["id"],
            "name": u["name"],
            "donations_total": don_by.get(u["id"], 0),
            "fideles": memb_by.get(u["id"], 0),
            "documents_pending": docs_by.get(u["id"], 0) if grain != "church" else None,
            "intentions_pending": inten_by.get(u["id"], 0) if grain != "church" else None,
        }
        for u in units
    ]
    rows.sort(key=lambda r: r["donations_total"], reverse=True)

    docs_qs = _scope_docs(DocumentRequest.objects.all(), scope)
    inten_qs = _scope_intentions(MassIntention.objects.all(), scope)

    return {
        "level": level,
        "grain": grain,
        "rows": rows,
        "documents": {
            "by_status": _by_status(docs_qs, "status", _DOC_STATUS_LABELS),
            "pending": docs_qs.filter(status__in=_PENDING_DOC_STATUSES).count(),
            "total": docs_qs.count(),
        },
        "intentions": {
            "by_status": _by_status(inten_qs, "status", _INTENTION_STATUS_LABELS),
            "pending": inten_qs.filter(status=MassIntentionStatus.PENDING).count(),
            "total": inten_qs.count(),
        },
    }
