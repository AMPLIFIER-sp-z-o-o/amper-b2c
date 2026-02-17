from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.html import format_html, mark_safe
from django.utils.translation import gettext_lazy as _
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from unfold.admin import TabularInline
from unfold.contrib.import_export.forms import ExportForm, ImportForm

from apps.utils.admin_mixins import AutoReorderMixin, HistoryModelAdmin
from apps.utils.admin_utils import make_image_preview_html
from apps.web.models import SiteSettings

from .models import (
    AttributeDefinition,
    AttributeOption,
    Category,
    CategoryBanner,
    CategoryRecommendedProduct,
    Product,
    ProductAttributeValue,
    ProductImage,
    ProductStatus,
)


class ProductImageInline(TabularInline):
    model = ProductImage
    extra = 1
    fields = ["image_preview", "image", "alt_text", "sort_order"]
    readonly_fields = ["image_preview"]
    classes = ["tab-product-images"]

    class Media:
        css = {
            "all": ["css/admin_product_image_inline.css"],
        }

    def image_preview(self, obj):
        """Display thumbnail preview with fullscreen on click and filename tooltip."""
        # Show open link only for saved objects (has pk)
        show_link = obj and obj.pk
        return make_image_preview_html(
            obj.image if obj else None,
            alt_text=getattr(obj, "alt_text", None),
            show_open_link=show_link,
        )

    image_preview.short_description = _("Preview")


class ProductAttributeValueForm(forms.ModelForm):
    class Meta:
        model = ProductAttributeValue
        fields = "__all__"
        labels = {
            "option": _("Attribute value"),
        }


class ProductAttributeValueInline(TabularInline):
    form = ProductAttributeValueForm
    model = ProductAttributeValue
    extra = 1
    autocomplete_fields = ["option"]
    hide_title = True

    def get_formset(self, request, obj=None, **kwargs):
        """Dynamically set the title of the inline section to include the product name."""
        if obj:
            self.verbose_name_plural = format_html(
                '{} <span class="mx-2 text-gray-400 font-normal">/</span> <span class="text-primary-600 font-bold">{}</span>',
                _("Product attribute values"),
                obj.name,
            )
        else:
            self.verbose_name_plural = _("Product attribute values")
        return super().get_formset(request, obj, **kwargs)


class CategoryBannerInline(TabularInline):
    """Inline to manage banners within a category."""

    model = CategoryBanner
    extra = 0
    fields = ["image_preview", "image", "name", "tab_title", "url", "is_active", "order"]
    readonly_fields = ["image_preview"]
    ordering = ("order", "id")
    classes = ["tab-product-images"]
    verbose_name_plural = format_html(
        '{}<span style="margin-left: 10px; font-weight: normal; font-size: 12px; color: #64748b;">{}</span>',
        _("Category Banners"),
        _("Banners displayed as a slider at the top of the category page."),
    )

    class Media:
        css = {
            "all": ["css/admin_product_image_inline.css"],
        }

    def image_preview(self, obj):
        """Display banner image preview."""
        return make_image_preview_html(obj.image if obj else None, size=80, show_open_link=bool(obj and obj.pk))

    image_preview.short_description = _("Preview")


class CategoryRecommendedProductInline(TabularInline):
    """Inline to manage recommended products within a category."""

    model = CategoryRecommendedProduct
    extra = 0
    fields = ["product_image_preview", "product", "order"]
    readonly_fields = ["product_image_preview"]
    ordering = ("order", "id")
    autocomplete_fields = ["product"]
    hide_title = True
    verbose_name_plural = format_html(
        '{}<span style="margin-left: 10px; font-weight: normal; font-size: 12px; color: #64748b;">{}</span>',
        _("Recommended Products"),
        _("Products displayed in the 'Recommended in category' section at the bottom."),
    )

    class Media:
        css = {
            "all": ["css/admin_product_image_inline.css"],
        }

    def get_queryset(self, request):
        """Prefetch product images to avoid N+1 queries."""
        from django.db.models import Prefetch

        return (
            super()
            .get_queryset(request)
            .select_related("product")
            .prefetch_related(Prefetch("product__images", queryset=ProductImage.objects.order_by("sort_order", "id")))
        )

    def product_image_preview(self, obj):
        """Display the primary product image."""
        if not obj or not obj.product_id:
            return make_image_preview_html(None, size=50, show_open_link=False)

        all_images = list(obj.product.images.all())
        primary_image = all_images[0] if all_images else None

        if primary_image and primary_image.image:
            return make_image_preview_html(
                primary_image.image,
                alt_text=primary_image.alt_text or obj.product.name,
                size=50,
                show_open_link=True,
            )
        return make_image_preview_html(None, size=50, show_open_link=False)

    product_image_preview.short_description = _("Image")


class CategoryProductInline(TabularInline):
    """Inline to display products assigned to a category."""

    model = Product
    fk_name = "category"
    extra = 0
    max_num = 0  # Prevent adding new products from here
    can_delete = False
    show_change_link = False  # We handle links in name_display
    hide_title = True  # Hide the row header since we show name in column
    per_page = 20  # Pagination for large product lists
    fields = ["product_image_preview", "name_display", "status", "price_display", "stock"]
    readonly_fields = ["product_image_preview", "name_display", "status", "price_display", "stock"]
    verbose_name = _("Assigned Product")
    verbose_name_plural = _("Assigned Products")

    class Media:
        css = {
            "all": ["css/admin_category_product.css"],
        }

    def get_queryset(self, request):
        """Prefetch product images to avoid N+1 queries."""
        from django.db.models import Prefetch

        return (
            super()
            .get_queryset(request)
            .prefetch_related(Prefetch("images", queryset=ProductImage.objects.order_by("sort_order", "id")))
        )

    def product_image_preview(self, obj):
        """Display the primary product image with link to open in new tab."""
        if not obj or not obj.pk:
            return make_image_preview_html(None, size=50, show_open_link=False)

        # Use prefetched images (access .all() to use cache, not .order_by which triggers new query)
        all_images = list(obj.images.all())
        primary_image = all_images[0] if all_images else None

        if primary_image and primary_image.image:
            return make_image_preview_html(
                primary_image.image,
                alt_text=primary_image.alt_text or obj.name,
                size=50,
                show_open_link=True,
            )
        return make_image_preview_html(None, size=50, show_open_link=False)

    product_image_preview.short_description = _("Image")

    def name_display(self, obj):
        """Display product name with Change and View on site links below."""
        if not obj.pk:
            return "-"
        change_url = reverse("admin:catalog_product_change", args=[obj.pk])
        site_url = obj.get_absolute_url()
        return format_html(
            '<div class="w-full">'
            '<div class="font-medium text-base text-gray-900 dark:text-gray-100">{name}</div>'
            '<div class="flex gap-3 mt-1 text-xs">'
            '<a href="{change_url}" class="text-primary-600 hover:underline dark:text-primary-500">{change_label}</a>'
            '<a href="{site_url}" target="_blank" rel="noopener" class="text-primary-600 hover:underline dark:text-primary-500">{view_label}</a>'
            "</div>"
            "</div>",
            name=obj.name,
            change_url=change_url,
            site_url=site_url,
            change_label=_("Change"),
            view_label=_("View on site"),
        )

    name_display.short_description = _("Name")

    def price_display(self, obj):
        """Display price with data-price for JS formatting."""
        currency = SiteSettings.get_settings().currency or "USD"
        return format_html(
            '<span data-price="{}" data-currency="{}">{}</span>',
            obj.price,
            currency,
            obj.price,
        )

    price_display.short_description = _("Price")

    def has_add_permission(self, request, obj=None):
        return False


class ProductResource(resources.ModelResource):
    def before_import_row(self, row, **kwargs):
        super().before_import_row(row, **kwargs)

        status = row.get("status")
        if status not in (None, ""):
            valid_statuses = {choice[0] for choice in ProductStatus.choices}
            if status not in valid_statuses:
                raise ValidationError(_("Invalid status: %(status)s") % {"status": status})

        price = row.get("price")
        if price not in (None, ""):
            try:
                price_value = Decimal(str(price))
            except (InvalidOperation, ValueError) as exc:
                raise ValidationError(_("Invalid price value: %(price)s") % {"price": price}) from exc

            if price_value < 0:
                raise ValidationError(_("Price cannot be negative."))

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "slug",
            "category",
            "status",
            "price",
            "stock",
            "description",
            "created_at",
            "updated_at",
        )
        export_order = fields
        import_id_fields = ["id"]


@admin.register(Product)
class ProductAdmin(HistoryModelAdmin, ImportExportModelAdmin):
    resource_class = ProductResource
    import_form_class = ImportForm
    export_form_class = ExportForm
    list_select_related = ["category"]
    list_per_page = 50
    show_full_result_count = False

    def get_queryset(self, request):
        from django.db.models import Prefetch

        return (
            super()
            .get_queryset(request)
            .prefetch_related(Prefetch("images", queryset=ProductImage.objects.order_by("sort_order", "id")))
        )

    list_display = (
        "image_preview",
        "name",
        "status",
        "category",
        "price_display",
        "stock",
        "sales_total_list",
        "revenue_display",
        "updated_at",
    )
    list_filter = ("status", "category")
    search_fields = ("name", "slug")
    ordering = ("-updated_at",)
    autocomplete_fields = ["category"]
    inlines = [ProductImageInline, ProductAttributeValueInline]
    readonly_fields = (
        "created_at",
        "updated_at",
        "sales_total_display",
        "revenue_total_display",
        "sales_per_day_display",
        "sales_per_month_display",
    )
    fieldsets = (
        (
            None,
            {
                "fields": ("name", "category", "status", "description"),
            },
        ),
        (
            _("Pricing & Inventory"),
            {
                "fields": ("price", "stock"),
            },
        ),
        (
            _("Statistics"),
            {
                "fields": (
                    "sales_total_display",
                    "revenue_total_display",
                    "sales_per_day_display",
                    "sales_per_month_display",
                ),
            },
        ),
        (
            _("Timestamps"),
            {
                "fields": ("created_at", "updated_at"),
            },
        ),
    )

    @admin.display(description=_("Price"), ordering="price")
    def price_display(self, obj):
        """Display price with data-price for JS formatting."""
        currency = SiteSettings.get_settings().currency or "USD"
        return format_html(
            '<span data-price="{}" data-currency="{}">{}</span>',
            obj.price,
            currency,
            obj.price,
        )

    def image_preview(self, obj):
        """Display product's primary image in list view."""
        if not obj or not obj.pk:
            return make_image_preview_html(None, size=40, show_open_link=False)

        # Access prefetched images via .all() and convert to list to ensure we use the prefetched cache
        # with the correct order defined in get_queryset
        all_images = list(obj.images.all())
        primary_image = all_images[0] if all_images else None

        if primary_image and primary_image.image:
            return make_image_preview_html(
                primary_image.image,
                alt_text=primary_image.alt_text or obj.name,
                size=40,
                show_open_link=False,
            )
        return make_image_preview_html(None, size=40, show_open_link=False)

    image_preview.short_description = _("Image")

    @admin.display(description=_("Revenue"), ordering="revenue_total")
    def revenue_display(self, obj):
        """Display revenue with data-price for JS formatting."""
        currency = SiteSettings.get_settings().currency or "USD"
        return format_html(
            '<span data-price="{}" data-currency="{}">{}</span>',
            obj.revenue_total,
            currency,
            obj.revenue_total,
        )

    @admin.display(description=_("Sales"), ordering="sales_total")
    def sales_total_list(self, obj):
        return obj.sales_total

    @admin.display(description=_("Units sold (total)"))
    def sales_total_display(self, obj):
        return obj.sales_total

    @admin.display(description=_("Revenue (total)"))
    def revenue_total_display(self, obj):
        """Display revenue with data-price for JS formatting."""
        currency = SiteSettings.get_settings().currency or "USD"
        return format_html(
            '<span data-price="{}" data-currency="{}">{}</span>',
            obj.revenue_total,
            currency,
            obj.revenue_total,
        )

    @admin.display(description=_("Units sold (daily avg)"))
    def sales_per_day_display(self, obj):
        return obj.sales_per_day

    @admin.display(description=_("Units sold (monthly avg)"))
    def sales_per_month_display(self, obj):
        return obj.sales_per_month


class CategoryResource(resources.ModelResource):
    class Meta:
        model = Category
        fields = ("id", "name", "slug", "parent")
        export_order = fields
        import_id_fields = ["id"]


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = "__all__"
        labels = {
            "image": _("Category Image"),
        }


@admin.register(Category)
class CategoryAdmin(HistoryModelAdmin, ImportExportModelAdmin):
    form = CategoryForm
    resource_class = CategoryResource
    import_form_class = ImportForm
    export_form_class = ExportForm
    list_display = (
        "name",
        "parent",
        "slug",
        "product_count",
        "banner_count",
        "recommended_count",
        "show_banners",
        "show_recommended_products",
    )
    list_editable = ["show_banners", "show_recommended_products"]
    list_select_related = ["parent"]
    list_per_page = 50
    show_full_result_count = False
    search_fields = ("name", "slug")
    ordering = ("name",)
    autocomplete_fields = ["parent"]
    inlines = [CategoryBannerInline, CategoryRecommendedProductInline, CategoryProductInline]
    readonly_fields = ["product_count_detail"]

    class Media:
        css = {
            "all": ["css/admin_product_image_inline.css"],
        }

    def get_fieldsets(self, request, obj=None):
        base_fieldsets = [
            (None, {"fields": ("name", "parent", "image")}),
            (_("Display Settings"), {"fields": ("show_banners", "show_recommended_products")}),
        ]
        if obj:  # Only show product count when editing existing category
            base_fieldsets.append((_("Products Info"), {"fields": ("product_count_detail",)}))
        return base_fieldsets

    def formfield_for_dbfield(self, db_field, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, **kwargs)
        if isinstance(db_field, models.ImageField):
            formfield.widget.attrs["data-product-image-upload"] = "true"
        return formfield

    def get_queryset(self, request):
        """Annotate counts using Subquery for better performance."""
        from django.db.models import OuterRef, Subquery
        from django.db.models.functions import Coalesce

        # Use Subquery instead of Count with distinct=True to avoid cartesian products
        product_count_subquery = (
            Product.objects.filter(category=OuterRef("pk"))
            .values("category")
            .annotate(cnt=models.Count("id"))
            .values("cnt")
        )

        banner_count_subquery = (
            CategoryBanner.objects.filter(category=OuterRef("pk"))
            .values("category")
            .annotate(cnt=models.Count("id"))
            .values("cnt")
        )

        recommended_count_subquery = (
            CategoryRecommendedProduct.objects.filter(category=OuterRef("pk"))
            .values("category")
            .annotate(cnt=models.Count("id"))
            .values("cnt")
        )

        return (
            super()
            .get_queryset(request)
            .annotate(
                _product_count=Coalesce(Subquery(product_count_subquery), 0),
                _banner_count=Coalesce(Subquery(banner_count_subquery), 0),
                _recommended_count=Coalesce(Subquery(recommended_count_subquery), 0),
            )
        )

    def banner_count(self, obj):
        """Display banner count in list view."""
        count = getattr(obj, "_banner_count", obj.banners.count())
        return count

    banner_count.short_description = _("Banners")

    def recommended_count(self, obj):
        """Display recommended products count in list view."""
        count = getattr(obj, "_recommended_count", obj.recommended_products.count())
        return count

    recommended_count.short_description = _("Recommended")

    def product_count(self, obj):
        """Display product count in list view."""
        count = getattr(obj, "_product_count", obj.products.count())
        if count > 0:
            url = reverse("admin:catalog_product_changelist") + f"?category__id__exact={obj.pk}"
            return format_html('<a href="{}" class="text-primary-600 hover:underline">{}</a>', url, count)
        return count

    product_count.short_description = _("Products")

    def product_count_detail(self, obj):
        """Display detailed product count in change form."""
        if not obj.pk:
            return "-"
        total = obj.products.count()
        active = obj.products.filter(status="active").count()
        hidden = obj.products.filter(status="hidden").count()
        disabled = obj.products.filter(status="disabled").count()

        url = reverse("admin:catalog_product_changelist") + f"?category__id__exact={obj.pk}"
        parts = [
            format_html(
                '<span class="text-lg font-semibold">{}</span> {} (',
                total,
                _("products total"),
            ),
            format_html('<span class="text-green-600">{} {}</span>', active, _("active")),
            format_html(', <span class="text-gray-500">{} {}</span>', hidden, _("hidden")),
        ]
        if disabled:
            parts.append(format_html(', <span class="text-orange-500">{} {}</span>', disabled, _("disabled")))
        parts.append(
            format_html(
                ') — <a href="{}" class="text-primary-600 hover:underline">{}</a>',
                url,
                _("View all products"),
            )
        )
        return mark_safe("".join(str(p) for p in parts))

    product_count_detail.short_description = _("Product Count")


class AttributeDefinitionResource(resources.ModelResource):
    class Meta:
        model = AttributeDefinition
        fields = ("id", "name", "slug")
        export_order = fields
        import_id_fields = ["id"]


@admin.register(AttributeDefinition)
class AttributeDefinitionAdmin(AutoReorderMixin, HistoryModelAdmin, ImportExportModelAdmin):
    resource_class = AttributeDefinitionResource
    import_form_class = ImportForm
    export_form_class = ExportForm
    list_display = ("name", "show_on_tile", "tile_display_order")
    list_editable = ["show_on_tile", "tile_display_order"]
    search_fields = ("name",)
    ordering = ("tile_display_order", "name")
    readonly_fields = ("slug",)
    order_field = "tile_display_order"
    order_scope_field = None
    fieldsets = (
        (None, {"fields": ("name", "slug")}),
        (
            _("Tile Display Settings"),
            {
                "fields": ("show_on_tile", "tile_display_order"),
                "description": _(
                    "Configure how this attribute appears on product tiles (cards) in slider, grid, and list views."
                ),
            },
        ),
    )


class AttributeOptionResource(resources.ModelResource):
    class Meta:
        model = AttributeOption
        fields = ("id", "attribute", "value")
        export_order = fields
        import_id_fields = ["id"]


@admin.register(AttributeOption)
class AttributeOptionAdmin(HistoryModelAdmin, ImportExportModelAdmin):
    resource_class = AttributeOptionResource
    import_form_class = ImportForm
    export_form_class = ExportForm
    list_display = ("attribute", "value")
    list_select_related = ["attribute"]
    list_per_page = 50
    show_full_result_count = False
    search_fields = ("value", "attribute__name")
    list_filter = ("attribute",)
    autocomplete_fields = ["attribute"]


@admin.register(ProductAttributeValue)
class ProductAttributeValueAdmin(HistoryModelAdmin):
    list_display = ("product", "option")
    list_select_related = ["product", "option", "option__attribute"]
    list_per_page = 50
    show_full_result_count = False
    list_filter = ("option__attribute",)
    search_fields = ("product__name", "option__attribute__name", "option__value")
    autocomplete_fields = ["product", "option"]


@admin.register(ProductImage)
class ProductImageAdmin(HistoryModelAdmin):
    list_display = ("product", "sort_order", "alt_text")
    list_select_related = ["product"]
    list_per_page = 50
    show_full_result_count = False
    list_filter = ("product",)
    ordering = ("product", "sort_order")
    autocomplete_fields = ["product"]


@admin.register(CategoryBanner)
class CategoryBannerAdmin(AutoReorderMixin, HistoryModelAdmin):
    """Admin for managing category banners."""

    list_display = ("name", "category", "is_active", "order", "image_preview")
    list_filter = ("category", "is_active")
    list_select_related = ["category"]
    list_per_page = 50
    show_full_result_count = False
    search_fields = ("name", "category__name")
    ordering = ("category", "order", "id")
    autocomplete_fields = ["category"]
    readonly_fields = ["image_preview_large"]
    order_field = "order"
    order_scope_field = "category"

    class Media:
        css = {
            "all": ["css/admin_product_image_inline.css"],
        }

    fieldsets = (
        (None, {"fields": ("category", "name", "tab_title", "is_active", "order")}),
        (_("Images"), {"fields": ("image_preview_large", "image", "mobile_image")}),
        (_("Link"), {"fields": ("url",)}),
    )

    def formfield_for_dbfield(self, db_field, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, **kwargs)
        if isinstance(db_field, models.ImageField):
            formfield.widget.attrs["data-product-image-upload"] = "true"
        return formfield

    def image_preview(self, obj):
        """Display banner image preview in list view."""
        return make_image_preview_html(obj.image if obj else None, size=60, show_open_link=False)

    image_preview.short_description = _("Preview")

    def image_preview_large(self, obj):
        """Display larger banner image preview in change form."""
        return make_image_preview_html(obj.image if obj else None, size=200, show_open_link=bool(obj and obj.pk))

    image_preview_large.short_description = _("Current Image")


@admin.register(CategoryRecommendedProduct)
class CategoryRecommendedProductAdmin(AutoReorderMixin, HistoryModelAdmin):
    """Admin for managing category recommended products."""

    list_display = ("product", "category", "order", "product_image_preview")
    list_filter = ("category",)
    list_select_related = ["category", "product"]
    list_per_page = 50
    show_full_result_count = False
    search_fields = ("product__name", "category__name")
    ordering = ("category", "order", "id")
    autocomplete_fields = ["category", "product"]
    order_field = "order"
    order_scope_field = "category"

    class Media:
        css = {
            "all": ["css/admin_product_image_inline.css"],
        }

    fieldsets = ((None, {"fields": ("category", "product", "order")}),)

    def get_queryset(self, request):
        """Prefetch product images to avoid N+1 queries."""
        from django.db.models import Prefetch

        return (
            super()
            .get_queryset(request)
            .prefetch_related(Prefetch("product__images", queryset=ProductImage.objects.order_by("sort_order", "id")))
        )

    def product_image_preview(self, obj):
        """Display the primary product image."""
        if not obj or not obj.product_id:
            return make_image_preview_html(None, size=50, show_open_link=False)

        all_images = list(obj.product.images.all())
        primary_image = all_images[0] if all_images else None

        if primary_image and primary_image.image:
            return make_image_preview_html(
                primary_image.image,
                alt_text=primary_image.alt_text or obj.product.name,
                size=50,
                show_open_link=False,
            )
        return make_image_preview_html(None, size=50, show_open_link=False)

    product_image_preview.short_description = _("Image")
