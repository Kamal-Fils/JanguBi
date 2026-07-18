import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.django.base")

# Must be called before importing channels routing (triggers Django setup)
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import (  # noqa: E402
    AllowedHostsOriginValidator,
    OriginValidator,
)
from django.conf import settings  # noqa: E402

from apps.messaging.middleware import JwtAuthMiddlewareStack  # noqa: E402
from apps.messaging.routing import websocket_urlpatterns  # noqa: E402
from apps.rosary.routing import rosary_websocket_urlpatterns  # noqa: E402

_ws_stack = JwtAuthMiddlewareStack(URLRouter(websocket_urlpatterns + rosary_websocket_urlpatterns))

# L'Origin d'un handshake WebSocket est le domaine du FRONT (ex.
# https://jangubi.kamalfils.app), pas celui de l'API. AllowedHostsOriginValidator
# compare l'Origin à ALLOWED_HOSTS (= domaine API en prod) → tout WS cross-origin
# était rejeté au handshake en production. Quand WS_ALLOWED_ORIGINS est défini
# (prod : fallback sur CORS_ALLOWED_ORIGINS), on valide contre cette liste
# explicite ; sinon comportement historique (dev : ALLOWED_HOSTS=["*"] → permissif).
_ws_origins = list(getattr(settings, "WS_ALLOWED_ORIGINS", []) or [])
if _ws_origins:
    _websocket_app = OriginValidator(_ws_stack, _ws_origins)
else:
    _websocket_app = AllowedHostsOriginValidator(_ws_stack)

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": _websocket_app,
    }
)
