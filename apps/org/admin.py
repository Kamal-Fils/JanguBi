from django.contrib import admin

from apps.org.models import (
    Church,
    Deanery,
    Diocese,
    Parish,
    Province,
    ReligiousCommunity,
    ReligiousOrder,
)


@admin.register(Province)
class ProvinceAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "code", "country", "created_at"]
    search_fields = ["name", "code"]
    list_filter = ["country"]


@admin.register(Diocese)
class DioceseAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "code", "province", "created_at"]
    search_fields = ["name", "code"]
    list_filter = ["province"]
    raw_id_fields = ["province"]


@admin.register(Parish)
class ParishAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "city", "diocese", "created_at"]
    search_fields = ["name", "city"]
    list_filter = ["diocese__province", "diocese"]
    raw_id_fields = ["diocese"]


@admin.register(ReligiousOrder)
class ReligiousOrderAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "abbreviation"]
    search_fields = ["name", "abbreviation"]


@admin.register(ReligiousCommunity)
class ReligiousCommunityAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "order", "diocese", "parish"]
    search_fields = ["name"]
    list_filter = ["order", "diocese"]
    raw_id_fields = ["order", "diocese", "parish"]


@admin.register(Church)
class ChurchAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "parish", "church_type", "is_main", "is_active", "created_at"]
    list_filter = ["church_type", "is_main", "is_active"]
    search_fields = ["name", "parish__name", "city"]
    raw_id_fields = ["parish"]


@admin.register(Deanery)
class DeaneryAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "diocese", "dean", "created_at"]
    search_fields = ["name"]
    list_filter = ["diocese"]
    raw_id_fields = ["diocese", "dean"]
