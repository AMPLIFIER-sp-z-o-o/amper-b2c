from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Order, OrderLine


class OrderLineInline(admin.TabularInline):
    model = OrderLine
    extra = 0
    readonly_fields = ("product", "quantity", "unit_price", "line_total")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "email", "full_name", "total", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("email", "full_name", "tracking_token")
    inlines = [OrderLineInline]
    readonly_fields = ("tracking_token", "email_verified_at", "created_at", "updated_at")

    fieldsets = (
        (None, {"fields": ("status", "customer")}),
        (_("Contact"), {"fields": ("email", "full_name", "phone")}),
        (_("Shipping"), {"fields": ("shipping_country", "shipping_city", "shipping_address")}),
        (_("Methods"), {"fields": ("delivery_method_name", "payment_method_name")}),
        (_("Totals"), {"fields": ("subtotal", "delivery_cost", "payment_cost", "total", "currency")}),
        (_("Tracking"), {"fields": ("tracking_token",)}),
        (_("Verification"), {"fields": ("email_verified_at",)}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at")}),
    )
