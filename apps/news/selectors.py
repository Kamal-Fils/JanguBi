from django.db.models import (
    Count,
    Exists,
    IntegerField,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    Value,
)
from django.db.models.functions import Coalesce

from apps.news.models import Article, ArticleCategory, ArticleReaction
from apps.users.models import BaseUser

REACTION_TYPES: tuple[str, ...] = tuple(ArticleReaction.ReactionType.values)


# ---------------------------------------------------------------------------
# Réactions — annotations (compteurs + état de l'utilisateur courant)
# ---------------------------------------------------------------------------


def _reaction_count_subquery(reaction_type: str) -> Coalesce:
    """Compteur d'un type de réaction, en SOUS-REQUÊTE agrégée.

    Volontairement pas un ``Count("reactions", filter=...)`` : celui-ci exige une
    jointure + GROUP BY sur la requête externe, ce qui (a) fait exploser les
    lignes si un autre join multi-valué est ajouté plus tard, et (b) transforme
    le ``COUNT(*)`` de la pagination en sous-requête enveloppante. La sous-requête
    agrégée reste inline dans le SELECT : elle est immunisée contre la
    multiplication de lignes et ne change pas la forme de la requête externe.
    """
    return Coalesce(
        Subquery(
            ArticleReaction.objects.filter(
                article=OuterRef("pk"), reaction_type=reaction_type
            )
            .order_by()
            .values("article")
            .annotate(total=Count("id"))
            .values("total")[:1],
            output_field=IntegerField(),
        ),
        Value(0),
    )


def annotate_reactions(qs: QuerySet[Article], *, viewer=None) -> QuerySet[Article]:
    """Attache compteurs par type + état du lecteur, **en une seule requête**.

    C'est le point sensible de la fonctionnalité : le fil est paginé, donc tout
    ce qui se calcule « par article » se paie N fois. Compteurs et état
    utilisateur arrivent donc par annotation (sous-requêtes corrélées inline),
    jamais par un accès en boucle depuis le sérialiseur.

    ``viewer`` anonyme (ou absent) → seuls les compteurs sont annotés ; l'état
    « mes réactions » est vide, ce qui est exactement la vérité pour un visiteur.
    """
    annotations: dict[str, object] = {
        f"reaction_{reaction_type}_count": _reaction_count_subquery(reaction_type)
        for reaction_type in REACTION_TYPES
    }

    if viewer is not None and getattr(viewer, "is_authenticated", False):
        for reaction_type in REACTION_TYPES:
            annotations[f"reaction_{reaction_type}_mine"] = Exists(
                ArticleReaction.objects.filter(
                    article=OuterRef("pk"), user=viewer, reaction_type=reaction_type
                )
            )

    return qs.annotate(**annotations)


def article_reaction_summary(*, article: Article, user=None) -> dict:
    """Compteurs + réactions du lecteur pour UN article (retour d'action).

    Utilisé après une bascule pour renvoyer l'état réconcilié au client, qui
    remplace alors sa mise à jour optimiste par la vérité serveur.
    """
    annotated = (
        annotate_reactions(Article.objects.filter(pk=article.pk), viewer=user)
        .values(
            *[f"reaction_{reaction_type}_count" for reaction_type in REACTION_TYPES],
            *(
                [f"reaction_{reaction_type}_mine" for reaction_type in REACTION_TYPES]
                if user is not None and getattr(user, "is_authenticated", False)
                else []
            ),
        )
        .first()
    ) or {}

    return {
        "counts": {
            reaction_type: annotated.get(f"reaction_{reaction_type}_count", 0) or 0
            for reaction_type in REACTION_TYPES
        },
        "mine": [
            reaction_type
            for reaction_type in REACTION_TYPES
            if annotated.get(f"reaction_{reaction_type}_mine", False)
        ],
    }


def article_get_reactable(*, article_id: str, user) -> Article | None:
    """Article sur lequel ``user`` a le DROIT de réagir, ou ``None``.

    On ne réinvente pas la règle : réagir suppose de pouvoir légitimement lire.
    On réutilise donc exactement le cloisonnement de lecture du fil
    (``get_scoped_queryset``) + la publication. Conséquence : un fidèle ne peut
    pas réagir au brouillon d'une autre paroisse en devinant son UUID.
    """
    from apps.users.scoping import get_scoped_queryset

    qs = Article.objects.filter(pk=article_id, status=Article.Status.PUBLISHED)
    return get_scoped_queryset(qs, user).first()


def category_list(*, active_only: bool = True) -> QuerySet[ArticleCategory]:
    qs = ArticleCategory.objects.all()
    if active_only:
        qs = qs.filter(is_active=True)
    return qs.order_by("display_order", "name")


def article_list(
    *,
    scope_type: str | None = None,
    scope_parish_id: int | None = None,
    scope_diocese_id: int | None = None,
    category_slug: str | None = None,
    status: str = Article.Status.PUBLISHED,
    author: BaseUser | None = None,
    search: str | None = None,
    content_type: str | None = None,
    viewer=None,
) -> QuerySet[Article]:
    # `author__profile` est préchargé parce que le sérialiseur de liste affiche
    # `author_name` via le profil : sans lui, chaque article de la page coûtait
    # une requête supplémentaire (N+1 préexistant, invisible tant que rien ne
    # comptait les requêtes).
    qs = Article.objects.select_related(
        "category", "author", "author__profile", "cover_image"
    )

    if status:
        qs = qs.filter(status=status)
    if scope_type:
        qs = qs.filter(scope_type=scope_type)
    if scope_parish_id is not None:
        qs = qs.filter(scope_parish_id=scope_parish_id)
    if scope_diocese_id is not None:
        qs = qs.filter(scope_diocese_id=scope_diocese_id)
    if category_slug:
        qs = qs.filter(category__slug=category_slug)
    if author is not None:
        qs = qs.filter(author=author)
    if search:
        qs = qs.filter(title__icontains=search)
    if content_type:
        qs = qs.filter(content_type=content_type)

    qs = annotate_reactions(qs, viewer=viewer)

    return qs.order_by("-published_at", "-created_at")


def article_list_for_editor(*, editor: BaseUser, **filters) -> QuerySet[Article]:
    """Articles visibles dans le back-office par `editor`, **scopés à son autorité**.

    La liste admin exposait auparavant TOUS les articles de la plateforme à tout
    éditeur — brouillons et lettres pastorales non publiées d'autres diocèses
    compris — alors que l'écriture, elle, est bien cloisonnée. On aligne la
    lecture sur l'autorité d'écriture : ce qu'on voit est ce sur quoi on peut
    agir, donc l'UI ne propose plus d'actions vouées à échouer.

    Fail-CLOSED : un éditeur sans affectation territoriale ne voit que ses
    propres articles.
    """
    from apps.users.scoping import (
        accessible_diocese_ids,
        accessible_parish_ids,
        accessible_province_ids,
        is_global_admin,
    )

    qs = article_list(**filters)

    if is_global_admin(editor):
        return qs

    visible = Q(author=editor)

    parish_ids = accessible_parish_ids(editor) or set()
    if parish_ids:
        visible |= Q(scope_type=Article.ScopeType.PARISH, scope_parish_id__in=parish_ids)
        # L'autorité « église » découle de celle sur sa paroisse (RG-CONT 3b).
        visible |= Q(
            scope_type=Article.ScopeType.CHURCH,
            scope_church__parish_id__in=parish_ids,
        )

    diocese_ids = accessible_diocese_ids(editor) or set()
    if diocese_ids:
        visible |= Q(scope_type=Article.ScopeType.DIOCESE, scope_diocese_id__in=diocese_ids)

    # La portée globale suit la même règle qu'à la publication : province+.
    if accessible_province_ids(editor):
        visible |= Q(scope_type=Article.ScopeType.GLOBAL)

    return qs.filter(visible)


def article_list_global(
    *,
    category_slug: str | None = None,
    search: str | None = None,
    content_type: str | None = None,
    viewer=None,
) -> QuerySet[Article]:
    """Articles publiés de portée globale — accessibles publiquement."""
    return article_list(
        scope_type=Article.ScopeType.GLOBAL,
        category_slug=category_slug,
        search=search,
        content_type=content_type,
        viewer=viewer,
    )


def article_list_for_parish(
    *,
    parish_id: int,
    category_slug: str | None = None,
    search: str | None = None,
    content_type: str | None = None,
    viewer=None,
) -> QuerySet[Article]:
    """Articles publiés d'une paroisse précise."""
    return article_list(
        scope_type=Article.ScopeType.PARISH,
        scope_parish_id=parish_id,
        category_slug=category_slug,
        search=search,
        content_type=content_type,
        viewer=viewer,
    )


def article_list_for_diocese(
    *,
    diocese_id: int,
    category_slug: str | None = None,
    search: str | None = None,
    content_type: str | None = None,
    viewer=None,
) -> QuerySet[Article]:
    """Articles publiés d'un diocèse précis."""
    return article_list(
        scope_type=Article.ScopeType.DIOCESE,
        scope_diocese_id=diocese_id,
        category_slug=category_slug,
        search=search,
        content_type=content_type,
        viewer=viewer,
    )


def article_get(*, article_id: str, viewer=None) -> Article | None:
    try:
        return annotate_reactions(
            Article.objects.select_related(
                "category", "author", "author__profile", "cover_image", "unpublished_by"
            ),
            viewer=viewer,
        ).get(pk=article_id)
    except Article.DoesNotExist:
        return None


def article_get_by_slug(*, slug: str, viewer=None) -> Article | None:
    try:
        return annotate_reactions(
            Article.objects.select_related(
                "category", "author", "author__profile", "cover_image", "unpublished_by"
            ),
            viewer=viewer,
        ).get(slug=slug)
    except Article.DoesNotExist:
        return None


def article_list_for_user(
    *,
    user: BaseUser,
    scope_type: str | None = None,
    scope_id: int | None = None,
) -> QuerySet[Article]:
    """Articles publiés visibles par l'utilisateur selon ses appartenances
    (multi-appartenance, Chantier 3a) : agrégation global ∪ église ∪ paroisse ∪
    diocèse via le helper générique get_scoped_queryset.

    Filtre de portée optionnel : si ``scope_type`` est fourni, le fil est restreint
    à cette portée. Le narrow s'applique APRÈS get_scoped_queryset, donc il reste un
    sous-ensemble de ce que l'utilisateur peut déjà voir — il n'élargit JAMAIS le
    cloisonnement (un scope_id hors appartenances donne un résultat vide, pas une fuite)."""
    from apps.users.scoping import (
        SCOPE_CHURCH,
        SCOPE_DIOCESE,
        SCOPE_GLOBAL,
        SCOPE_PARISH,
        get_scoped_queryset,
    )

    qs = Article.objects.select_related(
        "category", "author", "author__profile", "cover_image"
    ).filter(status=Article.Status.PUBLISHED)
    qs = get_scoped_queryset(qs, user)
    # Le lecteur du fil EST l'utilisateur : compteurs + « mes réactions » sont
    # annotés ici, donc la carte d'article rend son état actif sans une requête
    # par article.
    qs = annotate_reactions(qs, viewer=user)

    if scope_type == SCOPE_GLOBAL:
        qs = qs.filter(scope_type=SCOPE_GLOBAL)
    elif scope_type == SCOPE_CHURCH and scope_id is not None:
        qs = qs.filter(scope_type=SCOPE_CHURCH, scope_church_id=scope_id)
    elif scope_type == SCOPE_PARISH and scope_id is not None:
        qs = qs.filter(scope_type=SCOPE_PARISH, scope_parish_id=scope_id)
    elif scope_type == SCOPE_DIOCESE and scope_id is not None:
        qs = qs.filter(scope_type=SCOPE_DIOCESE, scope_diocese_id=scope_id)

    return qs.order_by("-published_at", "-created_at")
