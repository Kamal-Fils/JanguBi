from collections import OrderedDict

from drf_spectacular.utils import inline_serializer
from rest_framework import serializers
from rest_framework.pagination import LimitOffsetPagination as _LimitOffsetPagination
from rest_framework.response import Response

# Mémoïsation par nom : inline_serializer crée une CLASSE distincte à chaque appel.
# Si le même serializer est wrappé par plusieurs endpoints (ex. ArticleListOutput sur
# global/parish/feed/…), on obtiendrait N classes « PaginatedArticleListOutputList »
# d'identités différentes → drf-spectacular : « identical names, different identities »
# → schéma incorrect. On réutilise donc une seule instance par nom.
_PAGINATED_SERIALIZER_CACHE: dict = {}


def paginated_response_serializer(serializer_class):
    """Sérialiseur de réponse paginée {limit, offset, count, next, previous, results}
    pour ``@extend_schema(responses=...)``.

    Les APIView appellent ``get_paginated_response`` manuellement — drf-spectacular ne
    sait pas l'introspecter et documente sinon une LISTE NUE. Sans ce wrapper, une
    régénération d'``api.ts`` reproduit le bug d'enveloppe (front attend ``{results}``,
    schéma annonce un tableau)."""
    base = serializer_class.__name__
    if base.endswith("Serializer"):
        base = base[: -len("Serializer")]
    name = f"Paginated{base}List"

    if name not in _PAGINATED_SERIALIZER_CACHE:
        _PAGINATED_SERIALIZER_CACHE[name] = inline_serializer(
            name=name,
            fields={
                "limit": serializers.IntegerField(),
                "offset": serializers.IntegerField(),
                "count": serializers.IntegerField(),
                "next": serializers.CharField(allow_null=True),
                "previous": serializers.CharField(allow_null=True),
                "results": serializer_class(many=True),
            },
        )
    return _PAGINATED_SERIALIZER_CACHE[name]


def get_paginated_response(*, pagination_class, serializer_class, queryset, request, view):
    paginator = pagination_class()

    page = paginator.paginate_queryset(queryset, request, view=view)

    if page is not None:
        serializer = serializer_class(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    serializer = serializer_class(queryset, many=True)

    return Response(data=serializer.data)


class LimitOffsetPagination(_LimitOffsetPagination):
    default_limit = 10
    max_limit = 50

    def get_paginated_data(self, data):
        return OrderedDict(
            [
                ("limit", self.limit),
                ("offset", self.offset),
                ("count", self.count),
                ("next", self.get_next_link()),
                ("previous", self.get_previous_link()),
                ("results", data),
            ]
        )

    def get_paginated_response(self, data):
        """
        We redefine this method in order to return `limit` and `offset`.
        This is used by the frontend to construct the pagination itself.
        """
        return Response(
            OrderedDict(
                [
                    ("limit", self.limit),
                    ("offset", self.offset),
                    ("count", self.count),
                    ("next", self.get_next_link()),
                    ("previous", self.get_previous_link()),
                    ("results", data),
                ]
            )
        )
