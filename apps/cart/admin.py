from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from .models import DeliveryMethod


@admin.register(DeliveryMethod)
class DeliveryMethodAdmin(ModelAdmin):

    list_display = (
        "name",
        "price_display",
        "free_from_display",
        "delivery_time",
        "is_active",
    )

    list_editable = ("is_active",)

    search_fields = ("name",)
    ordering = ("name",)
    list_per_page = 50
    show_full_result_count = False

    fieldsets = (
        (None, {
            "fields": ("name", "price", "free_from", "delivery_time", "is_active"),
        }),
    )

    @admin.display(description=_("Price"), ordering="price")
    def price_display(self, obj):
        if obj.price == 0:
            return format_html('<span class="text-green-600 font-semibold">FREE</span>')
        return obj.price

    @admin.display(description=_("Free from"), ordering="free_from")
    def free_from_display(self, obj):
        if not obj.free_from:
            return "-"
        return obj.free_from

    def get_urls(self):
        urls = super().get_urls()
        urls = [u for u in urls if "history" not in u.pattern.regex.pattern]
        return urls
