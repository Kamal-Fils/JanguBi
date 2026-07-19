"""Inventaire des comptes administrateurs sans affectation territoriale.

À exécuter AVANT et APRÈS le durcissement du cloisonnement (`user_list`
fail-closed, gardes sur activation/anonymisation).

Contexte : `user_create_by_admin` ne crée aucune `RoleAssignment` — seule
`apis_roles.py` (ou une invitation clergé) en pose une. Tant que la liste des
utilisateurs était fail-open, ces comptes voyaient toute la plateforme, ce qui
masquait le problème. En fail-closed, ils ne voient plus qu'eux-mêmes : cette
commande dit exactement QUI est concerné, pour qu'on leur attribue leur
périmètre réel plutôt que de découvrir la régression en production.

Lecture seule — n'écrit rien.
"""

from django.core.management.base import BaseCommand

from apps.users.enums import UserRole
from apps.users.models import BaseUser
from apps.users.scoping import accessible_parish_ids, is_global_admin

ADMIN_ROLES = [
    UserRole.PROVINCE_ADMIN,
    UserRole.DIOCESE_ADMIN,
    UserRole.PARISH_ADMIN,
    UserRole.CHURCH_ADMIN,
]


class Command(BaseCommand):
    help = (
        "Liste les comptes administrateurs (hors super_admin) dépourvus "
        "d'affectation territoriale active — ils ne verront plus aucun "
        "utilisateur une fois le cloisonnement fail-closed appliqué."
    )

    def handle(self, *args, **options):
        admins = (
            BaseUser.objects.filter(role__in=ADMIN_ROLES, is_active=True)
            .select_related("profile")
            .order_by("role", "email")
        )

        orphelins = []
        for admin in admins:
            if is_global_admin(admin):
                continue
            if not accessible_parish_ids(admin):
                orphelins.append(admin)

        total = admins.count()
        self.stdout.write(f"Administrateurs actifs examinés : {total}")

        if not orphelins:
            self.stdout.write(
                self.style.SUCCESS(
                    "Aucun compte sans affectation territoriale : le passage en "
                    "fail-closed ne prive personne de son périmètre."
                )
            )
            self._report_clergy_without_scope()
            return

        self.stdout.write(
            self.style.WARNING(
                f"\n{len(orphelins)} compte(s) sans affectation territoriale active. "
                "En fail-closed, ils ne verront plus qu'eux-mêmes tant qu'une "
                "RoleAssignment ne leur est pas attribuée :"
            )
        )
        for admin in orphelins:
            self.stdout.write(f"  - {admin.email}  (rôle : {admin.role})")

        self.stdout.write(
            "\nAttribuer un périmètre via l'API d'affectation des rôles "
            "(apps/users/apis_roles.py) — ne pas rétablir le fail-open."
        )

        self._report_clergy_without_scope()

    def _report_clergy_without_scope(self):
        """Clergé sans périmètre : même risque sur les intentions de messe.

        Le cloisonnement des intentions retient l'union « RoleAssignment ∪
        paroisse principale ». Un prêtre dépourvu des deux ne verra plus aucune
        intention en attente, là où le fail-open lui montrait tout le pays.
        """
        from apps.mass_intentions.selectors import (
            CLERGY_PASTORAL_ROLES,
            pretre_accessible_parish_ids,
        )

        clergy = (
            BaseUser.objects.filter(
                pastoral_role__in=list(CLERGY_PASTORAL_ROLES), is_active=True
            )
            .select_related("profile")
            .order_by("email")
        )

        sans_perimetre = [
            membre
            for membre in clergy
            if pretre_accessible_parish_ids(user=membre) == set()
        ]

        self.stdout.write(f"\nMembres du clergé actifs examinés : {clergy.count()}")
        if not sans_perimetre:
            self.stdout.write(
                self.style.SUCCESS(
                    "Tous rattachés à au moins une paroisse : le cloisonnement "
                    "des intentions de messe ne prive personne."
                )
            )
            return

        self.stdout.write(
            self.style.WARNING(
                f"{len(sans_perimetre)} membre(s) du clergé sans paroisse rattachée — "
                "ils ne verront plus aucune intention de messe :"
            )
        )
        for membre in sans_perimetre:
            self.stdout.write(f"  - {membre.email}  ({membre.pastoral_role})")
