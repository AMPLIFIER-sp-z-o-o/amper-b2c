from django import forms
from django.contrib import admin
from django.db import models
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from unfold.admin import TabularInline
from unfold.contrib.import_export.forms import ExportForm, ImportForm
from unfold.decorators import display

from apps.utils.admin_mixins import BaseModelAdmin, HistoryModelAdmin
from apps.utils.admin_utils import make_image_preview_html, make_status_badge_html, make_status_text_html

from .models import (
    Banner,
    HomepageSection,
    HomepageSectionBanner,
    HomepageSectionProduct,
    HomepageSectionType,
    StorefrontCategoryBox,
    StorefrontCategoryItem,
    StorefrontHeroSection,
)


class BannerResource(resources.ModelResource):
    class Meta:
        model = Banner
        fields = ("id", "name", "url", "is_active", "available_from", "available_to", "order")
        export_order = fields
        import_id_fields = ["id"]


@admin.register(Banner)
class BannerAdmin(BaseModelAdmin, ImportExportModelAdmin):
    resource_class = BannerResource
    import_form_class = ImportForm
    export_form_class = ExportForm
    list_display = ("image_preview", "name", "display_status", "is_active", "available_from", "available_to", "order")
    list_filter = ("is_active", "available_from", "available_to")
    search_fields = ("name",)
    ordering = ("order", "-created_at")
    list_editable = ("order", "is_active")
    readonly_fields = ("desktop_preview", "mobile_preview")
    list_per_page = 50
    show_full_result_count = False

    class Media:
        css = {
            "all": ["css/admin_product_image_inline.css"],
        }

    @display(description=_("Status"))
    def display_status(self, obj):
        return make_status_text_html(obj.is_active, obj.available_from, obj.available_to)

    def formfield_for_dbfield(self, db_field, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, **kwargs)
        if isinstance(db_field, models.ImageField):
            formfield.widget.attrs["data-product-image-upload"] = "true"
        if db_field.name == "order":
            formfield.widget.attrs.update({"autocomplete": "off"})
        return formfield

    fieldsets = (
        (
            None,
            {
                "fields": ("name", "image", "mobile_image", "url"),
                "description": _(
                    "Desktop image: 1920x400px recommended. Images scale to fill the width; height adjusts automatically (max 600px). "
                    "Mobile image (optional): 1080x540px recommended. Images scale to fill the width; height adjusts automatically. "
                    "Displays on screens ≤768px."
                ),
            },
        ),
        (
            _("Availability"),
            {
                "fields": ("is_active", "available_from", "available_to", "order"),
            },
        ),
    )

    def image_preview(self, obj):
        """List view preview (small)."""
        return make_image_preview_html(obj.image if obj else None, size=50, show_open_link=False)

    image_preview.short_description = _("Preview")

    def desktop_preview(self, obj):
        """Desktop image preview."""
        return make_image_preview_html(
            obj.image if obj else None,
            alt_text=f"{obj.name} (Desktop)" if obj else None,
            show_open_link=bool(obj and obj.pk),
        )

    desktop_preview.short_description = _("Preview")

    def mobile_preview(self, obj):
        """Mobile image preview."""
        return make_image_preview_html(
            obj.mobile_image if obj else None,
            alt_text=f"{obj.name} (Mobile)" if obj else None,
            show_open_link=bool(obj and obj.pk),
        )

    mobile_preview.short_description = _("Preview")


@admin.register(HomepageSectionBanner)
class HomepageSectionBannerAdmin(HistoryModelAdmin):
    has_module_permission = lambda self, r: False


@admin.register(HomepageSectionProduct)
class HomepageSectionProductAdmin(HistoryModelAdmin):
    has_module_permission = lambda self, r: False


class HomepageSectionProductInline(TabularInline):
    model = HomepageSectionProduct
    extra = 0
    fields = ("product_image_preview", "product", "order")
    readonly_fields = ("product_image_preview",)
    ordering = ("order", "id")
    autocomplete_fields = ("product",)
    hide_title = True  # Hide row header since product name is shown in Product column
    verbose_name_plural = format_html(
        '{}<span style="margin-left: 10px; font-weight: normal; font-size: 12px; color: #64748b;">{}</span>',
        _("Products in section"),
        _("A maximum of 8 products is recommended to keep the layout clean and visually consistent."),
    )

    class Media:
        css = {
            "all": ["css/admin_product_image_inline.css"],
        }

    def get_queryset(self, request):
        """Prefetch product images to avoid N+1 queries."""
        from django.db.models import Prefetch

        from apps.catalog.models import ProductImage

        return (
            super()
            .get_queryset(request)
            .select_related("product")
            .prefetch_related(Prefetch("product__images", queryset=ProductImage.objects.order_by("sort_order", "id")))
        )

    def product_image_preview(self, obj):
        """Display the primary product image with link to open in new tab."""
        if not obj or not obj.product_id:
            return make_image_preview_html(None, size=50, show_open_link=False)

        # Use prefetched images (access .all() to use cache, not .order_by which triggers new query)
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


class HomepageSectionBannerInline(TabularInline):
    model = HomepageSectionBanner
    extra = 0
    max_num = 3
    fields = ("image", "name", "url", "order")
    readonly_fields = ()
    ordering = ("order", "id")
    classes = ["tab-product-images"]
    verbose_name_plural = format_html(
        '{}<span style="margin-left: 10px; font-weight: normal; font-size: 12px; color: #64748b;">{}</span>',
        _("Banners in section"),
        _(
            "The combined width must be no more than 1920px, and the maximum height is 400px."
            "For example: 1 × 1920px, 2 × 960px, or 3 × 640px."
            "Example: Banners are centered and fully responsive.."
        ),
    )

    class Media:
        css = {
            "all": ["css/admin_product_image_inline.css"],
        }


class HomepageSectionForm(forms.ModelForm):
    class Meta:
        model = HomepageSection
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        section_type = (
            self.data.get("section_type")
            or self.initial.get("section_type")
            or (self.instance.section_type if self.instance.pk else None)
            or HomepageSectionType.PRODUCT_LIST
        )

        if "section_type" in self.fields and not self.instance.pk:
            self.fields["section_type"].initial = section_type

        if "section_type" in self.fields and self.instance.pk:
            self.fields["section_type"].required = False

        if section_type not in [
            HomepageSectionType.PRODUCT_LIST,
            HomepageSectionType.BANNER_SECTION,
            HomepageSectionType.CUSTOM_SECTION,
        ]:
            if "title" in self.fields:
                self.fields.pop("title")

        if section_type != HomepageSectionType.CUSTOM_SECTION:
            self.fields.pop("custom_html", None)
            self.fields.pop("custom_css", None)
            self.fields.pop("custom_js", None)

    def clean(self):
        cleaned = super().clean()
        section_type = cleaned.get("section_type")
        if not section_type and self.instance.pk:
            section_type = self.instance.section_type

        if section_type == HomepageSectionType.CUSTOM_SECTION:
            cleaned["custom_html"] = cleaned.get("custom_html", "")
            cleaned["custom_css"] = cleaned.get("custom_css", "")
            cleaned["custom_js"] = cleaned.get("custom_js", "")
        else:
            cleaned["custom_html"] = ""
            cleaned["custom_css"] = ""
            cleaned["custom_js"] = ""
        return cleaned


@admin.register(HomepageSection)
class HomepageSectionAdmin(BaseModelAdmin):
    form = HomepageSectionForm
    change_form_template = "admin/homepage/homepagesection/change_form.html"
    list_display = (
        "name",
        "title",
        "section_type",
        "display_status",
        "is_enabled",
        "available_from",
        "available_to",
        "order",
    )
    list_filter = ("section_type", "is_enabled", "available_from", "available_to")
    search_fields = ("name", "title")
    ordering = ("order", "-created_at")
    list_editable = ("order", "is_enabled")
    list_per_page = 50
    show_full_result_count = False

    class Media:
        js = ("js/homepage_section_admin.js",)

    def _resolve_section_type(self, request, obj=None):
        if obj:
            return obj.section_type
        if request.method == "POST":
            return request.POST.get("section_type", HomepageSectionType.PRODUCT_LIST)
        if request.method == "GET" and "section_type" in request.GET:
            return request.GET.get("section_type", HomepageSectionType.PRODUCT_LIST)
        return HomepageSectionType.PRODUCT_LIST

    def get_readonly_fields(self, request, obj=None):
        """Make section_type readonly when editing an existing section."""
        readonly = list(super().get_readonly_fields(request, obj))
        if obj and obj.pk:
            readonly.append("section_type")
        return readonly

    def get_inlines(self, request, obj=None):
        section_type = self._resolve_section_type(request, obj)
        if section_type == HomepageSectionType.PRODUCT_LIST:
            return [HomepageSectionProductInline]
        elif section_type == HomepageSectionType.BANNER_SECTION:
            return [HomepageSectionBannerInline]
        return []

    def get_fieldsets(self, request, obj=None):
        section_type = self._resolve_section_type(request, obj)
        base_fields = ["section_type", "name"]
        description = None
        if section_type == HomepageSectionType.PRODUCT_LIST:
            base_fields.append("title")
        elif section_type == HomepageSectionType.BANNER_SECTION:
            base_fields.append("title")
            description = _(
                "Banner section allows up to 3 banners with a maximum combined width of 1920px. "
                "Banners will be centered on the page and responsive on mobile devices."
            )
        elif section_type == HomepageSectionType.CUSTOM_SECTION:
            base_fields.extend(["custom_html", "custom_css", "custom_js"])
            description = _(
                "Custom section lets you build content with a simple visual editor. "
                "Only safe HTML and layout/typography CSS are allowed."
            )

        first_fieldset = (None, {"fields": base_fields})
        if description:
            first_fieldset = (None, {"fields": base_fields, "description": description})

        return (
            first_fieldset,
            (_("Availability"), {"fields": ("is_enabled", "available_from", "available_to", "order")}),
        )

    def add_view(self, request, form_url="", extra_context=None):
        """Override add_view to set initial section_type from GET parameter."""
        extra_context = extra_context or {}
        section_type = request.GET.get("section_type", HomepageSectionType.PRODUCT_LIST)
        extra_context["initial_section_type"] = section_type
        return super().add_view(request, form_url, extra_context)

    def get_changeform_initial_data(self, request):
        """Set initial data for the form from GET parameters."""
        initial = super().get_changeform_initial_data(request)
        if "section_type" in request.GET:
            initial["section_type"] = request.GET.get("section_type")
        return initial

    @display(description=_("Status"), label=True)
    def display_status(self, obj):
        return make_status_badge_html(obj.is_enabled, obj.available_from, obj.available_to)


# =============================================================================
# Storefront Hero Section Admin
# =============================================================================


@admin.register(StorefrontCategoryItem)
class StorefrontCategoryItemAdmin(HistoryModelAdmin):
    """Hidden admin for media library source links."""

    has_module_permission = lambda self, r: False


class StorefrontCategoryItemInline(TabularInline):
    """Inline for category items within a category box."""

    model = StorefrontCategoryItem
    extra = 0
    max_num = 4
    fields = ("image_preview", "image", "name", "url", "open_in_new_tab", "order")
    readonly_fields = ("image_preview",)
    ordering = ("order", "id")
    classes = ["tab-product-images"]
    verbose_name_plural = format_html(
        '{}<span style="margin-left: 10px; font-weight: normal; font-size: 12px; color: #64748b;">{}</span>',
        _("Category Items"),
        _("Up to 4 items per box. Formats: SVG, PNG, JPG, WEBP. URL: use # or full https://..."),
    )

    class Media:
        css = {
            "all": ["css/admin_product_image_inline.css"],
        }

    def image_preview(self, obj):
        """Display image preview."""
        return make_image_preview_html(obj.image if obj else None, size=50, show_open_link=bool(obj and obj.pk))

    image_preview.short_description = _("Preview")


@admin.register(StorefrontCategoryBox)
class StorefrontCategoryBoxAdmin(BaseModelAdmin):
    """Admin for managing StorefrontCategoryBox with items inline."""

    list_display = ("title", "section", "shop_link_text", "order")
    list_filter = ("section",)
    search_fields = ("title", "shop_link_text")
    ordering = ("section", "order", "id")
    inlines = [StorefrontCategoryItemInline]

    class Media:
        css = {
            "all": ["css/admin_product_image_inline.css"],
        }

    fieldsets = (
        (
            None,
            {
                "fields": ("section", "title", "shop_link_text", "shop_link_url", "shop_link_open_in_new_tab", "order"),
            },
        ),
    )

    def has_module_permission(self, request):
        """Hide from sidebar but allow access through parent."""
        return False


class StorefrontCategoryBoxInline(TabularInline):
    """Inline for category boxes within the storefront section."""

    model = StorefrontCategoryBox
    extra = 0
    max_num = 2
    fields = ("title", "shop_link_text", "shop_link_url", "shop_link_open_in_new_tab", "order")
    ordering = ("order", "id")
    verbose_name_plural = format_html(
        '{}<span style="margin-left: 10px; font-weight: normal; font-size: 12px; color: #64748b;">{}</span>',
        _("Category Boxes"),
        _("Up to 2 category boxes. Each box can contain up to 4 items - edit items after saving. URL: use # or full https://..."),
    )
    show_change_link = True


@admin.register(StorefrontHeroSection)
class StorefrontHeroSectionAdmin(BaseModelAdmin):
    """Admin for Storefront Hero Section."""

    list_display = (
        "title_preview",
        "display_status",
        "is_active",
    )
    list_filter = ("is_active",)
    search_fields = ("title", "subtitle")
    list_editable = ("is_active",)
    list_per_page = 50
    show_full_result_count = False
    inlines = [StorefrontCategoryBoxInline]

    def has_add_permission(self, request):
        """Only allow adding if no instance exists yet."""
        return not StorefrontHeroSection.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of the singleton instance."""
        return False

    class Media:
        css = {
            "all": ["css/admin_product_image_inline.css"],
        }

    fieldsets = (
        (
            _("Left Side Content"),
            {
                "fields": ("title", "subtitle"),
                "description": _("Main headline and description text displayed on the left side of the section."),
            },
        ),
        (
            _("Buttons"),
            {
                "fields": (
                    "primary_button_text",
                    "primary_button_url",
                    "primary_button_open_in_new_tab",
                    "secondary_button_text",
                    "secondary_button_url",
                    "secondary_button_open_in_new_tab",
                ),
                "description": _("Call-to-action buttons. Use '#' for placeholder or full URL (e.g., https://example.com)."),
            },
        ),
        (
            _("Availability"),
            {
                "fields": ("is_active",),
                "description": _("Control when this section is displayed. Leave dates empty for always visible."),
            },
        ),
    )

    def title_preview(self, obj):
        """Truncated title for list display."""
        return obj.title[:50] + "..." if len(obj.title) > 50 else obj.title

    title_preview.short_description = _("Title")

    @display(description=_("Status"))
    def display_status(self, obj):
        return make_status_text_html(obj.is_active, obj.available_from, obj.available_to)
