from django.contrib import admin

from apps.bible.models import Book, Chapter, DailyText, HomilieNote, LectioDivinaSession, ReadingPlan, ReadingPlanPassage, Testament, Verse


@admin.register(Testament)
class TestamentAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "order")
    ordering = ("order",)


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("name", "testament", "order", "verse_count")
    list_filter = ("testament",)
    search_fields = ("name", "slug")
    ordering = ("order",)


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ("book", "number", "verse_count")
    list_filter = ("book__testament",)
    search_fields = ("book__name",)
    ordering = ("book__order", "number")


@admin.register(Verse)
class VerseAdmin(admin.ModelAdmin):
    list_display = ("chapter", "number", "source_file", "created_at")
    list_filter = ("source_file", "chapter__book__testament")
    search_fields = ("text",)
    raw_id_fields = ("chapter",)


@admin.register(DailyText)
class DailyTextAdmin(admin.ModelAdmin):
    list_display = ("date", "category", "title", "created_at")
    list_filter = ("category", "date")
    search_fields = ("title", "content")


@admin.register(HomilieNote)
class HomilieNoteAdmin(admin.ModelAdmin):
    list_display = ("author", "passage_start", "created_at")
    raw_id_fields = ("author", "passage_start", "passage_end")


@admin.register(LectioDivinaSession)
class LectioDivinaSessionAdmin(admin.ModelAdmin):
    list_display = ("user", "passage", "updated_at")
    raw_id_fields = ("user", "passage")


@admin.register(ReadingPlan)
class ReadingPlanAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "is_published", "created_at")
    list_filter = ("is_published",)
    search_fields = ("title",)
    raw_id_fields = ("author",)


@admin.register(ReadingPlanPassage)
class ReadingPlanPassageAdmin(admin.ModelAdmin):
    list_display = ("plan", "verse", "day_number", "order")
    raw_id_fields = ("plan", "verse")
