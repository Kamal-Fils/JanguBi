from django.contrib import admin

from apps.spiritual.models import PastoralReflection


@admin.register(PastoralReflection)
class PastoralReflectionAdmin(admin.ModelAdmin):
    list_display = ["id", "reflection_date", "scope_type", "author", "created_at"]
    list_filter = ["scope_type", "reflection_date"]
    search_fields = ["title", "content", "author__email"]
    raw_id_fields = ["author", "scope_parish", "scope_diocese", "scope_church"]
    date_hierarchy = "reflection_date"
