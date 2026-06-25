from django.contrib import admin

from .models import ParishTransferRequest


@admin.register(ParishTransferRequest)
class ParishTransferRequestAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "requester",
        "origin_parish",
        "destination_parish",
        "status",
        "created_at",
    ]
    list_filter = ["status", "created_at"]
    search_fields = ["requester__email", "reason", "rejection_reason"]
    raw_id_fields = ["requester", "origin_parish", "destination_parish"]
