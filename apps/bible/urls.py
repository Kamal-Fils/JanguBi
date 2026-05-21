from django.urls import path

from apps.bible.apis import (
    HomilieNoteDetailApi,
    HomilieNoteListCreateApi,
    LectioDivinaSessionApi,
    ReadingPlanDetailApi,
    ReadingPlanListCreateApi,
)
from apps.bible.views import (
    BookDetailApi,
    BookListApi,
    ChapterListApi,
    DailyTextListApi,
    ImportApi,
    SearchApi,
    TestamentBooksApi,
    TestamentListApi,
    VerseListApi,
)

urlpatterns = [
    # Testaments
    path("testaments/", TestamentListApi.as_view(), name="testament-list"),
    path("testaments/<slug:testament_slug>/books/", TestamentBooksApi.as_view(), name="testament-books"),

    # Books
    path("books/", BookListApi.as_view(), name="book-list"),
    path("books/<int:book_id>/", BookDetailApi.as_view(), name="book-detail"),
    path("books/<int:book_id>/chapters/", ChapterListApi.as_view(), name="chapter-list"),
    path("books/<int:book_id>/chapters/<int:chapter_number>/verses/", VerseListApi.as_view(), name="verse-list"),

    # Search
    path("search/", SearchApi.as_view(), name="search"),

    # Daily Texts
    path("daily-texts/", DailyTextListApi.as_view(), name="daily-text-list"),

    # Internal Tools
    path("import/", ImportApi.as_view(), name="import-file"),

    # Bible Avancé (M7)
    path("homilenotes/", HomilieNoteListCreateApi.as_view(), name="homilenote-list-create"),
    path("homilenotes/<int:note_id>/", HomilieNoteDetailApi.as_view(), name="homilenote-detail"),
    path("lectio/", LectioDivinaSessionApi.as_view(), name="lectio-divina"),
    path("reading-plans/", ReadingPlanListCreateApi.as_view(), name="reading-plan-list-create"),
    path("reading-plans/<int:plan_id>/", ReadingPlanDetailApi.as_view(), name="reading-plan-detail"),
    path("reading-plans/<int:plan_id>/publish/", ReadingPlanDetailApi.as_view(), name="reading-plan-publish"),
]
