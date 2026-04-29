from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

urlpatterns = [
    path("v1/", include([
        path("auth/", include(("apps.authentication.urls", "authentication"))),
        path("users/", include(("apps.users.urls", "users"))),
        path("errors/", include(("apps.errors.urls", "errors"))),
        path("files/", include(("apps.files.urls", "files"))),
        path("bible/", include(("apps.bible.urls", "bible"))),
        path("rosary/", include(("apps.rosary.urls", "rosary"))),
        path("tv/", include(("apps.tv.urls", "tv"))),
        #path("rag/", include(("apps.rag.urls", "rag"))),
        path("liturgy/", include(("apps.liturgy.urls", "liturgy"))),
        path("messaging/", include(("apps.messaging.urls", "messaging"))),
        path("documents/", include(("apps.documents.urls", "documents"))),
    ])),

    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('swagger-ui/', SpectacularSwaggerView.as_view(url_name='api:schema'), name='swagger-ui'),
    path('redoc/', SpectacularRedocView.as_view(url_name='api:schema'), name='redoc'),
]
