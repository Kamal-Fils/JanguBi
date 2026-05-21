from django.contrib import admin

from .models import Donation, DonationCampaign


@admin.register(DonationCampaign)
class DonationCampaignAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "donation_type", "is_active", "scope_type", "created_at"]
    list_filter = ["is_active", "donation_type", "scope_type"]
    search_fields = ["title"]
    raw_id_fields = ["created_by"]


@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    list_display = ["id", "donor", "campaign", "amount", "currency", "payment_provider", "status"]
    list_filter = ["status", "payment_provider"]
    raw_id_fields = ["donor", "campaign"]
