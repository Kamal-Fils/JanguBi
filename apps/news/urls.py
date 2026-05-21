from django.urls import path

from apps.news import apis

urlpatterns = [
    # Publique
    path("categories/", apis.CategoryListApi.as_view(), name="category-list"),
    path("", apis.ArticleGlobalListApi.as_view(), name="global-list"),
    path("my-parish/", apis.ArticleMyParishListApi.as_view(), name="my-parish-list"),
    path("parish/<int:parish_id>/", apis.ArticleParishListApi.as_view(), name="parish-list"),
    path("diocese/<int:diocese_id>/", apis.ArticleDioceseListApi.as_view(), name="diocese-list"),
    path("<uuid:article_id>/", apis.ArticleDetailApi.as_view(), name="detail"),

    # Administration
    path("admin/", apis.AdminArticleListApi.as_view(), name="admin-list"),
    path("admin/create/", apis.AdminArticleCreateApi.as_view(), name="admin-create"),
    path("admin/<uuid:article_id>/", apis.AdminArticleDetailApi.as_view(), name="admin-detail"),
    path("admin/<uuid:article_id>/update/", apis.AdminArticleUpdateApi.as_view(), name="admin-update"),
    path("admin/<uuid:article_id>/publish/", apis.AdminArticlePublishApi.as_view(), name="admin-publish"),
    path("admin/<uuid:article_id>/unpublish/", apis.AdminArticleUnpublishApi.as_view(), name="admin-unpublish"),
    path("admin/<uuid:article_id>/delete/", apis.AdminArticleDeleteApi.as_view(), name="admin-delete"),
]
