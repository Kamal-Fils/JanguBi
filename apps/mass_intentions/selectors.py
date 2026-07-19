from django.db.models import QuerySet
from django.http import Http404

from .models import MassIntention

# Rôles pastoraux habilités à traiter les intentions d'une paroisse. Source de
# vérité unique : ``apis.py`` importe cette constante, pour que la garde de rôle
# (HTTP) et la garde de périmètre (selectors/services) ne puissent pas diverger.
CLERGY_PASTORAL_ROLES = frozenset({"pretre", "eveque", "archeveque"})


def pretre_accessible_parish_ids(*, user) -> set[int] | None:
    """Périmètre territorial d'un membre du clergé sur les intentions de messe.

    Renvoie ``None`` pour « aucune restriction » (admin global / super_admin),
    sinon un ``set`` d'IDs de paroisses — **potentiellement vide**, auquel cas
    l'utilisateur ne peut traiter AUCUNE intention (fail-closed).

    Le périmètre est l'union de deux sources, volontairement :

    * ``accessible_parish_ids`` (``apps.users.scoping``) — l'autorité réelle
      dérivée des ``RoleAssignment`` actifs, y compris l'héritage
      église → paroisse → diocèse → province. C'est la source de vérité RBAC,
      la même que celle d'``apps/documents``.
    * ``profile.primary_parish_id`` — la paroisse principale, seule source
      utilisée jusqu'ici par ``mass_intention_list_pending``. On la conserve
      pour ne pas retirer l'accès aux curés déjà en place qui n'ont pas encore
      de ``RoleAssignment`` (le backfill est partiel) : sans elle, le correctif
      de sécurité se transformerait en panne fonctionnelle.

    ⚠ Ce second apport est **réservé au clergé** (``CLERGY_PASTORAL_ROLES``).
    Appliqué à tout le monde, il donnerait à n'importe quel fidèle un périmètre
    de lecture sur toute sa propre paroisse — donc sur les ``intention_text``
    de ses voisins. L'autorité issue des ``RoleAssignment``, elle, est déjà
    intrinsèquement fiable et reste offerte à tous (un ``parish_admin`` laïc
    est légitime).

    L'union est sûre : elle n'élargit jamais au-delà de paroisses réellement
    rattachées à l'utilisateur, et ne peut pas dégénérer en « tout ».
    """
    from apps.users.scoping import accessible_parish_ids, is_global_admin

    if is_global_admin(user):
        return None

    parish_ids: set[int] = set(accessible_parish_ids(user) or set())

    if getattr(user, "pastoral_role", None) in CLERGY_PASTORAL_ROLES:
        profile = getattr(user, "profile", None)
        primary_parish_id = getattr(profile, "primary_parish_id", None)
        if primary_parish_id:
            parish_ids.add(primary_parish_id)

    return parish_ids


def mass_intention_list_for_requestor(*, requestor) -> QuerySet[MassIntention]:
    return MassIntention.objects.filter(requestor=requestor).select_related("pretre", "parish")


def mass_intention_list_for_parish(*, parish_id: int) -> QuerySet[MassIntention]:
    return MassIntention.objects.filter(parish_id=parish_id).select_related(
        "requestor", "pretre", "parish"
    )


def mass_intention_list_pending(*, pretre=None) -> QuerySet[MassIntention]:
    """Intentions en attente, restreintes au périmètre territorial de ``pretre``.

    Fail-closed : un membre du clergé sans périmètre déterminable (ni
    ``RoleAssignment``, ni paroisse principale) ne voit RIEN — auparavant
    l'absence de ``primary_parish`` retirait tout filtre et exposait les
    intentions (dont ``intention_text``) de tout le pays.
    """
    qs = MassIntention.objects.filter(status="pending").select_related(
        "requestor", "pretre", "parish"
    )
    if pretre is None:
        return qs

    parish_ids = pretre_accessible_parish_ids(user=pretre)
    if parish_ids is None:  # admin global — aucune restriction
        return qs
    if not parish_ids:  # aucun périmètre → aucun accès
        return qs.none()
    return qs.filter(parish_id__in=parish_ids)


def mass_intention_get(*, intention_id: int, user) -> MassIntention:
    """Récupère une intention **scopée à ce que ``user`` a le droit de voir**.

    Trois portes d'entrée légitimes : le fidèle auteur de l'intention, un admin
    global, et un membre du clergé ayant autorité territoriale sur la paroisse
    de l'intention.

    Hors de ces cas → ``Http404`` (et non 403), comme
    ``document_request_get_for_admin`` : révéler « cette intention existe mais
    elle ne vous appartient pas » divulguerait déjà de l'information sur une
    autre paroisse. Une intention sans paroisse rattachée n'est traitable que
    par un admin global (fail-closed).
    """
    obj = (
        MassIntention.objects.select_related("requestor", "pretre", "parish")
        .filter(id=intention_id)
        .first()
    )
    if obj is None:
        raise Http404

    if obj.requestor_id == getattr(user, "id", None):
        return obj

    parish_ids = pretre_accessible_parish_ids(user=user)
    if parish_ids is None:  # admin global
        return obj
    if obj.parish_id is None or obj.parish_id not in parish_ids:
        raise Http404
    return obj
