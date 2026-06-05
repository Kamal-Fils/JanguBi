from datetime import date

from django.db.models import Case, IntegerField, QuerySet, Value, When
from django.utils import timezone

from apps.spiritual.models import PastoralReflection
from apps.users.models import BaseUser

# Priorité de spécificité : on sert la réflexion la PLUS ciblée pour l'utilisateur
# (église > paroisse > diocèse > global).
_SCOPE_PRIORITY = Case(
    When(scope_type=PastoralReflection.ScopeType.CHURCH, then=Value(0)),
    When(scope_type=PastoralReflection.ScopeType.PARISH, then=Value(1)),
    When(scope_type=PastoralReflection.ScopeType.DIOCESE, then=Value(2)),
    When(scope_type=PastoralReflection.ScopeType.GLOBAL, then=Value(3)),
    default=Value(9),
    output_field=IntegerField(),
)


def _base_qs() -> QuerySet[PastoralReflection]:
    return PastoralReflection.objects.select_related(
        "author", "author__profile", "scope_parish", "scope_diocese", "scope_church"
    )


def reflection_today_for_user(
    *, user: BaseUser, on_date: date | None = None
) -> PastoralReflection | None:
    """Réflexion du jour la plus pertinente pour l'utilisateur, selon ses
    appartenances (global ∪ église ∪ paroisse ∪ diocèse via get_scoped_queryset)."""
    from apps.users.scoping import get_scoped_queryset

    on_date = on_date or timezone.localdate()
    qs = _base_qs().filter(reflection_date=on_date)
    qs = get_scoped_queryset(qs, user)
    qs = qs.annotate(_priority=_SCOPE_PRIORITY).order_by("_priority", "-created_at")
    return qs.first()


def reflection_my_today(
    *, user: BaseUser, on_date: date | None = None
) -> PastoralReflection | None:
    """Réflexion écrite par l'utilisateur (auteur) pour la date donnée."""
    on_date = on_date or timezone.localdate()
    return _base_qs().filter(author=user, reflection_date=on_date).first()


def reflection_get(*, reflection_id) -> PastoralReflection | None:
    try:
        return _base_qs().get(pk=reflection_id)
    except PastoralReflection.DoesNotExist:
        return None


def reflection_list_for_user(*, user: BaseUser) -> QuerySet[PastoralReflection]:
    """Historique des réflexions visibles par l'utilisateur (toutes dates), scopé
    à ses appartenances."""
    from apps.users.scoping import get_scoped_queryset

    qs = get_scoped_queryset(_base_qs(), user)
    return qs.order_by("-reflection_date", "-created_at")
