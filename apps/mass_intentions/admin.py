from django.contrib import admin

from .models import MassIntention


@admin.register(MassIntention)
class MassIntentionAdmin(admin.ModelAdmin):
    list_display = ["id", "requestor", "intention_type", "status", "parish", "created_at"]
    list_filter = ["status", "intention_type", "created_at"]
    search_fields = ["requestor__email", "intention_text"]
    raw_id_fields = ["requestor", "pretre", "parish"]
