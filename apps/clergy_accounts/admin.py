from django.contrib import admin

from .models import ClergicalInvitation


@admin.register(ClergicalInvitation)
class ClergicalInvitationAdmin(admin.ModelAdmin):
    list_display = ["id", "email", "pastoral_role", "status", "created_by", "expires_at", "created_at"]
    list_filter = ["status", "pastoral_role"]
    search_fields = ["email", "first_name", "last_name"]
    raw_id_fields = ["created_by", "accepted_by", "diocese"]
    readonly_fields = ["token", "created_at", "updated_at"]
