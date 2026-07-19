"""
Réactions aux actualités (SRS : prier / amen / participer).

Trois invariants sont gardés ici, dans l'ordre de gravité :

1. **Unicité en base** — le compteur ne doit pas pouvoir mentir. La contrainte
   est testée au niveau SQL, pas seulement via le service : c'est elle qui tient
   quand deux requêtes concurrentes passent le `get_or_create` en même temps.
2. **Absence de N+1** — le fil est paginé ; un coût « par article » devient un
   coût « par page ». Le test compare le nombre de requêtes d'une page à 1
   article et d'une page à 12 : il doit être IDENTIQUE.
3. **Autorisation** — réagir suppose de pouvoir lire. Un article hors portée ne
   doit pas être réactible même quand on en devine l'UUID.
"""

import pytest
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.exceptions import ApplicationError
from apps.news.models import ArticleReaction
from apps.news.selectors import article_reaction_summary
from apps.news.services import article_reaction_set
from apps.org.tests.factories import ChurchFactory, ParishFactory
from apps.users.services_memberships import membership_create
from apps.users.tests.factories import BaseUserFactory

from .factories import (
    ArticleFactory,
    PublishedArticleFactory,
    PublishedParishArticleFactory,
)

PRAY = ArticleReaction.ReactionType.PRAY
AMEN = ArticleReaction.ReactionType.AMEN
ATTEND = ArticleReaction.ReactionType.ATTEND


def _member(church=None):
    """Fidèle rattaché à une église (donc à sa paroisse et son diocèse)."""
    user = BaseUserFactory()
    membership_create(user=user, church=church or ChurchFactory(), is_primary=True)
    return user


# ---------------------------------------------------------------------------
# 1. Unicité — en base, pas seulement en applicatif
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_unicite_est_garantie_par_la_base_et_pas_seulement_par_le_service():
    # Arrange — une réaction déjà posée.
    article = PublishedArticleFactory()
    user = _member()
    ArticleReaction.objects.create(article=article, user=user, reaction_type=PRAY)

    # Act & Assert — l'insertion brute du même triplet est refusée par la
    # contrainte : c'est ce qui protège du rejeu réseau, pas le code Python.
    with pytest.raises(IntegrityError), transaction.atomic():
        ArticleReaction.objects.create(article=article, user=user, reaction_type=PRAY)


@pytest.mark.django_db
def test_les_trois_types_coexistent_pour_un_meme_fidele():
    # Arrange
    article = PublishedArticleFactory()
    user = _member()

    # Act — « je prie » et « je participe » ne s'excluent pas.
    for reaction_type in (PRAY, AMEN, ATTEND):
        article_reaction_set(
            article_id=str(article.id),
            user=user,
            reaction_type=reaction_type,
            active=True,
        )

    # Assert
    assert ArticleReaction.objects.filter(article=article, user=user).count() == 3


# ---------------------------------------------------------------------------
# 2. Idempotence de la bascule
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_reposer_une_reaction_deja_posee_ne_double_pas_le_compteur():
    # Arrange
    article = PublishedArticleFactory()
    user = _member()

    # Act — rejeu de la même requête (double-clic / retry réseau).
    article_reaction_set(
        article_id=str(article.id), user=user, reaction_type=PRAY, active=True
    )
    summary = article_reaction_set(
        article_id=str(article.id), user=user, reaction_type=PRAY, active=True
    )

    # Assert — ni erreur, ni doublon.
    assert summary["counts"][PRAY] == 1
    assert ArticleReaction.objects.filter(article=article, reaction_type=PRAY).count() == 1


@pytest.mark.django_db
def test_retirer_une_reaction_absente_est_sans_effet():
    # Arrange
    article = PublishedArticleFactory()
    user = _member()

    # Act
    summary = article_reaction_set(
        article_id=str(article.id), user=user, reaction_type=AMEN, active=False
    )

    # Assert
    assert summary["counts"][AMEN] == 0
    assert summary["mine"] == []


@pytest.mark.django_db
def test_poser_puis_retirer_ramene_a_zero():
    # Arrange
    article = PublishedArticleFactory()
    user = _member()

    # Act
    article_reaction_set(
        article_id=str(article.id), user=user, reaction_type=ATTEND, active=True
    )
    summary = article_reaction_set(
        article_id=str(article.id), user=user, reaction_type=ATTEND, active=False
    )

    # Assert
    assert summary["counts"][ATTEND] == 0
    assert ATTEND not in summary["mine"]


@pytest.mark.django_db
def test_le_service_refuse_un_type_de_reaction_inconnu():
    # Arrange
    article = PublishedArticleFactory()
    user = _member()

    # Act & Assert — le service re-garde l'invariant même si le sérialiseur
    # a déjà validé : il peut être appelé directement (tâche, commande).
    with pytest.raises(ApplicationError):
        article_reaction_set(
            article_id=str(article.id), user=user, reaction_type="applaudir", active=True
        )


# ---------------------------------------------------------------------------
# 3. Autorisation — réagir suppose de pouvoir lire
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_impossible_de_reagir_a_un_article_hors_de_sa_portee():
    # Arrange — article d'une paroisse dont l'utilisateur n'est pas membre.
    article = PublishedParishArticleFactory(scope_parish=ParishFactory())
    outsider = _member()

    # Act & Assert — connaître l'UUID ne suffit pas.
    with pytest.raises(ApplicationError):
        article_reaction_set(
            article_id=str(article.id), user=outsider, reaction_type=PRAY, active=True
        )
    assert ArticleReaction.objects.count() == 0


@pytest.mark.django_db
def test_impossible_de_reagir_a_un_brouillon():
    # Arrange — un article non publié n'est lisible par personne dans le fil.
    article = ArticleFactory()  # status=draft, portée globale
    user = _member()

    # Act & Assert
    with pytest.raises(ApplicationError):
        article_reaction_set(
            article_id=str(article.id), user=user, reaction_type=PRAY, active=True
        )


@pytest.mark.django_db
def test_un_membre_de_la_paroisse_peut_reagir_a_son_article():
    # Arrange
    church = ChurchFactory()
    user = _member(church)
    article = PublishedParishArticleFactory(scope_parish=church.parish)

    # Act
    summary = article_reaction_set(
        article_id=str(article.id), user=user, reaction_type=PRAY, active=True
    )

    # Assert
    assert summary["counts"][PRAY] == 1
    assert summary["mine"] == [PRAY]


# ---------------------------------------------------------------------------
# 4. Sélecteur — compteurs et état du lecteur
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_le_resume_distingue_le_compte_total_et_mes_propres_reactions():
    # Arrange — deux fidèles prient, un seul participe.
    article = PublishedArticleFactory()
    me, other = _member(), _member()
    for user in (me, other):
        ArticleReaction.objects.create(article=article, user=user, reaction_type=PRAY)
    ArticleReaction.objects.create(article=article, user=other, reaction_type=ATTEND)

    # Act
    summary = article_reaction_summary(article=article, user=me)

    # Assert — le compteur est global, « mine » est personnel.
    assert summary["counts"] == {PRAY: 2, AMEN: 0, ATTEND: 1}
    assert summary["mine"] == [PRAY]


@pytest.mark.django_db
def test_un_visiteur_anonyme_voit_les_compteurs_sans_etat_personnel():
    # Arrange
    from django.contrib.auth.models import AnonymousUser

    article = PublishedArticleFactory()
    ArticleReaction.objects.create(article=article, user=_member(), reaction_type=AMEN)

    # Act
    summary = article_reaction_summary(article=article, user=AnonymousUser())

    # Assert
    assert summary["counts"][AMEN] == 1
    assert summary["mine"] == []


# ---------------------------------------------------------------------------
# 5. LE test de non-régression : pas de N+1 sur la liste paginée
# ---------------------------------------------------------------------------


def _queries_for_feed(client, url) -> int:
    with CaptureQueriesContext(connection) as captured:
        response = client.get(url)
    assert response.status_code == 200
    return len(captured.captured_queries)


@pytest.mark.django_db
def test_le_fil_ne_fait_pas_de_n_plus_1_sur_les_reactions():
    """Le nombre de requêtes ne doit PAS dépendre du nombre d'articles.

    C'est le piège de cette fonctionnalité : compteurs et « ai-je réagi ? » sont
    des données « par article », donc la tentation est de les lire depuis le
    sérialiseur — ce qui coûte une requête par carte du fil.

    On ne fige pas un nombre absolu (fragile, il dépend de l'auth et des
    appartenances) : on compare une page à 1 article et une page à 12. Toute
    lecture par article rendrait le second nombre strictement plus grand.
    """
    # Arrange — un fidèle, sa paroisse, et des réacteurs.
    church = ChurchFactory()
    me = _member(church)
    others = [_member(church) for _ in range(3)]

    client = APIClient()
    client.force_authenticate(me)
    url = reverse("api:news:feed")

    first = PublishedParishArticleFactory(scope_parish=church.parish)
    for user in others:
        ArticleReaction.objects.create(article=first, user=user, reaction_type=PRAY)
    ArticleReaction.objects.create(article=first, user=me, reaction_type=AMEN)

    # Préchauffage : la toute première requête paie des lectures ponctuelles
    # (schéma, contenttypes) qui n'ont rien à voir avec la pagination.
    _queries_for_feed(client, url)
    baseline = _queries_for_feed(client, url)

    # Act — on passe de 1 à 12 articles, chacun avec des réactions.
    for _ in range(11):
        article = PublishedParishArticleFactory(scope_parish=church.parish)
        for user in others:
            ArticleReaction.objects.create(
                article=article, user=user, reaction_type=ATTEND
            )

    with_twelve = _queries_for_feed(client, url)

    # Assert — même coût pour 12 articles que pour 1.
    response = client.get(url)
    assert len(response.data["results"]) == 12
    assert with_twelve == baseline, (
        f"N+1 détecté : {baseline} requête(s) pour 1 article, "
        f"{with_twelve} pour 12."
    )


@pytest.mark.django_db
def test_le_fil_expose_compteurs_et_etat_utilisateur_sans_appel_supplementaire():
    # Arrange
    church = ChurchFactory()
    me = _member(church)
    other = _member(church)
    article = PublishedParishArticleFactory(scope_parish=church.parish)
    ArticleReaction.objects.create(article=article, user=me, reaction_type=PRAY)
    ArticleReaction.objects.create(article=article, user=other, reaction_type=PRAY)

    client = APIClient()
    client.force_authenticate(me)

    # Act
    response = client.get(reverse("api:news:feed"))

    # Assert — tout est dans la charge utile de la liste.
    payload = response.data["results"][0]
    assert payload["reactions"]["counts"][PRAY] == 2
    assert payload["reactions"]["mine"] == [PRAY]


# ---------------------------------------------------------------------------
# 6. API
# ---------------------------------------------------------------------------


def _reaction_url(article):
    return reverse("api:news:reaction-set", kwargs={"article_id": article.id})


@pytest.mark.django_db
def test_endpoint_reaction_exige_une_authentification():
    article = PublishedArticleFactory()
    response = APIClient().post(
        _reaction_url(article), {"reaction_type": PRAY, "active": True}, format="json"
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_endpoint_reaction_pose_la_reaction_et_renvoie_l_etat_reconcilie():
    # Arrange
    article = PublishedArticleFactory()
    user = _member()
    client = APIClient()
    client.force_authenticate(user)

    # Act
    response = client.post(
        _reaction_url(article), {"reaction_type": ATTEND, "active": True}, format="json"
    )

    # Assert
    assert response.status_code == 200
    assert response.data["counts"][ATTEND] == 1
    assert response.data["mine"] == [ATTEND]


@pytest.mark.django_db
def test_endpoint_reaction_retire_la_reaction():
    # Arrange
    article = PublishedArticleFactory()
    user = _member()
    ArticleReaction.objects.create(article=article, user=user, reaction_type=PRAY)
    client = APIClient()
    client.force_authenticate(user)

    # Act
    response = client.post(
        _reaction_url(article), {"reaction_type": PRAY, "active": False}, format="json"
    )

    # Assert
    assert response.status_code == 200
    assert response.data["counts"][PRAY] == 0
    assert not ArticleReaction.objects.filter(article=article, user=user).exists()


@pytest.mark.django_db
def test_endpoint_reaction_rejette_un_type_inconnu_en_400():
    article = PublishedArticleFactory()
    client = APIClient()
    client.force_authenticate(_member())

    response = client.post(
        _reaction_url(article),
        {"reaction_type": "applaudir", "active": True},
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_endpoint_reaction_refuse_un_article_hors_portee_sans_reveler_son_existence():
    # Arrange
    article = PublishedParishArticleFactory(scope_parish=ParishFactory())
    client = APIClient()
    client.force_authenticate(_member())

    # Act
    response = client.post(
        _reaction_url(article), {"reaction_type": PRAY, "active": True}, format="json"
    )

    # Assert — message unique, non énumérant (ni « existe mais interdit », ni
    # « n'existe pas » : le client ne peut pas distinguer les deux).
    assert response.status_code == 400
    assert "portée" in response.data["detail"]


@pytest.mark.django_db
def test_le_detail_d_article_expose_les_reactions():
    # Arrange
    article = PublishedArticleFactory()
    user = _member()
    ArticleReaction.objects.create(article=article, user=user, reaction_type=AMEN)
    client = APIClient()
    client.force_authenticate(user)

    # Act
    response = client.get(reverse("api:news:detail", kwargs={"article_id": article.id}))

    # Assert
    assert response.status_code == 200
    assert response.data["reactions"]["counts"][AMEN] == 1
    assert response.data["reactions"]["mine"] == [AMEN]
