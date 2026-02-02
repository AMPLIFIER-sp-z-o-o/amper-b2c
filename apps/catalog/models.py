from __future__ import annotations

import re

from autoslug import AutoSlugField
from django.db import models
from django.urls import reverse
from django.utils.text import slugify
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
    sort_order = models.IntegerField(default=0, help_text=_("Sort order in navigation menu (lower numbers first)."))
    icon = models.CharField(max_length=50, blank=True, default="circle", help_text=_("Icon name for the menu."))

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "Categories"

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("web:product_list_category", args=[self.id, self.slug])


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
        max_digits=15,
        decimal_places=2,
        default=0,
        verbose_name=_("Units sold (total)"),
        help_text=_("Total number of units sold."),
    )
    revenue_total = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        verbose_name=_("Revenue (total)"),
        help_text=_("Total revenue generated."),
    )
    sales_per_day = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        verbose_name=_("Units sold (daily avg)"),
        help_text=_("Average units sold per day."),
    )
    sales_per_month = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
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
        return reverse("catalog:product_detail", kwargs={"slug": self.slug, "id": self.id})

    @property
    def tile_display_attributes(self) -> list:
        """
        Get attributes for display on product tiles (slider, grid, list views).
        
        Returns up to 4 attributes sorted by:
        1. tile_display_order (lower first)
        2. display_name (alphabetically) when order is the same
        
        Only attributes with show_on_tile=True are included.
        
        Returns a list of dicts with keys:
        - attribute_name: The display name of the attribute
        - full_value: The complete value
        - display_value: The truncated value (with ... if truncated)
        - is_truncated: Boolean indicating if value was truncated
        - attribute_id: AttributeDefinition id for filter matching
        - option_slug: AttributeOption slug for filter matching
        """
        max_attrs = 4
        max_value_length = 25
        attrs = []
        # Get attribute values with related attribute definitions
        attr_values = self.attribute_values.select_related(
            "option__attribute"
        ).filter(
            option__attribute__show_on_tile=True
        ).order_by(
            "option__attribute__tile_display_order",
            "option__attribute__display_name"
        )[:max_attrs]
        
        for av in attr_values:
            full_value = av.option.value
            is_truncated = len(full_value) > max_value_length
            display_value = full_value[:max_value_length] + "..." if is_truncated else full_value
            
            attrs.append({
                "attribute_name": av.option.attribute.display_name,
                "full_value": full_value,
                "display_value": display_value,
                "is_truncated": is_truncated,
                "attribute_id": av.option.attribute_id,
                "option_slug": av.option.slug,
            })
        
        return attrs


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
            max_order = ProductImage.objects.filter(product=self.product).aggregate(max_order=models.Max("sort_order"))[
                "max_order"
            ]
            if max_order is not None:
                self.sort_order = max_order + 1
        super().save(*args, **kwargs)


class AttributeDefinition(BaseModel):
    name = models.CharField(max_length=100, unique=True)
    display_name = models.CharField(max_length=150)
    # Controls whether this attribute appears on product tiles (slider, grid, list views)
    show_on_tile = models.BooleanField(
        default=True,
        verbose_name=_("Show on product tiles"),
        help_text=_("Whether to display this attribute on product cards/tiles."),
    )
    # Order in which attributes appear on tiles (lower = shown first)
    tile_display_order = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Tile display order"),
        help_text=_("Order in which attribute appears on product tiles. Lower numbers appear first."),
    )

    class Meta:
        ordering = ["display_name"]

    def __str__(self) -> str:
        return self.display_name

    def save(self, *args, **kwargs):
        # Auto-assign display order for new attributes
        if self._state.adding and self.tile_display_order == 0:
            max_order = AttributeDefinition.objects.aggregate(
                max_order=models.Max("tile_display_order")
            )["max_order"]
            if max_order is not None:
                self.tile_display_order = max_order + 1
        super().save(*args, **kwargs)


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

    @property
    def slug(self) -> str:
        """Return a slug combining id and slugified value for URL param use (e.g., '4-hp')."""
        return f"{self.id}-{slugify(self.value)}"

    @staticmethod
    def parse_slug(slug_value: str) -> int | None:
        """Parse a slug value (e.g., '4-hp') and return the option ID, or None if invalid."""
        if not slug_value:
            return None
        match = re.match(r"^(\d+)-", slug_value)
        if match:
            return int(match.group(1))
        # Fallback: try to parse as plain integer for backwards compatibility
        try:
            return int(slug_value)
        except (ValueError, TypeError):
            return None


class ProductAttributeValue(BaseModel):
    product = models.ForeignKey(Product, related_name="attribute_values", on_delete=models.CASCADE)
    option = models.ForeignKey(AttributeOption, related_name="product_values", on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["product", "option"], name="uniq_product_option"),
        ]

    def __str__(self) -> str:
        return str(self.option)
