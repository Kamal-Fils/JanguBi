"""
Diffusions inter-clergé : livraison et cloisonnement territorial.

Deux défauts corrigés ici, l'un de livraison, l'autre d'autorisation.

**Livraison.** `clerical_message_inbox` ne filtrait que sur
`individual_recipient`. Or trois des quatre portées laissent ce champ vide par
construction : les diffusions étaient écrites en base et n'apparaissaient dans
AUCUNE boîte de réception. Un évêque adressant une consigne à son diocèse
recevait un 201, la voyait dans ses « envoyés », et personne ne la lisait
jamais — un échec parfaitement silencieux.

**Autorisation.** L'envoi ne vérifiait que le RÔLE, jamais le territoire :
`scope_id` venait du client sans contrôle. Un curé pouvait diffuser au clergé
de n'importe quel diocèse en incrémentant un identifiant.
"""

import pytest

from apps.core.exceptions import ApplicationError
from apps.messaging.models import ClergicalMessage
from apps.messaging.selectors import clerical_message_inbox
from apps.messaging.services import clerical_message_send
from apps.org.tests.factories import DioceseFactory, ParishFactory, ProvinceFactory
from apps.users.enums import PastoralRole, RoleScope, UserRole
from apps.users.models import Membership, RoleAssignment
from apps.users.tests.factories import BaseUserFactory

pytestmark = pytest.mark.django_db

Scope = ClergicalMessage.RecipientScope


def _clergy_in(*, parish, pastoral_role=PastoralRole.PRETRE):
    """Membre du clergé rattaché à `parish` par affectation ET appartenance —
    les deux sources que le sélecteur réunit."""
    user = BaseUserFactory(role=UserRole.FIDELE, pastoral_role=pastoral_role)
    RoleAssignment.objects.create(
        user=user,
        role=UserRole.PARISH_ADMIN,
        scope=RoleScope.PARISH,
        parish=parish,
        diocese=parish.diocese,
        province=parish.diocese.province,
        is_active=True,
    )
    Membership.objects.create(user=user, church=_main_church(parish))
    return user


def _main_church(parish):
    """Église principale de la paroisse, créée une seule fois.

    Une contrainte d'unicité (`unique_main_church_per_parish`) interdit deux
    églises principales : rattacher un second membre du clergé à la même
    paroisse doit réutiliser l'église existante, pas en créer une autre.
    """
    from apps.org.models import Church
    from apps.org.tests.factories import ChurchFactory

    existing = Church.objects.filter(parish=parish, is_main=True).first()
    return existing or ChurchFactory(parish=parish, is_main=True)


def _bishop_of(diocese):
    user = BaseUserFactory(role=UserRole.FIDELE, pastoral_role=PastoralRole.EVEQUE)
    RoleAssignment.objects.create(
        user=user,
        role=UserRole.DIOCESE_ADMIN,
        scope=RoleScope.DIOCESE,
        diocese=diocese,
        province=diocese.province,
        is_active=True,
    )
    return user


class TestBroadcastDelivery:
    def test_diocese_broadcast_reaches_clergy_of_that_diocese(self):
        """Le cas qui ne fonctionnait pas du tout."""
        # Arrange
        diocese = DioceseFactory()
        parish = ParishFactory(diocese=diocese)
        bishop = _bishop_of(diocese)
        priest = _clergy_in(parish=parish)

        # Act
        clerical_message_send(
            sender=bishop,
            subject="Consigne diocésaine",
            body="Corps du message",
            recipient_scope=Scope.DIOCESE_CLERGY,
            scope_id=diocese.id,
        )

        # Assert
        assert clerical_message_inbox(user=priest).count() == 1

    def test_parish_broadcast_reaches_clergy_of_that_parish(self):
        parish = ParishFactory()
        sender = _clergy_in(parish=parish)
        deacon = _clergy_in(parish=parish, pastoral_role=PastoralRole.DIACRE)

        clerical_message_send(
            sender=sender,
            subject="Réunion",
            body="Corps",
            recipient_scope=Scope.PARISH_CLERGY,
            scope_id=parish.id,
        )

        assert clerical_message_inbox(user=deacon).count() == 1

    def test_individual_message_still_works(self):
        """Le seul cas qui fonctionnait : il ne doit pas régresser."""
        parish = ParishFactory()
        sender = _clergy_in(parish=parish)
        recipient = _clergy_in(parish=ParishFactory())

        clerical_message_send(
            sender=sender,
            subject="Bonjour",
            body="Corps",
            recipient_scope=Scope.INDIVIDUAL,
            individual_recipient_id=recipient.id,
        )

        assert clerical_message_inbox(user=recipient).count() == 1


class TestBroadcastIsolation:
    def test_clergy_of_another_diocese_does_not_receive(self):
        """Le revers : livrer largement ne doit pas livrer à tout le monde."""
        diocese = DioceseFactory()
        bishop = _bishop_of(diocese)
        outsider = _clergy_in(parish=ParishFactory())  # autre diocèse

        clerical_message_send(
            sender=bishop,
            subject="Consigne",
            body="Corps",
            recipient_scope=Scope.DIOCESE_CLERGY,
            scope_id=diocese.id,
        )

        assert clerical_message_inbox(user=outsider).count() == 0

    def test_fidele_never_receives_a_clergy_broadcast(self):
        diocese = DioceseFactory()
        parish = ParishFactory(diocese=diocese)
        bishop = _bishop_of(diocese)
        fidele = BaseUserFactory(role=UserRole.FIDELE, pastoral_role=PastoralRole.FIDELE)
        Membership.objects.create(user=fidele, church=_main_church(parish))

        clerical_message_send(
            sender=bishop,
            subject="Consigne",
            body="Corps",
            recipient_scope=Scope.DIOCESE_CLERGY,
            scope_id=diocese.id,
        )

        assert clerical_message_inbox(user=fidele).count() == 0

    def test_province_broadcast_is_not_visible_to_priests(self):
        """Une diffusion aux évêques doit rester entre évêques : l'ouvrir au
        clergé de la province exposerait des échanges d'épiscopat."""
        province = ProvinceFactory()
        diocese = DioceseFactory(province=province)
        parish = ParishFactory(diocese=diocese)
        archbishop = BaseUserFactory(role=UserRole.FIDELE, pastoral_role=PastoralRole.ARCHEVEQUE)
        RoleAssignment.objects.create(
            user=archbishop,
            role=UserRole.PROVINCE_ADMIN,
            scope=RoleScope.PROVINCE,
            province=province,
            is_active=True,
        )
        priest = _clergy_in(parish=parish)

        clerical_message_send(
            sender=archbishop,
            subject="Entre évêques",
            body="Corps",
            recipient_scope=Scope.PROVINCE_BISHOPS,
            scope_id=province.id,
        )

        assert clerical_message_inbox(user=priest).count() == 0

    def test_sender_does_not_receive_their_own_broadcast(self):
        parish = ParishFactory()
        sender = _clergy_in(parish=parish)

        clerical_message_send(
            sender=sender,
            subject="Réunion",
            body="Corps",
            recipient_scope=Scope.PARISH_CLERGY,
            scope_id=parish.id,
        )

        assert clerical_message_inbox(user=sender).count() == 0


class TestSendAuthorization:
    def test_cannot_broadcast_to_a_foreign_diocese(self):
        """La faille d'autorisation : il suffisait de changer l'identifiant."""
        own_parish = ParishFactory()
        priest = _clergy_in(parish=own_parish)
        foreign_diocese = DioceseFactory()

        with pytest.raises(ApplicationError):
            clerical_message_send(
                sender=priest,
                subject="Intrusion",
                body="Corps",
                recipient_scope=Scope.DIOCESE_CLERGY,
                scope_id=foreign_diocese.id,
            )

    def test_cannot_broadcast_to_a_foreign_parish(self):
        priest = _clergy_in(parish=ParishFactory())
        foreign_parish = ParishFactory()

        with pytest.raises(ApplicationError):
            clerical_message_send(
                sender=priest,
                subject="Intrusion",
                body="Corps",
                recipient_scope=Scope.PARISH_CLERGY,
                scope_id=foreign_parish.id,
            )

    def test_broadcast_without_territory_is_rejected(self):
        priest = _clergy_in(parish=ParishFactory())

        with pytest.raises(ApplicationError):
            clerical_message_send(
                sender=priest,
                subject="Sans portée",
                body="Corps",
                recipient_scope=Scope.DIOCESE_CLERGY,
                scope_id=None,
            )

    def test_individual_message_without_recipient_is_rejected(self):
        """Sans destinataire NI portée, le message partait en 201 et
        n'atteignait personne — le mode d'échec que l'on élimine."""
        priest = _clergy_in(parish=ParishFactory())

        with pytest.raises(ApplicationError):
            clerical_message_send(
                sender=priest,
                subject="Orphelin",
                body="Corps",
                recipient_scope=Scope.INDIVIDUAL,
                individual_recipient_id=None,
            )

    def test_fidele_cannot_send(self):
        fidele = BaseUserFactory(role=UserRole.FIDELE, pastoral_role=PastoralRole.FIDELE)

        with pytest.raises(ApplicationError):
            clerical_message_send(
                sender=fidele,
                subject="Tentative",
                body="Corps",
                recipient_scope=Scope.PARISH_CLERGY,
                scope_id=1,
            )
