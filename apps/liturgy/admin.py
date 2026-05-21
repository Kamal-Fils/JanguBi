from django.contrib import admin

from apps.liturgy.models import AelfDataEntry, AelfResource, LiturgicalDate, Office, Reading


@admin.register(AelfDataEntry)
class AelfDataEntryAdmin(admin.ModelAdmin):
    list_display = ["id", "source_endpoint", "date", "zone", "fetched_at"]
    list_filter = ["zone", "source_endpoint"]
    search_fields = ["date", "zone"]
    date_hierarchy = "fetched_at"


@admin.register(LiturgicalDate)
class LiturgicalDateAdmin(admin.ModelAdmin):
    list_display = ["id", "date", "zone", "day_name", "season", "mystery"]
    list_filter = ["zone", "season"]
    search_fields = ["date", "day_name"]
    date_hierarchy = "date"


@admin.register(AelfResource)
class AelfResourceAdmin(admin.ModelAdmin):
    list_display = ["id", "liturgical_date", "audio_url", "youtube_url"]
    raw_id_fields = ["liturgical_date"]


@admin.register(Reading)
class ReadingAdmin(admin.ModelAdmin):
    list_display = ["id", "liturgical_date", "type", "citation"]
    list_filter = ["type"]
    search_fields = ["citation"]
    raw_id_fields = ["liturgical_date"]


@admin.register(Office)
class OfficeAdmin(admin.ModelAdmin):
    list_display = ["id", "liturgical_date", "office_type"]
    list_filter = ["office_type"]
    raw_id_fields = ["liturgical_date"]
