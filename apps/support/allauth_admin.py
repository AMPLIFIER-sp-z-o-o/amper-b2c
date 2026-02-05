"""Custom admin for django-allauth social apps.

This module overrides allauth's default social account admin to:
1. Use Unfold-styled widgets
2. Simplify the form by hiding rarely-used fields
3. Provide better user experience for OAuth app configuration
4. Allow enabling/disabling providers without deleting them
"""

from allauth import app_settings
from allauth.account.adapter import get_adapter
from allauth.socialaccount import providers
from allauth.socialaccount.models import SocialAccount, SocialApp, SocialToken
from django import forms
from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold import widgets as unfold_widgets
from unfold.admin import StackedInline

from apps.users.models import SocialAppSettings
from apps.utils.admin_mixins import HistoryModelAdmin


class SocialAppSettingsInline(StackedInline):
    """Inline admin for SocialAppSettings to show is_active toggle."""

    model = SocialAppSettings
    can_delete = False
    verbose_name = _("Settings")
    verbose_name_plural = _("Settings")
    fields = ("is_active",)

    def has_add_permission(self, request, obj=None):
        return False


class SimplifiedSocialAppForm(forms.ModelForm):
    """Simplified form for SocialApp focusing on essential fields."""

    class Meta:
        model = SocialApp
        fields = ["provider", "name", "client_id", "secret"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["provider"] = forms.ChoiceField(
            choices=providers.registry.as_choices(),
            label=_("Provider"),
            help_text=_("Select the authentication provider"),
        )
        self.fields["provider"].widget = unfold_widgets.UnfoldAdminSelect2Widget(
            attrs={"data-minimum-results-for-search": 0},
            choices=self.fields["provider"].choices,
        )
        self.fields["client_id"].label = _("Client ID / App ID")
        self.fields["client_id"].help_text = _("OAuth Client ID (Google), App ID (Facebook), or API Key (Twitter)")
        self.fields["secret"].label = _("Client Secret")
        self.fields["secret"].help_text = _("OAuth Client Secret or App Secret")
        self.fields["name"].help_text = _("A friendly name to identify this application")
        if "sites" in self.fields:
            self.fields["sites"].help_text = _("Sites where this app is active")


@admin.register(SocialApp)
class CustomSocialAppAdmin(HistoryModelAdmin):
    """Simplified SocialApp admin with Unfold styling."""

    form = SimplifiedSocialAppForm
    list_display = ("name", "provider", "is_active_display")
    list_filter = ("provider",)
    search_fields = ["name", "provider", "client_id"]
    inlines = [SocialAppSettingsInline]

    fieldsets = (
        (
            None,
            {
                "fields": ("provider", "name"),
                "description": _("Select the OAuth provider and give this app a name."),
            },
        ),
        (
            _("OAuth Credentials"),
            {
                "fields": ("client_id", "secret"),
                "description": _("Enter the credentials from your OAuth provider's developer console."),
            },
        ),
    )

    def is_active_display(self, obj):
        """Display active status with colored badge."""
        try:
            is_active = obj.app_settings.is_active
        except SocialAppSettings.DoesNotExist:
            is_active = True
        if is_active:
            return format_html(
                '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">{}</span>',
                _("Active"),
            )
        return format_html(
            '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200">{}</span>',
            _("Disabled"),
        )

    is_active_display.short_description = _("Status")

    def save_model(self, request, obj, form, change):
        """Automatically assign the current site if none selected."""
        super().save_model(request, obj, form, change)
        # Ensure SocialAppSettings exists
        SocialAppSettings.objects.get_or_create(social_app=obj)
        if app_settings.SITES_ENABLED and not obj.sites.exists():
            from django.contrib.sites.models import Site

            obj.sites.add(Site.objects.get_current(request))


@admin.register(SocialAccount)
class CustomSocialAccountAdmin(HistoryModelAdmin):
    """Simplified SocialAccount admin."""

    autocomplete_fields = ["user"]
    list_display = ("user", "uid", "provider")
    list_filter = ("provider",)
    search_fields = ["user__email", "user__username", "uid", "provider"]
    readonly_fields = ("provider", "uid", "extra_data")

    def get_search_fields(self, request):
        base_fields = get_adapter().get_user_search_fields()
        return list(map(lambda a: "user__" + a, base_fields))


@admin.register(SocialToken)
class CustomSocialTokenAdmin(HistoryModelAdmin):
    """Token admin with better display."""

    autocomplete_fields = ["app", "account"]
    list_display = ("app", "account", "truncated_token", "expires_at")
    list_filter = ("app", "app__provider", "expires_at")
    readonly_fields = ("token", "token_secret")

    def truncated_token(self, token):
        max_chars = 40
        ret = token.token
        if len(ret) > max_chars:
            ret = ret[0:max_chars] + "...(truncated)"
        return ret

    truncated_token.short_description = _("Token")
