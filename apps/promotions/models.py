from apps.orders.models import Coupon as OrderCoupon


class Coupon(OrderCoupon):
    # This is a proxy model used only to expose Coupons under the "Promotions" admin section.
    # BaseModel enables django-simple-history for all subclasses; for a proxy this would attempt
    # to write to promotions_historicalcoupon (proxy app_label), creating a second history table.
    # We explicitly disable history tracking for this proxy to avoid duplicate history tables.
    history = None

    class Meta:
        proxy = True
