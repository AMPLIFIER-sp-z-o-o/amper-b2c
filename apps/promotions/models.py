from apps.orders.models import Coupon as OrderCoupon


class Coupon(OrderCoupon):
    class Meta:
        proxy = True
