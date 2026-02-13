from django.db import models
from django.conf import settings
from decimal import Decimal, ROUND_HALF_UP

# Create your models here.
class Cart(models.Model):
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
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
        subtotal = sum(
            (line.subtotal for line in self.lines.all()),
            Decimal("0.00")
        )
        self.subtotal = subtotal.quantize(Decimal("0.01"))

        delivery_cost = Decimal("0.00")
        if self.delivery_method:
            delivery_cost = self.delivery_method.get_cost_for_cart(subtotal)
        
        payment_cost = Decimal("0.00")
        if self.payment_method:
            payment_cost = Decimal(self.payment_method.additional_fees or 0)

        self.total = (subtotal + delivery_cost + payment_cost).quantize(Decimal("0.01"))

        self.save(update_fields=["subtotal", "total"])

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

