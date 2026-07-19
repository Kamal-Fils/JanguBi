from datetime import date

from django.db import transaction

from apps.core.exceptions import ApplicationError
from apps.spiritual.models import PastoralReflection
from apps.users.enums import PastoralRole
from apps.users.models import BaseUser

# Clergé pouvant PUBLIER une réflexion (matrice §16 : diacre/religieux EXCLUS).
_PUBLISHER_PASTORAL_ROLES = frozenset({
    PastoralRole.PRETRE,
    PastoralRole.EVEQUE,
    PastoralRole.ARCHEVEQUE,
})


def is_reflection_editor(user: BaseUser) -> bool:
    """Peut publier/éditer une réflexion : administrateur digital (user.role OU
    RoleAssignment) OU clergé publicateur (prêtre/évêque/archevêque). Diacre et
    religieux sont exclus (ils ne publient pas de réflexion, matrice §16)."""
    from apps.users.scoping import is_any_admin

    return is_any_admin(user) or user.pastoral_role in _PUBLISHER_PASTORAL_ROLES


def _check_editor(user: BaseUser) -> None:
    if not is_reflection_editor(user):
        raise ApplicationError("Seul le clergé (prêtre, évêque, archevêque) peut publier une réflexion.")


def _check_scope_consistency(
    scope_type: str,
    scope_parish_id: int | None,
    scope_diocese_id: int | None,
    scope_church_id: int | None,
) -> None:
    ST = PastoralReflection.ScopeType
    if scope_type == ST.PARISH and not scope_parish_id:
        raise ApplicationError("Une réflexion de portée 'paroisse' doit avoir un scope_parish_id.")
    if scope_type == ST.DIOCESE and not scope_diocese_id:
        raise ApplicationError("Une réflexion de portée 'diocèse' doit avoir un scope_diocese_id.")
    if scope_type == ST.CHURCH and not scope_church_id:
        raise ApplicationError("Une réflexion de portée 'église' doit avoir un scope_church_id.")
    if scope_type == ST.GLOBAL and (scope_parish_id or scope_diocese_id or scope_church_id):
        raise ApplicationError("Une réflexion globale ne doit pas porter de scope_parish/diocese/church_id.")


def _check_scope_authority(
    *,
    user: BaseUser,
    scope_type: str,
    scope_parish_id: int | None,
    scope_diocese_id: int | None,
    scope_church_id: int | None,
) -> None:
    """L'auteur doit avoir une autorité territoriale RÉELLE sur la portée — ferme
    l'injection inter-paroisses/diocèses (un curé de A ne publie pas sur B).

    Deux voies indépendantes, l'une suffit :
    - PASTORALE (``user_has_pastoral_authority``) : le prêtre publie sur SA
      paroisse du seul fait de sa charge. Un curé validé peut porter
      ``pastoral_role=PRETRE`` sans aucune ``RoleAssignment`` ; sans cette voie, la
      publication d'une réflexion — son acte propre — lui était refusée.
    - ADMINISTRATIVE (``RoleAssignment`` via ``user_can_admin_*``).

    Les deux sont fail-closed : la portée doit tomber dans un territoire réel.
    """
    from apps.users.scoping import (
        accessible_province_ids,
        is_global_admin,
        user_can_admin_church,
        user_can_admin_diocese,
        user_can_admin_parish,
        user_has_pastoral_authority,
    )

    if user_has_pastoral_authority(
        user=user,
        scope_type=scope_type,
        scope_parish_id=scope_parish_id,
        scope_diocese_id=scope_diocese_id,
        scope_church_id=scope_church_id,
        # Matrice §16 : le diacre et le religieux ne publient pas de réflexion.
        allowed_roles=_PUBLISHER_PASTORAL_ROLES,
    ):
        return

    ST = PastoralReflection.ScopeType
    if scope_type == ST.PARISH:
        if scope_parish_id is None or not user_can_admin_parish(user, scope_parish_id):
            raise ApplicationError("Vous n'avez pas autorité sur cette paroisse.")
    elif scope_type == ST.CHURCH:
        if scope_church_id is None or not user_can_admin_church(user, scope_church_id):
            raise ApplicationError("Vous n'avez pas autorité sur cette église.")
    elif scope_type == ST.DIOCESE:
        if scope_diocese_id is None or not user_can_admin_diocese(user, scope_diocese_id):
            raise ApplicationError("Vous n'avez pas autorité sur ce diocèse.")
    else:  # GLOBAL — réservé aux administrateurs province / national.
        if not (is_global_admin(user) or accessible_province_ids(user)):
            raise ApplicationError("La portée globale est réservée aux administrateurs province ou national.")


def _resolve_scope_targets(
    *,
    scope_parish_id: int | None,
    scope_diocese_id: int | None,
    scope_church_id: int | None,
):
    from apps.org.models import Church, Diocese, Parish

    parish = diocese = church = None
    if scope_parish_id is not None:
        parish = Parish.objects.filter(pk=scope_parish_id).first()
        if parish is None:
            raise ApplicationError("Paroisse introuvable.")
    if scope_diocese_id is not None:
        diocese = Diocese.objects.filter(pk=scope_diocese_id).first()
        if diocese is None:
            raise ApplicationError("Diocèse introuvable.")
    if scope_church_id is not None:
        church = Church.objects.filter(pk=scope_church_id).first()
        if church is None:
            raise ApplicationError("Église introuvable.")
    return parish, diocese, church


@transaction.atomic
def reflection_upsert(
    *,
    author: BaseUser,
    content: str,
    reflection_date: date,
    title: str = "",
    scope_type: str = PastoralReflection.ScopeType.PARISH,
    scope_parish_id: int | None = None,
    scope_diocese_id: int | None = None,
    scope_church_id: int | None = None,
) -> PastoralReflection:
    """Crée ou met à jour la réflexion de l'auteur pour une date (unique auteur+date)."""
    _check_editor(author)
    if not content or not content.strip():
        raise ApplicationError("Le contenu de la réflexion est obligatoire.")
    _check_scope_consistency(scope_type, scope_parish_id, scope_diocese_id, scope_church_id)
    _check_scope_authority(
        user=author,
        scope_type=scope_type,
        scope_parish_id=scope_parish_id,
        scope_diocese_id=scope_diocese_id,
        scope_church_id=scope_church_id,
    )
    scope_parish, scope_diocese, scope_church = _resolve_scope_targets(
        scope_parish_id=scope_parish_id,
        scope_diocese_id=scope_diocese_id,
        scope_church_id=scope_church_id,
    )

    reflection, _created = PastoralReflection.objects.update_or_create(
        author=author,
        reflection_date=reflection_date,
        defaults={
            "title": title,
            "content": content,
            "scope_type": scope_type,
            "scope_parish": scope_parish,
            "scope_diocese": scope_diocese,
            "scope_church": scope_church,
        },
    )
    return reflection


def _check_manage_authority(*, reflection: PastoralReflection, editor: BaseUser) -> None:
    """Qui peut modifier/supprimer une réflexion DÉJÀ publiée.

    Deux titres seulement : en être l'AUTEUR, ou porter l'autorité territoriale sur
    la portée de la réflexion (modération descendante — matrice §16 « Dépublier » :
    le prêtre sur son contenu, l'évêque sur son diocèse, l'archevêque sur sa
    province, le super-admin partout).

    On vérifie l'autorité sur la portée RÉELLE de la réflexion, et non un simple
    « est admin quelque part » : sinon l'admin de la paroisse A pourrait réécrire
    la réflexion de la paroisse B.
    """
    if reflection.author_id == editor.id:
        return
    _check_scope_authority(
        user=editor,
        scope_type=reflection.scope_type,
        scope_parish_id=reflection.scope_parish_id,
        scope_diocese_id=reflection.scope_diocese_id,
        scope_church_id=reflection.scope_church_id,
    )


@transaction.atomic
def reflection_update(
    *,
    reflection: PastoralReflection,
    editor: BaseUser,
    title: str | None = None,
    content: str | None = None,
    scope_type: str | None = None,
    scope_parish_id: int | None = None,
    scope_diocese_id: int | None = None,
    scope_church_id: int | None = None,
) -> PastoralReflection:
    """Édition d'une réflexion existante (auteur ou autorité sur sa portée).

    Seuls les champs fournis changent. L'auteur et la date ne sont jamais
    réattribués : ils forment l'identité de la réflexion (unique auteur+jour).
    Déplacer la portée exige l'autorité sur la NOUVELLE portée (fail-closed).
    """
    _check_manage_authority(reflection=reflection, editor=editor)

    if content is not None:
        if not content.strip():
            raise ApplicationError("Le contenu de la réflexion est obligatoire.")
        reflection.content = content
    if title is not None:
        reflection.title = title

    scope_changed = any(
        value is not None
        for value in (scope_type, scope_parish_id, scope_diocese_id, scope_church_id)
    )
    if scope_changed:
        ST = PastoralReflection.ScopeType
        new_scope_type = scope_type or reflection.scope_type

        # Une seule FK de portée peut être renseignée : celle du niveau courant.
        # Toute autre est remise à NULL, même si le client l'a envoyée — sinon une
        # réflexion « diocèse » pourrait repartir avec un scope_parish résiduel et
        # fuiter dans le feed d'une paroisse qui n'est plus la sienne.
        new_parish_id = new_diocese_id = new_church_id = None
        if new_scope_type == ST.PARISH:
            new_parish_id = (
                scope_parish_id if scope_parish_id is not None else reflection.scope_parish_id
            )
        elif new_scope_type == ST.DIOCESE:
            new_diocese_id = (
                scope_diocese_id if scope_diocese_id is not None else reflection.scope_diocese_id
            )
        elif new_scope_type == ST.CHURCH:
            new_church_id = (
                scope_church_id if scope_church_id is not None else reflection.scope_church_id
            )

        _check_scope_consistency(new_scope_type, new_parish_id, new_diocese_id, new_church_id)
        _check_scope_authority(
            user=editor,
            scope_type=new_scope_type,
            scope_parish_id=new_parish_id,
            scope_diocese_id=new_diocese_id,
            scope_church_id=new_church_id,
        )
        parish, diocese, church = _resolve_scope_targets(
            scope_parish_id=new_parish_id,
            scope_diocese_id=new_diocese_id,
            scope_church_id=new_church_id,
        )
        reflection.scope_type = new_scope_type
        reflection.scope_parish = parish
        reflection.scope_diocese = diocese
        reflection.scope_church = church

    reflection.save()
    return reflection


@transaction.atomic
def reflection_delete(*, reflection: PastoralReflection, editor: BaseUser) -> None:
    _check_manage_authority(reflection=reflection, editor=editor)
    reflection.delete()
