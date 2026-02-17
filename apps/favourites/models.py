from __future__ import annotations

import secrets
import string
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.catalog.models import Product
from apps.utils.models import BaseModel


def _generate_share_id() -> str:
    """Generate a unique, non-guessable share ID (10 chars, lowercase + digits)."""
    chars = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(10))


class WishList(BaseModel):
    """
    A shopping/wishlist that can contain multiple products.
    Each user can have multiple wishlists.
    Anonymous users are identified by session_key.
    """

    name = models.CharField(
        max_length=100,
        verbose_name=_("Name"),
        help_text=_("Name of the shopping list"),
    )
    share_id = models.CharField(
        max_length=10,
        unique=True,
        default=_generate_share_id,
        editable=False,
        db_index=True,
        verbose_name=_("Share ID"),
        help_text=_("Unique, non-guessable identifier for sharing"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wishlists",
        null=True,
        blank=True,
        verbose_name=_("User"),
    )
    session_key = models.CharField(
        max_length=40,
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_("Session Key"),
        help_text=_("Session key for anonymous users"),
    )
    is_default = models.BooleanField(
        default=False,
        verbose_name=_("Default"),
        help_text=_("Whether this is the default shopping list (Favourites)"),
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Description"),
    )

    class Meta:
        verbose_name = _("Shopping list")
        verbose_name_plural = _("Shopping lists")
        ordering = ["-is_default", "-updated_at"]
        constraints = [
            # Each user can only have one default wishlist
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_default=True, user__isnull=False),
                name="unique_user_default_wishlist",
            ),
            # Each session can only have one default wishlist
            models.UniqueConstraint(
                fields=["session_key"],
                condition=models.Q(is_default=True, session_key__isnull=False),
                name="unique_session_default_wishlist",
            ),
        ]

    def __str__(self) -> str:
        owner = (
            self.user.get_display_name()
            if self.user
            else f"Session ({self.session_key[:8] if self.session_key else 'unknown'}...)"
        )
        return f"{self.name} - {owner}"

    def get_absolute_url(self) -> str:
        return reverse("favourites:wishlist_detail", kwargs={"pk": self.pk})

    @property
    def product_count(self) -> int:
        """Return the number of products in the wishlist."""
        return self.items.count()

    @property
    def total_value(self) -> Decimal:
        """Calculate the total value of all products in the wishlist."""
        return sum(
            item.product.price for item in self.items.select_related("product").all() if item.product
        ) or Decimal("0.00")

    @classmethod
    def get_or_create_default(cls, user=None, session_key=None) -> WishList:
        """
        Get or create the default shopping list for a user or session.
        """
        if user and user.is_authenticated:
            wishlist, created = cls.objects.get_or_create(
                user=user,
                is_default=True,
                defaults={"name": _("Favourites")},
            )
        elif session_key:
            wishlist, created = cls.objects.get_or_create(
                session_key=session_key,
                user__isnull=True,
                is_default=True,
                defaults={"name": _("Favourites")},
            )
        else:
            raise ValueError("Either user or session_key must be provided")
        return wishlist

    @classmethod
    def merge_anonymous_wishlists(cls, user, session_key: str) -> int:
        """
        Merge anonymous wishlists into user's wishlists after login.
        Returns the number of items transferred.

        Strategy:
        - For default wishlist: merge items into user's default wishlist
        - For custom lists: transfer ownership to user (rename if name conflicts)
        """
        if not session_key:
            return 0

        transferred_count = 0
        anonymous_lists = cls.objects.filter(session_key=session_key, user__isnull=True)

        for anon_list in anonymous_lists:
            if anon_list.is_default:
                # Merge items into user's default wishlist
                user_default = cls.get_or_create_default(user=user)
                for item in anon_list.items.all():
                    # Skip duplicates
                    if not user_default.items.filter(product=item.product).exists():
                        WishListItem.objects.create(
                            wishlist=user_default,
                            product=item.product,
                            price_when_added=item.price_when_added,
                            notes=item.notes,
                        )
                        transferred_count += 1
                # Delete anonymous default list after merge
                anon_list.delete()
            else:
                # Transfer ownership of custom lists
                # Check for name conflicts
                existing_names = list(cls.objects.filter(user=user).values_list("name", flat=True))
                new_name = anon_list.name
                counter = 1
                while new_name in existing_names:
                    new_name = f"{anon_list.name} ({counter})"
                    counter += 1

                anon_list.user = user
                anon_list.session_key = None
                anon_list.name = new_name
                anon_list.save()
                transferred_count += anon_list.items.count()

        return transferred_count


class WishListItem(BaseModel):
    """
    An item in a wishlist, representing a product.
    """

    wishlist = models.ForeignKey(
        WishList,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Shopping list"),
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="wishlist_items",
        verbose_name=_("Product"),
    )
    price_when_added = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name=_("Price when added"),
        help_text=_("The price of the product when it was added to the shopping list"),
    )
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Notes"),
        help_text=_("Personal notes about this item"),
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Sort order"),
    )

    class Meta:
        verbose_name = _("Shopping list item")
        verbose_name_plural = _("Shopping list items")
        ordering = ["sort_order", "-created_at"]
        constraints = [
            # Each product can only appear once in a wishlist
            models.UniqueConstraint(
                fields=["wishlist", "product"],
                name="unique_wishlist_product",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product.name} in {self.wishlist.name}"

    def save(self, *args, **kwargs):
        # Auto-set price when adding
        if self._state.adding and not self.price_when_added:
            self.price_when_added = self.product.price
        super().save(*args, **kwargs)

    @property
    def price_changed(self) -> bool:
        """Check if the product price has changed since being added."""
        return self.product.price != self.price_when_added

    @property
    def price_difference(self) -> Decimal:
        """Calculate the price difference (positive = price increased)."""
        return self.product.price - self.price_when_added

    @property
    def is_available(self) -> bool:
        """Check if the product is still available (in stock and not disabled)."""
        return not self.product.is_unavailable
