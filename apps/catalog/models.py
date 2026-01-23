from __future__ import annotations

from autoslug import AutoSlugField
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django_ckeditor_5.fields import CKEditor5Field

from apps.media.storage import DynamicMediaStorage
from apps.utils.models import BaseModel


class ProductStatus(models.TextChoices):
    ACTIVE = "active", _("Active")
    HIDDEN = "hidden", _("Hidden")


class Category(BaseModel):
    name = models.CharField(max_length=200)
    slug = AutoSlugField(populate_from="name", unique=True, always_update=False)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="children",
        on_delete=models.SET_NULL,
    )
    image = models.ImageField(upload_to="category-images/", blank=True, null=True, storage=DynamicMediaStorage())

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Categories"

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("web:home")


class Product(BaseModel):
    name = models.CharField(max_length=255)
    slug = AutoSlugField(populate_from="name", unique=True, always_update=False)
    category = models.ForeignKey(Category, related_name="products", on_delete=models.PROTECT)
    status = models.CharField(
        max_length=20,
        choices=ProductStatus.choices,
        default=ProductStatus.HIDDEN,
        help_text=_("Controls product page visibility."),
    )
    price = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    stock = models.PositiveIntegerField(default=0)
    sales_total = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        verbose_name=_("Units sold (total)"),
        help_text=_("Total number of units sold."),
    )
    revenue_total = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        verbose_name=_("Revenue (total)"),
        help_text=_("Total revenue generated."),
    )
    sales_per_day = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        verbose_name=_("Units sold (daily avg)"),
        help_text=_("Average units sold per day."),
    )
    sales_per_month = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        verbose_name=_("Units sold (monthly avg)"),
        help_text=_("Average units sold per month."),
    )
    description = CKEditor5Field(blank=True, default="", verbose_name=_("Description"), config_name="extends")

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["status", "-revenue_total"], name="idx_status_revenue"),
            models.Index(fields=["status", "-sales_total"], name="idx_status_sales"),
            models.Index(fields=["status", "-sales_per_day"], name="idx_status_sales_day"),
            models.Index(fields=["status", "-updated_at"], name="idx_status_updated"),
            models.Index(fields=["stock"], name="idx_stock"),
            models.Index(fields=["sales_per_month"], name="idx_sales_month"),
        ]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("web:home")


class ProductImage(BaseModel):
    product = models.ForeignKey(Product, related_name="images", on_delete=models.CASCADE)
    image = models.ImageField(upload_to="product-images/", storage=DynamicMediaStorage())
    alt_text = models.CharField(max_length=200, blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return f"{self.product.name} ({self.sort_order})"

    def save(self, *args, **kwargs):
        # Auto-increment sort_order for new images if not explicitly set
        if self._state.adding and self.sort_order == 0:
            max_order = ProductImage.objects.filter(product=self.product).aggregate(
                max_order=models.Max("sort_order")
            )["max_order"]
            if max_order is not None:
                self.sort_order = max_order + 1
        super().save(*args, **kwargs)


class AttributeDefinition(BaseModel):
    name = models.CharField(max_length=100, unique=True)
    display_name = models.CharField(max_length=150)

    class Meta:
        ordering = ["display_name"]

    def __str__(self) -> str:
        return self.display_name


class AttributeOption(BaseModel):
    attribute = models.ForeignKey(AttributeDefinition, related_name="options", on_delete=models.CASCADE)
    value = models.CharField(max_length=100)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["attribute", "value"], name="uniq_attribute_option_value"),
        ]
        ordering = ["attribute", "value"]

    def __str__(self) -> str:
        return f"{self.attribute.display_name}: {self.value}"


class ProductAttributeValue(BaseModel):
    product = models.ForeignKey(Product, related_name="attribute_values", on_delete=models.CASCADE)
    option = models.ForeignKey(AttributeOption, related_name="product_values", on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["product", "option"], name="uniq_product_option"),
        ]

    def __str__(self) -> str:
        return str(self.option)
