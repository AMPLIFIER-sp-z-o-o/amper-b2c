import secrets

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.catalog.models import Product
from apps.utils.models import BaseModel


class OrderStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    CONFIRMED = "confirmed", _("Confirmed")
    CANCELLED = "cancelled", _("Cancelled")


class Order(BaseModel):
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="orders",
        verbose_name=_("Customer"),
    )

    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING,
        verbose_name=_("Status"),
    )

    tracking_token = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        verbose_name=_("Tracking token"),
    )

    email_verified_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Email verified at"),
        help_text=_(
            "Set when the customer opens the tracking link from the email. "
            "Used to safely attach guest orders to an account later."
        ),
    )

    email = models.EmailField(verbose_name=_("Email"))
    full_name = models.CharField(max_length=255, verbose_name=_("Full name"))
    company = models.CharField(max_length=255, blank=True, default="", verbose_name=_("Company"))
    phone = models.CharField(max_length=50, blank=True, default="", verbose_name=_("Phone"))

    shipping_postal_code = models.CharField(max_length=20, blank=True, default="", verbose_name=_("Postal code"))
    shipping_city = models.CharField(max_length=120, verbose_name=_("City"))
    shipping_address = models.CharField(max_length=255, verbose_name=_("Shipping address"))

    delivery_method_name = models.CharField(max_length=120, blank=True, default="", verbose_name=_("Delivery method"))
    payment_method_name = models.CharField(max_length=120, blank=True, default="", verbose_name=_("Payment method"))

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name=_("Subtotal"))
    tax_rate_percent = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("Tax rate percent"),
    )
    tax_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name=_("Tax"))
    discount_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("Discount"),
    )
    coupon_code = models.CharField(max_length=50, blank=True, default="", verbose_name=_("Coupon code"))
    delivery_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name=_("Delivery cost"))
    payment_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name=_("Payment cost"))
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name=_("Total"))

    currency = models.CharField(max_length=10, blank=True, default="", verbose_name=_("Currency"))

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Order #{self.pk}"

    def get_tracking_url(self) -> str:
        return reverse("orders:track", kwargs={"token": self.tracking_token})

    @classmethod
    def generate_tracking_token(cls) -> str:
        # 43+ chars, URL safe
        return secrets.token_urlsafe(32)


class OrderLine(BaseModel):
    order = models.ForeignKey(Order, related_name="lines", on_delete=models.CASCADE, verbose_name=_("Order"))
    product = models.ForeignKey(Product, on_delete=models.PROTECT, verbose_name=_("Product"))

    quantity = models.PositiveIntegerField(default=1, verbose_name=_("Quantity"))
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_("Unit price"))
    line_total = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_("Line total"))

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.product} x{self.quantity}"


class CouponKind(models.TextChoices):
    PERCENT = "percent", _("Percent")
    FIXED = "fixed", _("Fixed")


class Coupon(BaseModel):
    code = models.CharField(max_length=50, unique=True, db_index=True, verbose_name=_("Code"))
    kind = models.CharField(
        max_length=20,
        choices=CouponKind.choices,
        default=CouponKind.PERCENT,
        verbose_name=_("Type"),
        help_text=_("Percent reduces subtotal by a percentage. Fixed reduces subtotal by a currency amount."),
    )
    value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("Value"),
        help_text=_("For Percent: enter 10 for 10%. For Fixed: enter amount in store currency."),
    )
    is_active = models.BooleanField(default=True, verbose_name=_("Active"))
    valid_from = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Valid from"),
        help_text=_("Optional start time. Leave empty for immediate availability."),
    )
    valid_to = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Valid to"),
        help_text=_("Optional end time. Leave empty for no expiration."),
    )
    usage_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Usage limit"),
        help_text=_("Optional. Maximum number of times this coupon can be used."),
    )
    used_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Used count"),
        help_text=_("Number of times the coupon has been used."),
    )
    min_subtotal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Min subtotal"),
        help_text=_("Optional. Coupon is valid only when cart subtotal is at least this amount."),
    )

    class Meta:
        ordering = ["code"]
        verbose_name = _("Coupon")
        verbose_name_plural = _("Coupons")

    def __str__(self) -> str:
        return self.code
