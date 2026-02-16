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
    phone = models.CharField(max_length=50, blank=True, default="", verbose_name=_("Phone"))

    shipping_country = models.CharField(max_length=120, verbose_name=_("Country"))
    shipping_city = models.CharField(max_length=120, verbose_name=_("City"))
    shipping_address = models.CharField(max_length=255, verbose_name=_("Shipping address"))

    delivery_method_name = models.CharField(max_length=120, blank=True, default="", verbose_name=_("Delivery method"))
    payment_method_name = models.CharField(max_length=120, blank=True, default="", verbose_name=_("Payment method"))

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name=_("Subtotal"))
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
