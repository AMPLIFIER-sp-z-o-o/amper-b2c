from pathlib import Path
from urllib.parse import urljoin

from django.contrib import admin
from django.db.models import Prefetch
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline

from apps.catalog.models import ProductImage
from apps.web.models import SiteSettings

from .models import WishList, WishListItem


def _get_site_currency() -> str:
    return SiteSettings.get_settings().currency or "USD"


def _format_price_with_currency(price_value):
    if price_value is None:
        return "-"

    currency = _get_site_currency()
    return format_html(
        '<span data-price="{}" data-currency="{}">{}</span><span class="ml-1 text-xs text-base-500">{}</span>',
        price_value,
        currency,
        price_value,
        currency,
    )


class WishListItemInline(TabularInline):
    model = WishListItem
    extra = 0
    can_delete = False
    fields = (
        "product_link",
        "product_image_display",
        "price_when_added_display",
        "current_price_display",
        "notes",
        "created_at",
    )
    readonly_fields = (
        "product_link",
        "product_image_display",
        "price_when_added_display",
        "current_price_display",
        "created_at",
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("product")
            .prefetch_related(Prefetch("product__images", queryset=ProductImage.objects.order_by("sort_order", "id")))
        )

    @admin.display(description=_("Product"), ordering="product__name")
    def product_link(self, obj):
        if not obj.product_id:
            return "-"

        product_opts = obj.product._meta
        change_url = reverse(f"admin:{product_opts.app_label}_{product_opts.model_name}_change", args=[obj.product_id])
        return format_html(
            '<a href="{}" class="product-link-box cursor-pointer text-primary-600 hover:underline dark:text-primary-500" '
            'style="display:flex;align-items:center;min-height:72px;width:100%;">{}</a>',
            change_url,
            obj.product,
        )

    @admin.display(description=_("Image"))
    def product_image_display(self, obj):
        if not obj.product_id:
            return "-"

        images = list(obj.product.images.all())
        primary_image = images[0] if images else None
        if not primary_image or not primary_image.image:
            return format_html(
                '<div class="bg-white border border-base-200 flex grow items-center overflow-hidden '
                'rounded-default shadow-xs max-w-2xl product-image-upload" style="min-height:56px;" '
                'title="{}" aria-label="{}">'
                '<div class="product-image-inline-chip is-empty" title="{}">'
                '<span class="material-symbols-outlined">image</span>'
                "</div>"
                '<span class="grow px-3 py-2 text-base-500">{}</span>'
                "</div>",
                _("No image"),
                _("No image"),
                _("No image"),
                _("No image"),
            )

        image_url = primary_image.image.url
        filename = Path(primary_image.image.name).name
        alt_text = primary_image.alt_text or obj.product.name

        return format_html(
            '<div class="bg-white border border-base-200 flex grow items-center overflow-hidden '
            'rounded-default shadow-xs max-w-2xl product-image-upload" title="{filename}" '
            'aria-label="{filename}">'
            '<div class="product-image-inline-chip" title="{filename}">'
            '<img src="{url}" alt="{alt}" title="{filename}" data-filename="{filename}" '
            'style="cursor: pointer;" onclick="openFullscreen(this);">'
            "</div>"
            '<label class="grow relative" title="{filename}">'
            '<input type="text" aria-label="{choose_label}" value="{url}" readonly '
            'class="grow font-medium min-w-0 px-3 py-2 text-ellipsis pointer-events-none cursor-default" title="{filename}">'
            "</label>"
            '<div class="flex flex-none items-center leading-none self-stretch">'
            '<a target="_blank" rel="noopener" class="border-r border-base-200 cursor-pointer '
            "text-base-400 px-3 hover:text-base-700 dark:border-base-700 dark:text-base-500 "
            'dark:hover:text-base-200 js-open-file" title="{open_label}" href="{url}" '
            'aria-label="{open_label}">'
            '<span class="material-symbols-outlined">open_in_new</span>'
            "</a>"
            "</div>"
            "</div>",
            filename=filename,
            url=image_url,
            alt=alt_text,
            choose_label=_("Choose file to upload"),
            open_label=_("Open in new tab"),
        )

    @admin.display(description=_("Price when added"), ordering="price_when_added")
    def price_when_added_display(self, obj):
        return _format_price_with_currency(obj.price_when_added)

    @admin.display(description=_("Current price"), ordering="product__price")
    def current_price_display(self, obj):
        if not obj.product_id:
            return "-"
        return _format_price_with_currency(obj.product.price)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "notes":
            formfield.help_text = _("Internal note for staff only. Not visible to users.")
            formfield.widget.attrs["rows"] = 2
            formfield.widget.attrs["style"] = "min-height:72px; max-height:72px;"
        return formfield

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WishList)
class WishListAdmin(ModelAdmin):
    list_display = ("name", "user_display", "product_count_display", "created_at")
    list_display_links = ("name", "user_display", "product_count_display", "created_at")
    list_filter = ("created_at",)
    search_fields = ("name", "user__email", "user__first_name", "user__last_name")
    readonly_fields = ("name_display", "user_link", "share_id_copy", "created_at", "updated_at")
    fields = ("name_display", "user_link", "description", "share_id_copy", "created_at", "updated_at")
    inlines = (WishListItemInline,)

    class Media:
        css = {
            "all": ["css/admin_product_image_inline.css", "css/admin_favorites_wishlist.css"],
        }
        js = ["js/admin_favorites_wishlist.js"]

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        self._current_request = request
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        finally:
            self._current_request = None

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user")

    @admin.display(description=_("Name"), ordering="name")
    def name_display(self, obj):
        return obj.name

    @admin.display(description=_("Products"))
    def product_count_display(self, obj):
        return obj.product_count

    @admin.display(description=_("User"), ordering="user__email")
    def user_display(self, obj):
        if not obj.user_id:
            return _("Anonymous")
        return str(obj.user)

    @admin.display(description=_("User"), ordering="user__email")
    def user_link(self, obj):
        if not obj.user_id:
            return format_html('<span class="text-base-500">{}</span>', _("Anonymous"))

        user_opts = obj.user._meta
        change_url = reverse(f"admin:{user_opts.app_label}_{user_opts.model_name}_change", args=[obj.user_id])
        return format_html(
            '<a href="{}" class="cursor-pointer text-primary-600 hover:underline dark:text-primary-500">{}</a>',
            change_url,
            obj.user,
        )

    @admin.display(description=_("Share ID"))
    def share_id_copy(self, obj):
        if not obj or not obj.share_id:
            return "-"

        share_url = self._build_share_url(obj)

        return format_html(
            '<div class="flex items-center gap-2 w-full" data-share-id-copy>'
            '<a href="{}" target="_blank" rel="noopener" '
            'class="share-id-link-box inline-flex flex-1 min-w-0 items-center rounded-default border border-base-200 px-2.5 py-1 text-sm '
            'text-primary-600 hover:bg-base-100 hover:underline dark:border-base-700 dark:text-primary-500 dark:hover:bg-base-800" '
            'title="{}" aria-label="{}">'
            '<span class="share-id-value font-mono">{}</span>'
            "</a>"
            '<button type="button" '
            'class="share-id-copy-btn cursor-pointer rounded-default border border-base-200 px-2 py-1 text-xs font-medium '
            'hover:bg-base-100 dark:border-base-700 dark:hover:bg-base-800 inline-flex items-center gap-1.5" '
            'data-share-id-copy-btn data-share-id="{}" data-copy-label="{}" data-copied-label="{}" '
            'data-error-label="{}" aria-label="{}">'
            '<span class="material-symbols-outlined text-base">content_copy</span>'
            '<span class="share-id-copy-label">{}</span>'
            "</button>"
            "</div>",
            share_url,
            share_url,
            _("Open shared list in new tab"),
            share_url,
            share_url,
            _("Copy"),
            _("Copied"),
            _("Error"),
            _("Copy"),
            _("Copy"),
        )

    def _build_share_url(self, obj):
        relative_share_url = f"{reverse('favorites:favorites_page')}?list={obj.share_id}"

        request = getattr(self, "_current_request", None)
        if request is not None:
            return request.build_absolute_uri(relative_share_url)

        site_url = (SiteSettings.get_settings().site_url or "").strip()
        if site_url:
            return urljoin(f"{site_url.rstrip('/')}/", relative_share_url.lstrip("/"))

        return relative_share_url

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "description":
            formfield.help_text = _("Internal description for staff only. Not visible to users.")
            formfield.widget.attrs["rows"] = 3
            formfield.widget.attrs["style"] = "min-height:72px;"
        return formfield

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WishListItem)
class WishListItemAdmin(ModelAdmin):
    list_display = (
        "product",
        "wishlist",
        "price_when_added_display",
        "current_price_display",
        "price_changed_display",
        "created_at",
    )
    list_filter = ("created_at", "wishlist")
    search_fields = ("product__name", "wishlist__name")
    readonly_fields = (
        "wishlist",
        "product",
        "price_when_added_display",
        "current_price_display",
        "created_at",
        "updated_at",
    )
    fields = (
        "wishlist",
        "product",
        "price_when_added_display",
        "current_price_display",
        "notes",
        "created_at",
        "updated_at",
    )

    @admin.display(description=_("Price when added"), ordering="price_when_added")
    def price_when_added_display(self, obj):
        return _format_price_with_currency(obj.price_when_added)

    @admin.display(description=_("Current price"), ordering="product__price")
    def current_price_display(self, obj):
        return _format_price_with_currency(obj.product.price)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "notes":
            formfield.help_text = _("Internal note for staff only. Not visible to users.")
            formfield.widget.attrs["rows"] = 2
            formfield.widget.attrs["style"] = "min-height:72px; max-height:72px;"
        return formfield

    @admin.display(description=_("Price Changed"), boolean=True)
    def price_changed_display(self, obj):
        return obj.price_changed

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
