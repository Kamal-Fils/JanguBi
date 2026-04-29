from urllib.parse import parse_qs

from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_jwt.settings import api_settings


@database_sync_to_async
def _get_user_from_token(token: str):
    try:
        payload = api_settings.JWT_DECODE_HANDLER(token)
        user_id = api_settings.JWT_PAYLOAD_GET_USER_ID_HANDLER(payload)

        from apps.users.models import BaseUser

        return BaseUser.objects.get(id=user_id, is_active=True)
    except Exception:
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
