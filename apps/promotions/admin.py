from django.contrib import admin

from unfold.admin import ModelAdmin

from .models import Coupon


@admin.register(Coupon)
class CouponAdmin(ModelAdmin):
    list_display = ("code", "kind", "value", "is_active", "valid_from", "valid_to", "usage_limit", "used_count")
    list_editable = ("is_active",)
    list_filter = ("kind", "is_active")
    search_fields = ("code",)
    ordering = ("code",)
