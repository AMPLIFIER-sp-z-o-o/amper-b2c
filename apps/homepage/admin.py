from django import forms
from django.contrib import admin
from django.db import models
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from unfold.admin import TabularInline
from unfold.contrib.import_export.forms import ExportForm, ImportForm
from unfold.decorators import display

from apps.utils.admin_mixins import AutoReorderMixin, BaseModelAdmin, HistoryModelAdmin
from apps.utils.admin_utils import make_image_preview_html, make_status_badge_html, make_status_text_html

from .models import (
    Banner,
    BannerGroup,
    BannerSettings,
    BannerType,
    HomepageSection,
    HomepageSectionBanner,
    HomepageSectionCategoryBox,
    HomepageSectionCategoryItem,
    HomepageSectionProduct,
    HomepageSectionType,
    StorefrontCategoryBox,
    StorefrontCategoryItem,
    StorefrontHeroSection,
)


class BannerResource(resources.ModelResource):
    class Meta:
        model = Banner
        fields = ("id", "banner_type", "name", "url", "is_active", "order")
        export_order = fields
        import_id_fields = ["id"]


class BannerForm(forms.ModelForm):
    """Form for Banner admin with conditional fields based on banner_type."""

    class Meta:
        model = Banner
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Get banner_type from instance, POST data, or default
        banner_type = None
        if self.instance and self.instance.pk:
            banner_type = self.instance.banner_type
        elif self.data:
            banner_type = self.data.get("banner_type")

        # For simple banners, we don't need content fields
        # But we keep them in the form and hide via fieldsets


@admin.register(BannerSettings)
class BannerSettingsAdmin(BaseModelAdmin):
    """Admin for Banner Settings singleton - hidden from sidebar, kept for backwards compatibility."""

    list_display = ("__str__", "active_banner_type", "display_status")

    def has_module_permission(self, request):
        """Hide from sidebar - use BannerGroup admin instead."""
        return False

    def has_add_permission(self, request):
        """Only allow one instance."""
        return not BannerSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """Prevent deletion."""
        return False

    fieldsets = (
        (
            None,
            {
                "fields": ("active_banner_type",),
                "description": _("Select which type of banners to display on the homepage. Only banners of the selected type will be shown."),
            },
        ),
        (
            _("Availability"),
            {
                "fields": ("available_from", "available_to"),
                "description": _("Optionally restrict when banners are displayed."),
            },
        ),
    )

    @display(description=_("Status"))
    def display_status(self, obj):
        return make_status_text_html(True, obj.available_from, obj.available_to)


# =============================================================================
# Banner Group Admin (Main banner management interface)
# =============================================================================


class BannerInline(TabularInline):
    """Inline for editing banners within a BannerGroup."""

    model = Banner
    extra = 0
    fields = ("image_preview", "image", "mobile_image", "name", "is_active", "order")
    readonly_fields = ("image_preview",)
    ordering = ("order", "-created_at")
    show_change_link = True
    verbose_name_plural = format_html(
        '{}<span style="margin-left: 10px; font-weight: normal; font-size: 12px; color: #64748b;">{}</span>',
        _("Banners"),
        _("Click on a banner to edit its full details."),
    )

    class Media:
        css = {
            "all": ["css/admin_product_image_inline.css"],
        }

    def image_preview(self, obj):
        """Display image preview."""
        return make_image_preview_html(obj.image if obj else None, size=60, show_open_link=bool(obj and obj.pk))

    image_preview.short_description = _("Preview")


@admin.register(BannerGroup)
class BannerGroupAdmin(BaseModelAdmin):
    """Admin for Banner Groups - the main interface for managing homepage banners."""

    list_display = ("banner_type_display", "banner_count", "display_status", "is_active")
    list_display_links = ("banner_type_display",)
    list_editable = ("is_active",)
    ordering = ("-banner_type",)  # Content first
    inlines = [BannerInline]

    class Media:
        css = {
            "all": ["css/admin_product_image_inline.css"],
        }

    def has_add_permission(self, request):
        """Limit to exactly 2 groups (one per type)."""
        return BannerGroup.objects.count() < 2

    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of banner groups."""
        return False

    def get_queryset(self, request):
        """Ensure both groups exist."""
        BannerGroup.ensure_groups_exist()
        return super().get_queryset(request)

    def get_fieldsets(self, request, obj=None):
        return (
            (
                None,
                {
                    "fields": ("is_active",),
                    "description": _(
                        "Toggle to make this banner type active on the homepage. "
                        "Only one banner type can be active at a time."
                    ),
                },
            ),
            (
                _("Availability"),
                {
                    "fields": ("available_from", "available_to"),
                    "description": _("Optionally restrict when banners are displayed."),
                },
            ),
        )

    def get_readonly_fields(self, request, obj=None):
        """Make banner_type readonly."""
        return ["banner_type"]

    @display(description=_("Banner Type"))
    def banner_type_display(self, obj):
        return obj.get_banner_type_display()

    @display(description=_("Banners"))
    def banner_count(self, obj):
        count = obj.banners.filter(is_active=True).count()
        total = obj.banners.count()
        return f"{count} active / {total} total"

    @display(description=_("Status"))
    def display_status(self, obj):
        return make_status_badge_html(obj.is_active, obj.available_from, obj.available_to)


@admin.register(Banner)
class BannerAdmin(AutoReorderMixin, ImportExportModelAdmin, BaseModelAdmin):
    """Admin for Banner with conditional fieldsets based on banner_type.
    Hidden from sidebar - access through BannerGroup admin."""

    resource_class = BannerResource
    import_form_class = ImportForm
    export_form_class = ExportForm
    form = BannerForm
    list_display = (
        "image_preview",
        "name",
        "banner_type",
        "display_status",
        "is_active",
        "available_from",
        "available_to",
        "order",
    )
    list_filter = ("banner_type", "is_active")
    search_fields = ("name", "title")
    ordering = ("banner_type", "order", "-created_at")
    list_editable = ("is_active", "order")
    list_per_page = 50
    show_full_result_count = False
    order_field = "order"
    order_scope_field = "group"

    class Media:
        css = {
            "all": ["css/admin_product_image_inline.css"],
        }
        js = ("js/banner_admin.js",)

    def has_module_permission(self, request):
        """Hide from sidebar - access through BannerGroup admin."""
        return False

    def get_readonly_fields(self, request, obj=None):
        """Make banner_type readonly when editing existing."""
        readonly = list(super().get_readonly_fields(request, obj))
        if obj and obj.pk:
            readonly.append("banner_type")
        return readonly

    def get_fieldsets(self, request, obj=None):
        """Return fieldsets based on banner_type."""
        # Determine banner_type
        if obj:
            banner_type = obj.banner_type
        elif request.method == "POST":
            banner_type = request.POST.get("banner_type", BannerType.SIMPLE)
        else:
            banner_type = request.GET.get("banner_type", BannerType.SIMPLE)

        base_fieldset = (
            None,
            {
                "fields": ("banner_type", "name", "image", "mobile_image", "image_alignment"),
                "description": _(
                    "Desktop image: 1920x400px recommended. Images scale to fill the width; height adjusts automatically (max 600px). "
                    "Mobile image (optional): 1080x540px recommended."
                ),
            },
        )

        if banner_type == BannerType.CONTENT:
            return (
                base_fieldset,
                (
                    _("Content"),
                    {
                        "fields": ("badge_label", "badge_text", "title", "subtitle", "text_alignment", "overlay_opacity"),
                    },
                ),
                (
                    _("Primary Button"),
                    {
                        "fields": ("primary_button_text", "primary_button_url", "primary_button_icon", "primary_button_open_in_new_tab"),
                    },
                ),
                (
                    _("Secondary Button"),
                    {
                        "fields": ("secondary_button_text", "secondary_button_url", "secondary_button_icon", "secondary_button_open_in_new_tab"),
                    },
                ),
                (
                    _("Availability"),
                    {
                        "fields": ("is_active", "available_from", "available_to", "order"),
                    },
                ),
            )
        else:
            # Simple banner
            return (
                base_fieldset,
                (
                    _("Link"),
                    {
                        "fields": ("url",),
                        "description": _("URL to redirect when the banner is clicked."),
                    },
                ),
                (
                    _("Availability"),
                    {
                        "fields": ("is_active", "available_from", "available_to", "order"),
                    },
                ),
            )

    @display(description=_("Preview"))
    def image_preview(self, obj):
        """Display image preview."""
        return make_image_preview_html(obj.image if obj else None, size=80, show_open_link=bool(obj and obj.pk))

    @display(description=_("Status"))
    def display_status(self, obj):
        # Check if this banner's type is currently active
        settings = BannerSettings.get_settings()
        is_type_active = obj.banner_type == settings.active_banner_type
        if not is_type_active:
            return make_status_text_html(False, None, None)
        return make_status_text_html(obj.is_active, obj.available_from, obj.available_to)


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


# =============================================================================
# Homepage Section Category Box (for Storefront Hero sections)
# =============================================================================


@admin.register(HomepageSectionCategoryItem)
class HomepageSectionCategoryItemAdmin(HistoryModelAdmin):
    """Hidden admin for media library source links."""

    has_module_permission = lambda self, r: False


class HomepageSectionCategoryItemInline(TabularInline):
    """Inline for category items within a category box."""

    model = HomepageSectionCategoryItem
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


@admin.register(HomepageSectionCategoryBox)
class HomepageSectionCategoryBoxAdmin(AutoReorderMixin, BaseModelAdmin):
    """Admin for managing HomepageSectionCategoryBox with items inline."""

    list_display = ("title", "section", "shop_link_text", "order")
    list_filter = ("section",)
    search_fields = ("title", "shop_link_text")
    ordering = ("section", "order", "id")
    inlines = [HomepageSectionCategoryItemInline]
    order_field = "order"
    order_scope_field = "section"

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


class HomepageSectionCategoryBoxInline(TabularInline):
    """Inline for category boxes within the storefront hero section."""

    model = HomepageSectionCategoryBox
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

        # Remove title for section types that don't need it
        if section_type not in [
            HomepageSectionType.PRODUCT_LIST,
            HomepageSectionType.PRODUCT_SLIDER,
            HomepageSectionType.BANNER_SECTION,
            HomepageSectionType.CUSTOM_SECTION,
            HomepageSectionType.STOREFRONT_HERO,
        ]:
            if "title" in self.fields:
                self.fields.pop("title")

        # Remove custom section fields for non-custom types
        if section_type != HomepageSectionType.CUSTOM_SECTION:
            self.fields.pop("custom_html", None)
            self.fields.pop("custom_css", None)
            self.fields.pop("custom_js", None)

        # Remove storefront hero fields for non-storefront-hero types
        if section_type != HomepageSectionType.STOREFRONT_HERO:
            self.fields.pop("subtitle", None)
            self.fields.pop("primary_button_text", None)
            self.fields.pop("primary_button_url", None)
            self.fields.pop("primary_button_open_in_new_tab", None)
            self.fields.pop("secondary_button_text", None)
            self.fields.pop("secondary_button_url", None)
            self.fields.pop("secondary_button_open_in_new_tab", None)

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
class HomepageSectionAdmin(AutoReorderMixin, BaseModelAdmin):
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
    order_field = "order"
    order_scope_field = None

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
        elif section_type == HomepageSectionType.PRODUCT_SLIDER:
            return [HomepageSectionProductInline]
        elif section_type == HomepageSectionType.BANNER_SECTION:
            return [HomepageSectionBannerInline]
        elif section_type == HomepageSectionType.STOREFRONT_HERO:
            return [HomepageSectionCategoryBoxInline]
        return []

    def get_fieldsets(self, request, obj=None):
        section_type = self._resolve_section_type(request, obj)
        base_fields = ["section_type", "name"]
        description = None
        if section_type == HomepageSectionType.PRODUCT_LIST:
            base_fields.append("title")
        elif section_type == HomepageSectionType.PRODUCT_SLIDER:
            base_fields.append("title")
            description = _(
                "Product slider displays products in a horizontal carousel with navigation controls. "
                "Add products to display them in a sliding view."
            )
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
        elif section_type == HomepageSectionType.STOREFRONT_HERO:
            base_fields.extend(["title", "subtitle"])
            description = _(
                "Storefront hero section displays a promotional area with title, subtitle, "
                "CTA buttons, and category boxes with product images."
            )

        first_fieldset = (None, {"fields": base_fields})
        if description:
            first_fieldset = (None, {"fields": base_fields, "description": description})

        fieldsets = [first_fieldset]

        # Add buttons fieldset for storefront hero
        if section_type == HomepageSectionType.STOREFRONT_HERO:
            fieldsets.append(
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
                )
            )

        fieldsets.append((_("Availability"), {"fields": ("is_enabled", "available_from", "available_to", "order")}))

        return tuple(fieldsets)

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
class StorefrontCategoryBoxAdmin(AutoReorderMixin, BaseModelAdmin):
    """Admin for managing StorefrontCategoryBox with items inline."""

    list_display = ("title", "section", "shop_link_text", "order")
    list_filter = ("section",)
    search_fields = ("title", "shop_link_text")
    ordering = ("section", "order", "id")
    inlines = [StorefrontCategoryItemInline]
    order_field = "order"
    order_scope_field = "section"

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
    """Admin for Storefront Hero Section (DEPRECATED - kept for backwards compatibility)."""

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

    def has_module_permission(self, request):
        """Hide from sidebar - use HomepageSection with section_type=STOREFRONT_HERO instead."""
        return False

    def has_add_permission(self, request):
        """Prevent adding new instances - use HomepageSection instead."""
        return False

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
