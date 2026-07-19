from django.contrib import admin

from .models import MassIntention, MassIntentionStatusLog


@admin.register(MassIntention)
class MassIntentionAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "reference",
        "requestor",
        "intention_type",
        "status",
        "parish",
        "celebration_date",
        "created_at",
    ]
    list_filter = ["status", "intention_type", "created_at"]
    search_fields = ["reference", "requestor__email", "intention_text"]
    raw_id_fields = ["requestor", "pretre", "parish", "receipt_file"]
    readonly_fields = ["reference"]


@admin.register(MassIntentionStatusLog)
class MassIntentionStatusLogAdmin(admin.ModelAdmin):
    list_display = ["intention", "from_status", "to_status", "changed_by", "created_at"]
    list_filter = ["to_status", "created_at"]
    search_fields = ["intention__reference", "changed_by__email"]
    raw_id_fields = ["intention", "changed_by"]

    # Journal immuable : consultable, jamais modifiable depuis l'admin.
    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False
