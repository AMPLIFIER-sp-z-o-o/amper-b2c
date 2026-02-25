from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline

from apps.catalog.models import ProductImage
from apps.utils.admin_utils import make_image_preview_html
from apps.web.models import SiteSettings

from .models import Order, OrderLine


class OrderLineInline(TabularInline):
    model = OrderLine
    extra = 0
    max_num = 0
    can_delete = False
    show_change_link = False
    hide_title = True
    fields = ["product_image_preview", "product_name_display", "quantity", "unit_price_display", "line_total_display"]
    readonly_fields = [
        "product_image_preview",
        "product_name_display",
        "quantity",
        "unit_price_display",
        "line_total_display",
    ]
    verbose_name = _("Order Line")
    verbose_name_plural = _("Order Lines")

    class Media:
        css = {
            "all": ["css/admin_product_image_inline.css"],
        }

    def get_queryset(self, request):
        from django.db.models import Prefetch

        return (
            super()
            .get_queryset(request)
            .select_related("product")
            .prefetch_related(Prefetch("product__images", queryset=ProductImage.objects.order_by("sort_order", "id")))
        )

    @admin.display(description=_("Image"))
    def product_image_preview(self, obj):
        if not obj or not obj.product_id:
            return make_image_preview_html(None, size=50, show_open_link=False)
        all_images = list(obj.product.images.all())
        primary_image = all_images[0] if all_images else None
        if primary_image and primary_image.image:
            return make_image_preview_html(
                primary_image.image,
                alt_text=primary_image.alt_text or obj.product.name,
                size=50,
                show_open_link=True,
            )
        return make_image_preview_html(None, size=50, show_open_link=False)

    @admin.display(description=_("Product"))
    def product_name_display(self, obj):
        if not obj or not obj.product_id:
            return "-"
        change_url = reverse("admin:catalog_product_change", args=[obj.product_id])
        site_url = obj.product.get_absolute_url()
        return format_html(
            '<div class="w-full">'
            '<div class="font-medium text-base text-gray-900 dark:text-gray-100">{name}</div>'
            '<div class="flex gap-3 mt-1 text-xs">'
            '<a href="{change_url}" class="text-primary-600 hover:underline dark:text-primary-500">{change_label}</a>'
            '<a href="{site_url}" target="_blank" rel="noopener" class="text-primary-600 hover:underline dark:text-primary-500">{view_label}</a>'
            "</div>"
            "</div>",
            name=obj.product.name,
            change_url=change_url,
            site_url=site_url,
            change_label=_("Edit product"),
            view_label=_("View on site"),
        )

    @admin.display(description=_("Unit price"))
    def unit_price_display(self, obj):
        currency = SiteSettings.get_settings().currency or "USD"
        return format_html(
            '<span data-price="{}" data-currency="{}">{}</span>',
            obj.unit_price,
            currency,
            obj.unit_price,
        )

    @admin.display(description=_("Line total"))
    def line_total_display(self, obj):
        currency = SiteSettings.get_settings().currency or "USD"
        return format_html(
            '<span data-price="{}" data-currency="{}">{}</span>',
            obj.line_total,
            currency,
            obj.line_total,
        )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(ModelAdmin):
    list_display = ("id", "status", "customer_list_display", "email", "full_name", "total_display", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("email", "full_name", "tracking_token")
    inlines = [OrderLineInline]
    readonly_fields = (
        "customer_display",
        "email",
        "full_name",
        "phone",
        "shipping_address",
        "shipping_postal_code",
        "shipping_city",
        "delivery_method_name",
        "payment_method_name",
        "subtotal_display",
        "discount_display",
        "coupon_code",
        "delivery_cost_display",
        "total_display",
        "order_summary_url_display",
        "email_verified_at",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (None, {"fields": ("status", "customer_display")}),
        (_("Contact"), {"fields": ("email", "full_name", "phone")}),
        (
            _("Shipping"),
            {"fields": ("shipping_address", "shipping_postal_code", "shipping_city")},
        ),
        (
            _("Methods"),
            {"fields": ("delivery_method_name", "payment_method_name")},
        ),
        (
            _("Totals"),
            {
                "fields": (
                    "subtotal_display",
                    "discount_display",
                    "coupon_code",
                    "delivery_cost_display",
                    "total_display",
                )
            },
        ),
        (
            _("Tracking"),
            {"fields": ("order_summary_url_display",)},
        ),
        (_("Verification"), {"fields": ("email_verified_at",)}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description=_("Customer"))
    def customer_list_display(self, obj):
        if not obj.customer_id:
            return _("Guest")
        return str(obj.customer)

    @admin.display(description=_("Customer"))
    def customer_display(self, obj):
        if not obj.customer_id:
            return format_html('<span class="text-gray-400 dark:text-gray-500">{}</span>', _("Guest"))
        change_url = reverse("admin:users_customuser_change", args=[obj.customer_id])
        return format_html(
            '<a href="{}" class="text-primary-600 hover:underline dark:text-primary-500">{}</a>',
            change_url,
            obj.customer,
        )

    @admin.display(description=_("Order summary link"))
    def order_summary_url_display(self, obj):
        try:
            base_url = (SiteSettings.get_settings().site_url or "").strip().rstrip("/")
        except Exception:
            base_url = ""

        tracking_path = obj.get_tracking_url()
        url = f"{base_url}{tracking_path}" if base_url else tracking_path
        return format_html(
            '<a href="{url}" target="_blank" rel="noopener" class="text-primary-600 hover:underline dark:text-primary-500">{url}</a>',
            url=url,
        )

    @admin.display(description=_("Subtotal"), ordering="subtotal")
    def subtotal_display(self, obj):
        currency = SiteSettings.get_settings().currency or "USD"
        return format_html('<span data-price="{}" data-currency="{}">{}</span>', obj.subtotal, currency, obj.subtotal)

    @admin.display(description=_("Discount"), ordering="discount_total")
    def discount_display(self, obj):
        currency = SiteSettings.get_settings().currency or "USD"
        return format_html(
            '<span data-price="{}" data-currency="{}">{}</span>', obj.discount_total, currency, obj.discount_total
        )

    @admin.display(description=_("Delivery cost"), ordering="delivery_cost")
    def delivery_cost_display(self, obj):
        currency = SiteSettings.get_settings().currency or "USD"
        return format_html(
            '<span data-price="{}" data-currency="{}">{}</span>', obj.delivery_cost, currency, obj.delivery_cost
        )

    @admin.display(description=_("Total"), ordering="total")
    def total_display(self, obj):
        currency = SiteSettings.get_settings().currency or "USD"
        return format_html('<span data-price="{}" data-currency="{}">{}</span>', obj.total, currency, obj.total)
