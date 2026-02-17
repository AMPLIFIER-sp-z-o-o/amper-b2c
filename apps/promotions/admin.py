from django.contrib import admin
from django.db import transaction
from unfold.admin import ModelAdmin

from .models import Coupon


def _copy_coupon_fields(*, src, dst) -> None:
    # Keep in sync with apps.orders.models.Coupon fields.
    for field_name in (
        "code",
        "kind",
        "value",
        "is_active",
        "valid_from",
        "valid_to",
        "usage_limit",
        "used_count",
        "min_subtotal",
    ):
        setattr(dst, field_name, getattr(src, field_name))


@admin.register(Coupon)
class CouponAdmin(ModelAdmin):
    list_display = ("code", "kind", "value", "is_active", "valid_from", "valid_to", "usage_limit", "used_count")
    list_editable = ("is_active",)
    list_filter = ("kind", "is_active")
    readonly_fields = ("used_count",)
    search_fields = ("code",)
    ordering = ("code",)

    def save_model(self, request, obj, form, change):
        # NOTE: Coupon is a proxy model (apps.promotions) for apps.orders.models.Coupon.
        # BaseModel enables django-simple-history; saving the proxy would attempt to write
        # to promotions_historicalcoupon. We persist through the base model instead so
        # history is recorded in orders_historicalcoupon.
        from apps.orders.models import Coupon as OrderCoupon

        with transaction.atomic():
            if change and obj.pk:
                base_obj = OrderCoupon.objects.get(pk=obj.pk)
            else:
                base_obj = OrderCoupon()

            _copy_coupon_fields(src=obj, dst=base_obj)
            base_obj.save()

            # Ensure the proxy instance has the PK for admin redirects.
            obj.pk = base_obj.pk

    def delete_model(self, request, obj):
        from apps.orders.models import Coupon as OrderCoupon

        if not obj.pk:
            return
        with transaction.atomic():
            OrderCoupon.objects.filter(pk=obj.pk).delete()
