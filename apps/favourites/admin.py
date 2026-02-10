from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline

from .models import WishList, WishListItem


class WishListItemInline(TabularInline):
    model = WishListItem
    extra = 0
    readonly_fields = ("price_when_added", "created_at")
    autocomplete_fields = ("product",)


@admin.register(WishList)
class WishListAdmin(ModelAdmin):
    list_display = ("name", "user", "is_default", "product_count_display", "created_at")
    list_filter = ("is_default", "created_at")
    search_fields = ("name", "user__email", "user__first_name", "user__last_name")
    readonly_fields = ("session_key", "created_at", "updated_at")
    autocomplete_fields = ("user",)
    inlines = (WishListItemInline,)

    @admin.display(description=_("Products"))
    def product_count_display(self, obj):
        return obj.product_count


@admin.register(WishListItem)
class WishListItemAdmin(ModelAdmin):
    list_display = ("product", "wishlist", "price_when_added", "price_changed_display", "created_at")
    list_filter = ("created_at", "wishlist")
    search_fields = ("product__name", "wishlist__name")
    readonly_fields = ("price_when_added", "created_at", "updated_at")
    autocomplete_fields = ("product", "wishlist")

    @admin.display(description=_("Price Changed"), boolean=True)
    def price_changed_display(self, obj):
        return obj.price_changed
