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
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    def recalculate(self):
        total = sum(
            (line.subtotal for line in self.lines.all()),
            Decimal("0.00")
        )
        self.total = total.quantize(Decimal("0.01"))
        self.save(update_fields=["total"])

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