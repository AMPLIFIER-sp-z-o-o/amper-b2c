from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils import formats, timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.widgets import UnfoldAdminPasswordInput, UnfoldAdminTextInputWidget

from .client import notify_disconnected, run_settings_connection_test
from .models import LiveAssistedSalesSettings


class LiveAssistedSalesSettingsForm(forms.ModelForm):
    class Meta:
        model = LiveAssistedSalesSettings
        fields = "__all__"
        widgets = {
            "las_base_url": UnfoldAdminTextInputWidget(
                attrs={
                    "autocomplete": "off",
                    "data-lpignore": "true",
                    "data-1p-ignore": "true",
                }
            ),
            "store_api_key": UnfoldAdminPasswordInput(
                attrs={
                    "autocomplete": "new-password",
                    "data-las-secret": "true",
                    "data-lpignore": "true",
                    "data-1p-ignore": "true",
                    "data-show-label": _("Show store API key"),
                    "data-hide-label": _("Hide store API key"),
                },
                render_value=True,
            ),
        }


@admin.register(LiveAssistedSalesSettings)
class LiveAssistedSalesSettingsAdmin(ModelAdmin):
    form = LiveAssistedSalesSettingsForm
    list_display = ("enabled", "las_base_url", "last_test_status", "last_test_at", "test_connection_link")
    readonly_fields = ("connection_status_panel",)
    fieldsets = (
        (_("LAS integration"), {"fields": ("enabled", "las_base_url", "store_api_key")}),
        (_("Connection health"), {"fields": ("connection_status_panel",)}),
    )

    class Media:
        css = {
            "all": ("css/live_assisted_sales_admin.css",),
        }
        js = ("js/live_assisted_sales_admin.js",)

    def has_add_permission(self, request):
        return not LiveAssistedSalesSettings.objects.exists()

    def save_model(self, request, obj, form, change):
        previous = None
        if change and obj.pk:
            previous = LiveAssistedSalesSettings.objects.filter(pk=obj.pk).first()
        super().save_model(request, obj, form, change)

        previous_configured = bool(
            previous and previous.enabled and previous.las_base_url and previous.store_api_key
        )
        current_configured = obj.is_configured
        connection_changed = bool(
            previous
            and (
                previous.enabled != obj.enabled
                or previous.las_base_url != obj.las_base_url
                or previous.store_api_key != obj.store_api_key
            )
        )
        if previous_configured and (not current_configured or connection_changed):
            notify_disconnected(previous.las_base_url, previous.store_api_key)
        if current_configured:
            ok, message = run_settings_connection_test(obj)
            messages.success(request, message) if ok else messages.error(request, message)

    def test_connection_link(self, obj):
        if not obj or not obj.pk:
            return _("Save settings first.")
        url = reverse("admin:live_assisted_sales_settings_test", args=[obj.pk])
        return format_html('<a class="button" href="{}">{}</a>', url, _("Test connection"))

    test_connection_link.short_description = _("Test connection")

    @admin.display(description="")
    def connection_status_panel(self, obj):
        if not obj or not obj.pk:
            return format_html(
                '<div class="las-connection-panel las-connection-panel--neutral">'
                '<div class="las-connection-panel__header">'
                '<span class="material-symbols-outlined">info</span>'
                '<div><strong>{}</strong><p>{}</p></div>'
                "</div>"
                "</div>",
                _("Connection check unavailable"),
                _("Save the LAS integration settings before running a connection check."),
            )

        status = obj.last_test_status or ""
        status_config = {
            "success": ("success", _("Connected"), "check_circle"),
            "failed": ("failed", _("Needs attention"), "error"),
        }.get(status, ("neutral", _("Not tested"), "help"))
        status_class, status_label, status_icon = status_config

        tested_at = _("Never")
        if obj.last_test_at:
            tested_at = formats.date_format(timezone.localtime(obj.last_test_at), "DATETIME_FORMAT")

        message = obj.last_test_message or _("Run a connection check after saving the base URL and store API key.")
        url = reverse("admin:live_assisted_sales_settings_test", args=[obj.pk])
        button_label = _("Run connection check")
        description = _(
            "Verifies that this storefront can authenticate with LAS and send browser activity events."
        )

        return format_html(
            '<div class="las-connection-panel las-connection-panel--{}">'
            '<div class="las-connection-panel__header">'
            '<span class="material-symbols-outlined">lan</span>'
            "<div><strong>{}</strong><p>{}</p></div>"
            '<a class="las-connection-panel__button" href="{}">'
            '<span class="material-symbols-outlined">sync</span>{}'
            "</a>"
            "</div>"
            '<div class="las-connection-panel__body">'
            '<div class="las-connection-panel__status">'
            '<span class="las-connection-panel__badge">'
            '<span class="material-symbols-outlined">{}</span>{}'
            "</span>"
            "</div>"
            '<div class="las-connection-panel__item"><span>{}</span><strong>{}</strong></div>'
            '<div class="las-connection-panel__item las-connection-panel__item--wide">'
            "<span>{}</span><strong>{}</strong></div>"
            "</div>"
            "</div>",
            status_class,
            _("Connection health"),
            description,
            url,
            button_label,
            status_icon,
            status_label,
            _("Last checked"),
            tested_at,
            _("Result message"),
            message,
        )

    def get_urls(self):
        return [
            path(
                "<int:object_id>/test-connection/",
                self.admin_site.admin_view(self.test_connection_view),
                name="live_assisted_sales_settings_test",
            ),
        ] + super().get_urls()

    def test_connection_view(self, request, object_id):
        settings_obj = self.get_object(request, object_id)
        ok, message = run_settings_connection_test(settings_obj)
        messages.success(request, message) if ok else messages.error(request, message)
        return redirect("admin:live_assisted_sales_liveassistedsalessettings_change", object_id)
