import logging
from urllib.parse import parse_qs

from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import UntypedToken

logger = logging.getLogger(__name__)


@database_sync_to_async
def _get_user_from_token(token: str):
    from apps.users.models import BaseUser

    try:
        validated = UntypedToken(token)  # validates signature + expiry via simplejwt defaults
        user_id = validated["user_id"]
        return BaseUser.objects.get(id=user_id, is_active=True)
    except (InvalidToken, TokenError, KeyError, BaseUser.DoesNotExist):
        return AnonymousUser()
    except Exception:
        logger.exception("Unexpected error while authenticating WebSocket JWT")
        return AnonymousUser()


class JwtAuthMiddleware:
    """
    Extracts JWT from ?token=<jwt> query param and populates scope["user"].
    Browsers cannot set Authorization headers on WebSocket connections.
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        query_string = scope.get("query_string", b"").decode()
        params = parse_qs(query_string)
        token = params.get("token", [None])[0]

        if token:
            scope["user"] = await _get_user_from_token(token)
        else:
            scope["user"] = AnonymousUser()

        return await self.inner(scope, receive, send)


def JwtAuthMiddlewareStack(inner):
    return JwtAuthMiddleware(AuthMiddlewareStack(inner))
