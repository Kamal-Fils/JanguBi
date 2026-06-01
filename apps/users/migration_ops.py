"""Opérations réutilisables pour les migrations data de l'app users.

Fonctions à signature STABLE (injection des modèles, historiques ou réels) afin
d'être appelées depuis une migration ``RunPython`` ET testées directement avec
les modèles réels.
"""

from __future__ import annotations


def backfill_memberships(*, Profile, Church, Membership):
    """Crée une appartenance principale pour chaque ``Profile`` ayant une
    ``primary_parish``, pointée sur l'église PRINCIPALE (``is_main``) de la paroisse.

    DÉFENSIF : une paroisse sans église ``is_main`` est flaguée et sautée — jamais
    d'exception, jamais d'appartenance orpheline. Idempotent (``get_or_create`` sur
    user+church).

    Retourne ``(created_count, flagged)`` où ``flagged`` est une liste de dicts
    ``{"user_id", "parish_id", "parish_name"}`` à reprendre manuellement.
    """
    created = 0
    flagged: list[dict] = []

    profiles = (
        Profile.objects.exclude(primary_parish__isnull=True)
        .select_related("primary_parish")
        .iterator()
    )
    for profile in profiles:
        parish = profile.primary_parish
        main_church = Church.objects.filter(parish=parish, is_main=True).first()
        if main_church is None:
            flagged.append(
                {
                    "user_id": profile.user_id,
                    "parish_id": parish.id,
                    "parish_name": parish.name,
                }
            )
            continue
        _, was_created = Membership.objects.get_or_create(
            user_id=profile.user_id,
            church=main_church,
            defaults={"is_primary": True},
        )
        if was_created:
            created += 1

    return created, flagged
