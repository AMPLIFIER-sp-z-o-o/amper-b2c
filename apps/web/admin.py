from django import forms
from django.contrib import admin
from django.db import models
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from unfold.admin import StackedInline, TabularInline
from unfold.widgets import UnfoldAdminColorInputWidget, UnfoldAdminSelect2Widget

from apps.utils.admin_mixins import BaseModelAdmin, HistoryModelAdmin, SingletonAdminMixin
from apps.utils.admin_utils import make_image_preview_html

from .models import (
    BottomBar,
    BottomBarLink,
    CustomCSS,
    Footer,
    FooterSection,
    FooterSectionLink,
    FooterSocialMedia,
    Navbar,
    NavbarItem,
    SiteSettings,
    TopBar,
)


class TopBarForm(forms.ModelForm):
    class Meta:
        model = TopBar
        fields = "__all__"
        widgets = {
            "content_type": UnfoldAdminSelect2Widget,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        content_type = (
            self.data.get("content_type")
            or self.initial.get("content_type")
            or (self.instance.content_type if self.instance.pk else None)
            or TopBar.ContentType.STANDARD
        )
        if "content_type" in self.fields and not self.instance.pk:
            self.fields["content_type"].initial = content_type

        is_custom = content_type == TopBar.ContentType.CUSTOM
        if "text" in self.fields:
            self.fields["text"].required = not is_custom
        if "custom_html" in self.fields:
            self.fields["custom_html"].required = is_custom


@admin.register(TopBar)
class TopBarAdmin(BaseModelAdmin):
    form = TopBarForm
    change_form_template = "admin/web/topbar/change_form.html"
    list_display = ("name", "content_type", "text", "is_active", "available_from", "available_to", "order")
    list_filter = ("is_active", "available_from", "available_to")
    search_fields = ("name", "text")
    ordering = ("order", "-created_at")
    list_editable = ("order", "is_active")

    def has_add_permission(self, request):
        if TopBar.objects.exists():
            return False
        return super().has_add_permission(request)

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "content_type",
                    "background_color",
                    "text",
                    "link_label",
                    "link_url",
                    "custom_html",
                    "custom_css",
                    "custom_js",
                ),
                "description": _("Choose standard content or provide custom HTML for the top bar."),
            },
        ),
        (
            _("Availability"),
            {
                "fields": ("is_active", "available_from", "available_to", "order"),
            },
        ),
    )


@admin.register(CustomCSS)
class CustomCSSAdmin(SingletonAdminMixin, HistoryModelAdmin):
    change_form_template = "admin/web/customcss/change_form.html"
    list_display = ("custom_css_active", "updated_at")
    fieldsets = (
        (
            _("Custom CSS"),
            {
                "fields": ("custom_css_active", "custom_css"),
                "description": _("Edit and activate custom CSS that is injected into the public site."),
            },
        ),
    )

    def has_add_permission(self, request):
        return not CustomCSS.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        settings_obj = CustomCSS.get_settings()
        return redirect(reverse("admin:web_customcss_change", args=[settings_obj.pk]))


class SiteSettingsForm(forms.ModelForm):
    class Meta:
        model = SiteSettings
        fields = "__all__"
        labels = {
            "default_image": _("Product Image"),
        }
        widgets = {
            "currency": UnfoldAdminSelect2Widget,
        }


@admin.register(SiteSettings)
class SiteSettingsAdmin(SingletonAdminMixin, HistoryModelAdmin):
    form = SiteSettingsForm
    list_display = ("store_name", "currency", "updated_at")
    readonly_fields = ("default_image_preview",)

    class Media:
        css = {
            "all": ["css/admin_product_image_inline.css"],
        }

    fieldsets = (
        (
            _("Store Information"),
            {
                "fields": ("store_name", "site_url", "description", "keywords", "default_image"),
                "description": _("Basic store information used in SEO and meta tags."),
            },
        ),
        (
            _("Regional Settings"),
            {
                "fields": ("currency",),
                "description": _("Currency symbol displayed on prices."),
            },
        ),
    )

    def default_image_preview(self, obj):
        """Display ProductImageInline-style preview for default image."""
        show_link = obj and obj.pk
        return make_image_preview_html(
            obj.default_image if obj else None,
            alt_text="Default image",
            show_open_link=show_link,
        )

    default_image_preview.short_description = _("Preview")

    def formfield_for_dbfield(self, db_field, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, **kwargs)
        if isinstance(db_field, models.ImageField):
            formfield.widget.attrs["data-product-image-upload"] = "true"
        return formfield

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        settings_obj = SiteSettings.get_settings()
        return redirect(reverse("admin:web_sitesettings_change", args=[settings_obj.pk]))


# ============================================================================
# Footer Admin
# ============================================================================


class FooterForm(forms.ModelForm):
    class Meta:
        model = Footer
        fields = "__all__"
        widgets = {
            "content_type": UnfoldAdminSelect2Widget,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        content_type = (
            self.data.get("content_type")
            or self.initial.get("content_type")
            or (self.instance.content_type if self.instance.pk else None)
            or Footer.ContentType.STANDARD
        )
        if "content_type" in self.fields and not self.instance.pk:
            self.fields["content_type"].initial = content_type

        is_custom = content_type == Footer.ContentType.CUSTOM
        if "custom_html" in self.fields:
            self.fields["custom_html"].required = is_custom


class FooterSectionLinkInline(TabularInline):
    model = FooterSectionLink
    extra = 1
    fields = ("label", "url", "order")
    ordering = ("order", "id")


@admin.register(FooterSectionLink)
class FooterSectionLinkAdmin(HistoryModelAdmin):
    has_module_permission = lambda self, r: False


@admin.register(FooterSection)
class FooterSectionAdmin(HistoryModelAdmin):
    inlines = [FooterSectionLinkInline]
    list_display = ("name", "order")
    ordering = ("order", "id")
    fields = ("footer", "name", "order")
    readonly_fields = ("footer",)

    def save_model(self, request, obj, form, change):
        if not hasattr(obj, "footer") or not obj.footer_id:
            obj.footer = Footer.get_settings()
        super().save_model(request, obj, form, change)

    def has_module_permission(self, request):
        # Hide from sidebar - only accessible via Footer admin
        return False


class FooterSectionInline(StackedInline):
    model = FooterSection
    extra = 0
    fields = ("name", "order")
    ordering = ("order", "id")
    show_change_link = True


class FooterSocialMediaForm(forms.ModelForm):
    class Meta:
        model = FooterSocialMedia
        fields = "__all__"
        widgets = {
            "platform": UnfoldAdminSelect2Widget,
        }


class FooterSocialMediaInline(TabularInline):
    model = FooterSocialMedia
    form = FooterSocialMediaForm
    extra = 0
    fields = ("platform", "label", "url", "is_active", "order")
    ordering = ("order", "id")
    formfield_overrides = {
        models.URLField: {"widget": forms.TextInput},
    }


@admin.register(Footer)
class FooterAdmin(SingletonAdminMixin, HistoryModelAdmin):
    form = FooterForm
    change_form_template = "admin/web/footer/change_form.html"
    inlines = [FooterSocialMediaInline, FooterSectionInline]
    list_display = ("__str__", "content_type", "is_active")
    search_fields = ["id"]
    fieldsets = (
        (
            None,
            {
                "fields": ("content_type", "is_active", "custom_html", "custom_css", "custom_js"),
                "description": _("Choose standard sections or provide custom HTML for the footer."),
            },
        ),
    )

    def has_add_permission(self, request):
        return not Footer.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        settings_obj = Footer.get_settings()
        return redirect(reverse("admin:web_footer_change", args=[settings_obj.pk]))


# ============================================================================
# Bottom Bar Admin
# ============================================================================


class BottomBarLinkInline(TabularInline):
    model = BottomBarLink
    extra = 1
    fields = ("label", "url", "order")
    ordering = ("order", "id")


@admin.register(BottomBarLink)
class BottomBarLinkAdmin(HistoryModelAdmin):
    has_module_permission = lambda self, r: False


@admin.register(BottomBar)
class BottomBarAdmin(SingletonAdminMixin, HistoryModelAdmin):
    inlines = [BottomBarLinkInline]
    list_display = ("__str__", "is_active")
    fieldsets = (
        (
            None,
            {
                "fields": ("is_active",),
                "description": _("Configure the bottom bar with legal links displayed between logo and copyright."),
            },
        ),
    )

    def has_add_permission(self, request):
        return not BottomBar.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        settings_obj = BottomBar.get_settings()
        return redirect(reverse("admin:web_bottombar_change", args=[settings_obj.pk]))


# ============================================================================
# Navbar Admin
# ============================================================================



class NavbarItemForm(forms.ModelForm):
    label_color = forms.CharField(
        widget=UnfoldAdminColorInputWidget,
        required=False,
    )

    class Meta:
        model = NavbarItem
        fields = "__all__"
        widgets = {
            "item_type": UnfoldAdminSelect2Widget,
            "category": UnfoldAdminSelect2Widget,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Get item_type from form data (handles inline prefix) or instance
        item_type = None
        if self.data:
            # For inline forms, the field name includes prefix like "items-0-item_type"
            prefix = self.prefix
            if prefix:
                item_type = self.data.get(f"{prefix}-item_type")
            else:
                item_type = self.data.get("item_type")
        
        if not item_type:
            item_type = (
                self.initial.get("item_type")
                or (self.instance.item_type if self.instance.pk else None)
                or NavbarItem.ItemType.CATEGORY
            )

        is_category = item_type == NavbarItem.ItemType.CATEGORY
        is_custom_link = item_type == NavbarItem.ItemType.CUSTOM_LINK

        # Set required fields based on type
        if "category" in self.fields:
            self.fields["category"].required = is_category
        if "label" in self.fields:
            self.fields["label"].required = is_custom_link
        if "url" in self.fields:
            self.fields["url"].required = is_custom_link


class NavbarItemInline(TabularInline):
    model = NavbarItem
    form = NavbarItemForm
    extra = 0
    fields = ("order", "item_type", "category", "label", "url", "label_color", "open_in_new_tab", "is_active")
    ordering = ("order", "id")
    
    # Don't show add/change/delete buttons for related objects
    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        # Disable related widget wrapper buttons for category field
        if 'category' in formset.form.base_fields:
            formset.form.base_fields['category'].widget.can_add_related = False
            formset.form.base_fields['category'].widget.can_change_related = False
            formset.form.base_fields['category'].widget.can_delete_related = False
            formset.form.base_fields['category'].widget.can_view_related = False
        return formset


@admin.register(NavbarItem)
class NavbarItemAdmin(HistoryModelAdmin):
    form = NavbarItemForm
    list_display = ("__str__", "item_type", "order", "is_active")
    list_filter = ("item_type", "is_active")
    list_editable = ("order", "is_active")
    ordering = ("order", "id")

    fieldsets = (
        (
            _("Item Configuration"),
            {
                "fields": ("navbar", "item_type", "category", "label", "url", "open_in_new_tab"),
                "description": _("Configure the navigation item type and target."),
            },
        ),
        (
            _("Styling"),
            {
                "fields": ("label_color", "icon"),
                "description": _("Optional styling for the label."),
            },
        ),
        (
            _("Display"),
            {
                "fields": ("order", "is_active"),
            },
        ),
    )

    def has_module_permission(self, request):
        # Hide from sidebar - only accessible via Navbar admin
        return False


class NavbarForm(forms.ModelForm):
    class Meta:
        model = Navbar
        fields = "__all__"


@admin.register(Navbar)
class NavbarAdmin(SingletonAdminMixin, HistoryModelAdmin):
    form = NavbarForm
    change_form_template = "admin/web/navbar/change_form.html"
    inlines = [NavbarItemInline]
    list_display = ("__str__", "mode")
    fieldsets = (
        (
            _("Navigation Mode"),
            {
                "fields": ("mode",),
                "description": _(
                    "Choose between default navigation (categories shown alphabetically) "
                    "or custom navigation (manually configured items below)."
                ),
            },
        ),
    )

    def has_add_permission(self, request):
        return not Navbar.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        settings_obj = Navbar.get_settings()
        return redirect(reverse("admin:web_navbar_change", args=[settings_obj.pk]))
