from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.utils.models import BaseModel

# Create your models here.
class Cart(models.Model):
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_rate_percent = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    tax_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    discount_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    coupon_code = models.CharField(max_length=50, blank=True, default="")
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_method = models.ForeignKey(
        "DeliveryMethod",
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )
    payment_method = models.ForeignKey(
        "PaymentMethod",
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )

    def recalculate(self):
        lines = list(self.lines.all())
        subtotal = sum((line.subtotal for line in lines), Decimal("0.00"))
        self.subtotal = subtotal.quantize(Decimal("0.01"))

        tax_rate = Decimal(self.tax_rate_percent or 0)
        if tax_rate < 0:
            tax_rate = Decimal("0.00")

        delivery_cost = Decimal("0.00")
        payment_cost = Decimal("0.00")
        discount_total = Decimal(self.discount_total or 0)
        if discount_total < 0:
            discount_total = Decimal("0.00")

        # When the cart has no items, fees must not persist.
        if lines:
            if self.delivery_method:
                delivery_cost = self.delivery_method.get_cost_for_cart(subtotal)

            if self.payment_method:
                payment_cost = Decimal(self.payment_method.additional_fees or 0)
        else:
            tax_rate = Decimal("0.00")
            discount_total = Decimal("0.00")
            self.coupon_code = ""

        tax_total = (subtotal * tax_rate / Decimal("100.00")).quantize(Decimal("0.01"))
        self.tax_rate_percent = tax_rate.quantize(Decimal("0.01"))
        self.tax_total = tax_total
        self.discount_total = discount_total.quantize(Decimal("0.01"))

        self.total = (subtotal + tax_total + delivery_cost + payment_cost - discount_total).quantize(Decimal("0.01"))
        if self.total < 0:
            self.total = Decimal("0.00")

        self.save(
            update_fields=[
                "subtotal",
                "tax_rate_percent",
                "tax_total",
                "discount_total",
                "coupon_code",
                "total",
            ]
        )

    def __str__(self):
        return f"Cart {self.id}"


class CartLine(models.Model):
    cart = models.ForeignKey(
        Cart,
        related_name="lines",
        on_delete=models.CASCADE
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE
    )
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "product"],
                name="uniq_cart_product"
            )
        ]

    @property
    def subtotal(self):
        return (self.quantity * self.price).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP
        )
    
class DeliveryMethod(models.Model):
    name = models.CharField(max_length=120)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    delivery_time = models.PositiveIntegerField(
        help_text="Delivery time in days"
    )
    free_from = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Free delivery from this cart amount"
    )
    is_active = models.BooleanField(default=True)


    def get_cost_for_cart(self, cart_total: Decimal) -> Decimal:
        """
        Returns final delivery cost depending on cart value.
        """
        if self.free_from is not None and cart_total >= self.free_from:
            return Decimal("0.00")
        return self.price

    def clean(self):
        super().clean()
        errors = {}
        if self.price is not None and self.price < 0:
            errors["price"] = _("Price must be non-negative.")
        if self.free_from is not None and self.free_from < 0:
            errors["free_from"] = _("Free-from amount must be non-negative.")
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.name} ({self.price})"
    

class PaymentMethod(models.Model):
    name = models.CharField(max_length=120)
    default_payment_time = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Payment time in days"
    )
    additional_fees = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Additional fee for this payment method"
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name}"

    def clean(self):
        super().clean()
        if self.additional_fees is not None and self.additional_fees < 0:
            raise ValidationError({"additional_fees": _("Additional fees must be non-negative.")})

