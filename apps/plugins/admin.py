from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import textwrap
import zipfile
from functools import lru_cache
from pathlib import Path

from django.contrib import admin, messages
from django.conf import settings
from django.contrib.auth import get_permission_codename
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path as url_path
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline

from apps.plugins.engine.lifecycle import PluginLifecycleManager, get_plugin_dir, get_plugins_root
from apps.plugins.engine.loader import sync_and_load_plugins
from apps.plugins.engine.registry import registry
from apps.plugins.forms import PluginAdminForm, PluginConfigForm, PluginUploadZipForm
from apps.plugins.management.commands.plugins_validate_zip import PluginZipValidator
from apps.plugins.models import (
    Plugin,
    PluginKVData,
    PluginLog,
    PluginMigrationState,
    PluginStatus,
    PluginWebhookEvent,
)
from apps.utils.admin_mixins import HistoryModelAdmin


@lru_cache(maxsize=1)
def _get_bundled_plugin_seed_data() -> dict[str, dict]:
    seed_file = Path(settings.BASE_DIR) / "assets" / "seeds" / "generated" / "plugins_data.json"
    try:
        data = json.loads(seed_file.read_text(encoding="utf-8"))
    except Exception:
        return {}

    if not isinstance(data, list):
        return {}

    entries: dict[str, dict] = {}
    for entry in data:
        if not isinstance(entry, dict):
            continue
        slug = str(entry.get("slug") or "").strip()
        if not slug:
            continue
        entries[slug] = entry
    return entries


def _get_bundled_plugin_slugs() -> set[str]:
    """Return slugs of plugins bundled with the repo (defined in plugins_data.json seed)."""
    return set(_get_bundled_plugin_seed_data().keys())


def _resolve_bundled_plugin_zip_path(slug: str) -> Path:
    entry = _get_bundled_plugin_seed_data().get(slug, {})
    package_zip = str(entry.get("package_zip") or "").strip()
    if package_zip:
        candidate = Path(package_zip)
        return candidate if candidate.is_absolute() else Path(settings.BASE_DIR) / candidate
    return Path(settings.BASE_DIR) / "plugins" / "dist" / f"{slug}.zip"


def _resolve_plugin_directory_for_backup(plugin: Plugin) -> Path | None:
    root = get_plugins_root().resolve()
    candidates: list[Path] = []

    package_path = str(plugin.package_path or "").strip()
    if package_path:
        candidates.append(Path(package_path))
    candidates.append(get_plugin_dir(plugin.slug))

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            continue

        if not resolved.exists() or not resolved.is_dir():
            continue

        try:
            resolved.relative_to(root)
        except ValueError:
            continue

        return resolved

    return None


def _write_plugin_backup_zip(source_dir: Path, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                archive.write(file_path, arcname=file_path.relative_to(source_dir).as_posix())


# ─── Scaffold helpers ──────────────────────────────────────────────────────────

def _scaffold_manifest(slug: str, name: str, version: str, has_config: bool) -> dict:
    return {
        "slug": slug,
        "name": name,
        "version": version,
        "entrypoint": "entrypoint.py",
        "dependencies": [],
        "scopes": [],
        "default_config": {},
    }


def _scaffold_schema() -> dict:
    return {
        "type": "object",
        "required": [],
        "properties": {
            "api_key": {
                "type": "string",
                "title": "API Key",
                "format": "password",
                "description": "Private API key from provider dashboard.",
            },
        },
    }


def _scaffold_entrypoint(slug: str) -> str:
    tpl = textwrap.dedent("""\
        from __future__ import annotations

        PLUGIN_SLUG = "__SLUG__"


        def register(api):
            # Register your hooks here.  Examples:
            #   api.register_filter("my.hook.name", my_filter, priority=20)
            #   api.register_action("my.event.name", my_action, priority=20)
            #   api.register_async_action("plugin.webhook.received", handle_webhook, priority=20)
            pass


        def on_plugin_activated(plugin=None, **kwargs): pass
        def on_plugin_deactivated(plugin=None, **kwargs): pass
        def on_plugin_before_delete(plugin=None, **kwargs): pass
    """)
    return tpl.replace("__SLUG__", slug)


_EVENT_TYPE_LABELS = {
    "bootstrap.loaded": _("Plugin started correctly"),
    "bootstrap.sync_failed": _("Plugin sync failed"),
    "bootstrap.zombie_plugin": _("Plugin files are missing"),
    "lifecycle.install": _("Plugin was installed"),
    "lifecycle.update": _("Plugin was updated"),
    "lifecycle.update_failed": _("Plugin update failed"),
    "lifecycle.activate": _("Plugin was activated"),
    "lifecycle.deactivate": _("Plugin was deactivated"),
    "lifecycle.uninstall": _("Plugin was uninstalled"),
    "lifecycle.callback.executed": _("Plugin callback completed"),
    "lifecycle.callback.failed": _("Plugin callback failed"),
    "action.executed": _("Plugin action completed"),
    "filter.applied": _("Plugin rule applied"),
    "async_action.executed": _("Async action completed"),
    "async_action.error": _("Async action failed"),
    "hook.skipped": _("A plugin hook was skipped"),
    "hook.timeout.soft": _("Plugin response was slow"),
    "hook.timeout": _("Plugin timed out"),
    "hook.error": _("Plugin returned an error"),
    "http.request": _("External connection attempt"),
}

_EVENT_TYPE_IMPACT = {
    "bootstrap.loaded": _("Plugin is available and ready to work."),
    "bootstrap.sync_failed": _("System could not fully sync plugin files from disk."),
    "bootstrap.zombie_plugin": _("Database entry exists, but package files are missing on disk."),
    "lifecycle.install": _("Installation finished successfully."),
    "lifecycle.update": _("Plugin update was applied."),
    "lifecycle.update_failed": _("Update failed. The plugin may require attention before use."),
    "lifecycle.activate": _("Plugin is now active for store operations."),
    "lifecycle.deactivate": _("Plugin was turned off and is no longer used in flows."),
    "lifecycle.uninstall": _("Plugin data and registration were removed."),
    "lifecycle.callback.executed": _("Plugin lifecycle callback ran successfully."),
    "lifecycle.callback.failed": _("Lifecycle callback failed and may block part of plugin behavior."),
    "action.executed": _("Requested plugin action completed."),
    "filter.applied": _("Plugin filter logic was applied successfully."),
    "async_action.executed": _("Background plugin task completed."),
    "async_action.error": _("Background plugin task failed."),
    "hook.skipped": _("A hook was skipped, so optional plugin logic did not run."),
    "hook.timeout.soft": _("Plugin replied slowly. Store flow continued with reduced responsiveness."),
    "hook.timeout": _("Plugin response exceeded allowed time and was interrupted."),
    "hook.error": _("Plugin callback returned an error."),
    "http.request": _("Plugin attempted to contact an external service."),
}


def _humanize_event_type(event_type: str) -> str:
    if not event_type:
        return str(_("Unknown event"))
    if event_type in _EVENT_TYPE_LABELS:
        return str(_EVENT_TYPE_LABELS[event_type])
    return event_type.replace(".", " ").replace("_", " ").strip().capitalize()


def _owner_impact(event_type: str, level: str) -> str:
    if event_type in _EVENT_TYPE_IMPACT:
        return str(_EVENT_TYPE_IMPACT[event_type])

    if level == "error":
        return str(_("Action is required. The plugin reported an error."))
    if level == "warning":
        return str(_("Plugin completed with a warning. Monitor if this repeats."))
    return str(_("No action needed."))


def _owner_result(level: str) -> str:
    if level == "error":
        return str(_("Needs attention"))
    if level == "warning":
        return str(_("Warning"))
    return str(_("OK"))


def _short_message(message: str, limit: int = 140) -> str:
    if not message:
        return "-"
    return message[: limit - 1] + "…" if len(message) > limit else message


def _technical_details_markup(obj: PluginLog) -> str:
    details_url = reverse("admin:plugins_pluginlog_change", args=[obj.pk])
    correlation = obj.correlation_id or "-"
    short_message = _short_message(obj.message)

    return format_html(
        "<a href='{}'>{}</a><br><span><code>{}</code></span><br><span>{}: <code>{}</code></span><br><span>{}</span>",
        details_url,
        _("Open full diagnostics"),
        obj.event_type,
        _("Correlation"),
        correlation,
        short_message,
    )


class PluginLogInline(TabularInline):
    model = PluginLog
    extra = 0
    max_num = 0
    per_page = 50
    fields = ("created_at", "owner_event", "owner_result", "owner_impact", "technical_details")
    readonly_fields = ("created_at", "owner_event", "owner_result", "owner_impact", "technical_details")
    ordering = ("-created_at",)
    verbose_name = _("Activity entry")
    verbose_name_plural = _("Store owner activity and diagnostics")
    can_delete = False
    show_change_link = False

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user")

    @admin.display(description=_("What happened"))
    def owner_event(self, obj):
        return _humanize_event_type(obj.event_type)

    @admin.display(description=_("Result"))
    def owner_result(self, obj):
        return _owner_result(obj.level)

    @admin.display(description=_("Description"))
    def owner_impact(self, obj):
        return _owner_impact(obj.event_type, obj.level)

    @admin.display(description=_("Details"))
    def technical_details(self, obj):
        return _technical_details_markup(obj)


@admin.register(Plugin)
class PluginAdmin(HistoryModelAdmin):
    form = PluginAdminForm
    change_form_template = "admin/plugins/plugin/change_form.html"
    change_list_template = "admin/plugins/plugin/change_list.html"
    object_history_list_template = "admin/plugins/plugin/object_history_list.html"
    list_display = ("name", "slug", "status", "updated_at")
    list_filter = ("status",)
    search_fields = ("name", "slug")
    inlines = [PluginLogInline]
    readonly_fields = (
        "store_owner_status",
        "lifecycle_actions",
        "package_info",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            _("Plugin"),
            {
                "fields": (
                    "name",
                    "status",
                    "package_info",
                ),
            },
        ),
        (
            _("Actions"),
            {
                "fields": ("lifecycle_actions",),
            },
        ),
        (
            _("Execution mode"),
            {
                "fields": ("execution_mode", "safe_mode_ip_allowlist"),
                "description": _(
                    "Controls which requests trigger plugin hooks. "
                    "Use \"Super Admin only\" for testing, \"IP allowlist\" for staged rollout, "
                    "or \"Live\" for normal production operation."
                ),
            },
        ),
        (
            _("Diagnostics"),
            {
                "fields": ("store_owner_status", "created_at", "updated_at"),
            },
        ),
    )

    actions = ["activate_selected", "deactivate_selected", "sync_selected"]
    delete_related_preview_limit = 20

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()
        return self.readonly_fields

    def get_inlines(self, request, obj=None):
        if obj is None:
            return []
        return self.inlines

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return (
                (
                    _("Plugin"),
                    {
                        "fields": (
                            "name",
                            "status",
                        ),
                    },
                ),
            )
        return self.fieldsets

    def get_urls(self):
        custom_urls = [
            url_path("sync/", self.admin_site.admin_view(self.sync_from_disk_view), name="plugins_sync_from_disk"),
            url_path(
                "deactivate/<int:plugin_id>/",
                self.admin_site.admin_view(self.deactivate_single_view),
                name="plugins_deactivate",
            ),
            url_path(
                "test-connection/<int:plugin_id>/",
                self.admin_site.admin_view(self.test_connection_view),
                name="plugins_test_connection",
            ),
            url_path(
                "configure/<int:plugin_id>/",
                self.admin_site.admin_view(self.configure_view),
                name="plugins_configure",
            ),
            url_path(
                "upload/",
                self.admin_site.admin_view(self.upload_zip_view),
                name="plugins_upload_zip",
            ),
            url_path(
                "upload/<int:plugin_id>/",
                self.admin_site.admin_view(self.upload_zip_view),
                name="plugins_upload_zip_for_plugin",
            ),
            url_path(
                "download/<int:plugin_id>/",
                self.admin_site.admin_view(self.download_zip_view),
                name="plugins_download_zip",
            ),
            url_path(
                "scaffold/",
                self.admin_site.admin_view(self.scaffold_view),
                name="plugins_scaffold",
            ),
        ]
        return custom_urls + super().get_urls()

    def add_view(self, request, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context.setdefault("zip_form", PluginUploadZipForm())
        return super().add_view(request, form_url=form_url, extra_context=extra_context)

    def save_model(self, request, obj, form, change):
        target_status = form.cleaned_data.get("status") or PluginStatus.DEACTIVATED

        if target_status == PluginStatus.ACTIVATED:
            plugin_dir = get_plugin_dir(obj.slug)
            if not (plugin_dir / "manifest.json").exists():
                messages.error(
                    request,
                    _("Cannot activate plugin '%(slug)s' because package files are missing on disk.")
                    % {"slug": obj.slug},
                )
                target_status = PluginStatus.DEACTIVATED

        # Activation should always run through lifecycle validation.
        if target_status == PluginStatus.ACTIVATED:
            obj.status = PluginStatus.DEACTIVATED

        super().save_model(request, obj, form, change)

        try:
            if target_status == PluginStatus.ACTIVATED:
                PluginLifecycleManager.activate(obj, user=request.user)
            elif target_status == PluginStatus.DEACTIVATED:
                PluginLifecycleManager.deactivate(obj, user=request.user)
        except Exception as exc:
            messages.error(request, _("Failed to update plugin status: %(error)s") % {"error": str(exc)})

        sync_and_load_plugins()

    @admin.display(description="")
    def lifecycle_actions(self, obj):
        if not obj or not getattr(obj, "pk", None):
            return "-"

        upload_url = reverse("admin:plugins_upload_zip_for_plugin", args=[obj.id])
        download_url = reverse("admin:plugins_download_zip", args=[obj.id])
        deactivate_url = reverse("admin:plugins_deactivate", args=[obj.id])
        test_url = reverse("admin:plugins_test_connection", args=[obj.id])
        configure_url = reverse("admin:plugins_configure", args=[obj.id])

        # (url, label, title, extra_classes, icon, is_test_btn)
        buttons = [
            (
                upload_url,
                str(_("Upload ZIP")),
                str(_("Upload package for this plugin")),
                "bg-primary-600 border-primary-600 text-white hover:bg-primary-700 hover:border-primary-700",
                "upload",
                False,
            ),
            (
                download_url,
                str(_("Download ZIP")),
                str(_("Download plugin package as ZIP")),
                "bg-white border-base-300 text-base-700 hover:bg-base-100 dark:bg-base-800 dark:border-base-600 dark:text-base-200 dark:hover:bg-base-700",
                "download",
                False,
            ),
            (
                configure_url,
                str(_("Configure")),
                str(_("Open plugin configuration")),
                "bg-white border-base-300 text-base-700 hover:bg-base-100 dark:bg-base-800 dark:border-base-600 dark:text-base-200 dark:hover:bg-base-700",
                "settings",
                False,
            ),
            (
                test_url,
                str(_("Test connection")),
                str(_("Run plugin connection test")),
                "bg-white border-base-300 text-base-700 hover:bg-base-100 dark:bg-base-800 dark:border-base-600 dark:text-base-200 dark:hover:bg-base-700",
                "wifi_tethering",
                True,
            ),
        ]

        upload_help_raw = str(
            _(
                "How to upload: click Upload ZIP and choose a plugin package that contains at least manifest.json and entrypoint.py (additional files are optional)."
            )
        )
        upload_help_title = str(_("How to upload plugin ZIP"))

        _code = 'font-family:monospace;font-weight:700;background:rgba(0,0,0,0.08);padding:1px 5px;border-radius:3px;font-size:0.85em;'
        upload_help_html = upload_help_raw.replace(
            "manifest.json", f'<code style="{_code}">manifest.json</code>'
        ).replace(
            "entrypoint.py", f'<code style="{_code}">entrypoint.py</code>'
        )

        uid = f"plugin-test-result-{obj.pk}"
        link_tpl = (
            '<a href="{url}" title="{title}" class="inline-flex items-center gap-1.5 px-3 py-1.5 '
            'rounded-default border text-sm font-medium transition-colors {extra}">'
            '<span class="material-symbols-outlined" style="font-size:15px;line-height:1">{icon}</span>'
            '{label}</a>'
        )
        test_tpl = (
            '<button type="button" data-test-url="{url}" data-result-id="{uid}" title="{title}" '
            'class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-default border text-sm font-medium transition-colors {extra}">'
            '<span class="material-symbols-outlined" style="font-size:15px;line-height:1">{icon}</span>'
            '{label}</button>'
        )

        parts = []
        for (url, label, title, cls, icon, is_test) in buttons:
            if is_test:
                parts.append(test_tpl.format(url=url, uid=uid, title=title, extra=cls, icon=icon, label=label))
            else:
                parts.append(link_tpl.format(url=url, title=title, extra=cls, icon=icon, label=label))

        btn_html = mark_safe("".join(parts))

        test_result_html = mark_safe(
            f'<div id="{uid}" style="display:none" class="mt-2 px-3 py-2 rounded-default text-sm border"></div>'
        )

        # language=JavaScript
        js = mark_safe(f"""
<script>
(function() {{
  var btn = document.querySelector('[data-result-id="{uid}"]');
  if (!btn) return;
  btn.addEventListener('click', function() {{
    if (btn.dataset.loading) return;
    btn.dataset.loading = '1';
    var origContent = btn.innerHTML;
    btn.innerHTML = '<span class="material-symbols-outlined" style="font-size:15px;line-height:1">hourglass_top</span>{_("Testing…")}';
    btn.style.opacity = '0.7';
    btn.style.pointerEvents = 'none';
    var box = document.getElementById('{uid}');
    fetch(btn.dataset.testUrl, {{credentials:'same-origin'}})
      .then(function(r){{ return r.json(); }})
      .then(function(data) {{
        box.style.display = '';
        if (data.success) {{
          box.className = 'mt-2 px-3 py-2 rounded-default text-sm border bg-green-50 border-green-200 text-green-800 dark:bg-green-500/10 dark:border-green-500/30 dark:text-green-300';
          box.innerHTML = '<span class="material-symbols-outlined align-middle" style="font-size:15px">check_circle</span> ' + (data.message || '{_("Connection OK")}');
        }} else {{
          box.className = 'mt-2 px-3 py-2 rounded-default text-sm border bg-red-50 border-red-200 text-red-800 dark:bg-red-500/10 dark:border-red-500/30 dark:text-red-300';
          box.innerHTML = '<span class="material-symbols-outlined align-middle" style="font-size:15px">error</span> ' + (data.message || '{_("Connection failed")}');
        }}
      }})
      .catch(function(e) {{
        box.style.display = '';
        box.className = 'mt-2 px-3 py-2 rounded-default text-sm border bg-red-50 border-red-200 text-red-800 dark:bg-red-500/10 dark:border-red-500/30 dark:text-red-300';
        box.innerHTML = '<span class="material-symbols-outlined align-middle" style="font-size:15px">error</span> {_("Request failed")}';
      }})
      .finally(function() {{
        btn.innerHTML = origContent;
        btn.style.opacity = '';
        btn.style.pointerEvents = '';
        delete btn.dataset.loading;
      }});
  }});
}})();
</script>""")

        return format_html(
            '<div style="display:flex; flex-wrap:wrap; gap:8px;">{}</div>'
            '{}'
            '<div class="mt-2 px-3 py-2 rounded-default text-sm bg-blue-50 border border-blue-200 text-blue-800 dark:bg-blue-500/10 dark:border-blue-500/30 dark:text-blue-300">'
            '<p class="m-0 font-semibold">{}</p><p class="m-0 mt-1">{}</p></div>'
            '{}',
            btn_html,
            test_result_html,
            upload_help_title,
            mark_safe(upload_help_html),
            js,
        )

    @admin.display(description=_("Store owner summary"))
    def store_owner_status(self, obj):
        if not obj or not getattr(obj, "pk", None):
            return "-"

        latest_log = obj.logs.order_by("-created_at").first()
        latest_error = obj.logs.filter(level="error").order_by("-created_at").first()
        latest_warning = obj.logs.filter(level="warning").order_by("-created_at").first()

        if obj.status != PluginStatus.ACTIVATED:
            headline = _("Plugin is turned off.")
            guidance = _("Activate it when you want to use this integration in your store.")
        elif latest_error:
            headline = _("Plugin needs attention.")
            guidance = _(
                "Check plugin configuration and credentials. If this repeats, open full diagnostics and send them to support."
            )
        elif latest_warning:
            headline = _("Plugin is working, but with warnings.")
            guidance = _("You can keep using it, but monitor recent activity for repeated warnings.")
        else:
            headline = _("Plugin is working normally.")
            guidance = _("No action needed right now.")

        if latest_log:
            last_event = _humanize_event_type(latest_log.event_type)
            last_seen = latest_log.created_at.strftime("%Y-%m-%d %H:%M")
            latest_activity = _("Latest activity: %(event)s (%(when)s)") % {"event": last_event, "when": last_seen}
        else:
            latest_activity = _("No activity logs yet.")

        return format_html(
            "<strong>{}</strong><br><span>{}</span><br><span>{}</span>",
            headline,
            latest_activity,
            guidance,
        )

    def _build_admin_context(self, request: HttpRequest, *, plugin: Plugin, title: str) -> dict:
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "original": plugin,
            "title": title,
            "plugin": plugin,
        }
        return context

    def _require_change_permission(self, request: HttpRequest) -> None:
        if not self.has_change_permission(request):
            raise PermissionDenied

    def _format_validation_message(self, message) -> str:
        text = f"[{message.code}] {message.message}"
        if message.hint:
            text += f" {_('Fix')}: {message.hint}"
        return text

    def _emit_zip_validation_messages(self, request: HttpRequest, report, *, strict: bool) -> None:
        for error in report.errors:
            messages.error(request, self._format_validation_message(error))

        for warning in report.warnings:
            rendered_warning = self._format_validation_message(warning)
            if strict:
                messages.error(request, rendered_warning)
            else:
                messages.warning(request, rendered_warning)

    def _run_test_connection(self, request: HttpRequest, plugin: Plugin) -> dict:
        fallback_message = str(_("No test connection handler available."))
        payload = registry.apply_filters(
            "plugin.test_connection",
            {"success": False, "message": fallback_message},
            request=request,
            plugin_slug=plugin.slug,
            plugin=plugin,
        )

        if isinstance(payload, dict) and (
            payload.get("success") or str(payload.get("message") or "").strip() != fallback_message
        ):
            return payload

        direct_payload = self._run_direct_test_connection(request, plugin)
        if direct_payload is not None:
            return direct_payload

        return payload if isinstance(payload, dict) else {"success": False, "message": fallback_message}

    def _run_direct_test_connection(self, request: HttpRequest, plugin: Plugin) -> dict | None:
        plugin_dir = Path(plugin.package_path or "")
        if not plugin_dir.exists():
            plugin_dir = get_plugin_dir(plugin.slug)

        entrypoint = plugin_dir / (plugin.entrypoint or "entrypoint.py")
        if not entrypoint.exists():
            return None

        module_name = f"plugin_test_connection_{plugin.slug}"
        spec = importlib.util.spec_from_file_location(module_name, entrypoint)
        if not spec or not spec.loader:
            return None

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
            test_func = getattr(module, "test_connection", None)
            if not callable(test_func):
                return None
            payload = test_func(
                {"success": False, "message": str(_("No test connection handler available."))},
                plugin_slug=plugin.slug,
                plugin=plugin,
                request=request,
            )
            if isinstance(payload, dict):
                return payload
            return {
                "success": False,
                "message": str(_("Plugin test connection returned invalid payload.")),
            }
        except Exception as exc:
            return {
                "success": False,
                "message": str(_("Connection test failed: %(error)s")) % {"error": str(exc)},
            }

    @admin.action(description=_("Activate selected plugins"))
    def activate_selected(self, request: HttpRequest, queryset):
        for plugin in queryset:
            try:
                PluginLifecycleManager.activate(plugin, user=request.user)
            except Exception as exc:
                self.message_user(
                    request, _("Failed to activate %(slug)s: %(err)s") % {"slug": plugin.slug, "err": exc}
                )
        sync_and_load_plugins()

    @admin.action(description=_("Deactivate selected plugins"))
    def deactivate_selected(self, request: HttpRequest, queryset):
        for plugin in queryset:
            PluginLifecycleManager.deactivate(plugin, user=request.user)
        sync_and_load_plugins()

    @admin.action(description=_("Sync selected plugins from disk"))
    def sync_selected(self, request: HttpRequest, queryset):
        for plugin in queryset:
            plugin_dir = get_plugin_dir(plugin.slug)
            if plugin_dir.exists():
                PluginLifecycleManager.install_or_update_from_directory(plugin_dir, user=request.user)
        sync_and_load_plugins()

    def sync_from_disk_view(self, request: HttpRequest):
        self._require_change_permission(request)
        sync_and_load_plugins()
        messages.success(request, _("Plugins synchronized from disk."))
        return redirect(reverse("admin:plugins_plugin_changelist"))

    def deactivate_single_view(self, request: HttpRequest, plugin_id: int):
        self._require_change_permission(request)
        plugin = Plugin.objects.filter(id=plugin_id).first()
        if not plugin:
            messages.error(request, _("Plugin not found."))
            return redirect(reverse("admin:plugins_plugin_changelist"))
        PluginLifecycleManager.deactivate(plugin, user=request.user)
        sync_and_load_plugins()
        messages.success(request, _("Plugin deactivated."))
        return redirect(reverse("admin:plugins_plugin_change", args=[plugin.id]))

    def test_connection_view(self, request: HttpRequest, plugin_id: int):
        self._require_change_permission(request)
        plugin = Plugin.objects.filter(id=plugin_id).first()
        if not plugin:
            return JsonResponse({"success": False, "message": str(_("Plugin not found."))}, status=404)

        payload = self._run_test_connection(request, plugin)
        return JsonResponse(payload)

    def configure_view(self, request: HttpRequest, plugin_id: int):
        if not self.has_change_permission(request):
            raise PermissionDenied

        plugin = Plugin.objects.filter(id=plugin_id).first()
        if not plugin:
            messages.error(request, _("Plugin not found."))
            return redirect(reverse("admin:plugins_plugin_changelist"))

        test_payload: dict | None = None
        if request.method == "POST":
            form = PluginConfigForm(plugin, request.POST)
            if form.is_valid():
                plugin.config = form.to_config_payload()
                plugin.save(update_fields=["config", "updated_at"])
                messages.success(request, _("Plugin configuration saved."))
                if plugin.status == PluginStatus.ACTIVATED:
                    sync_and_load_plugins()

                if "_save_and_test" in request.POST:
                    test_payload = self._run_test_connection(request, plugin)
                    if test_payload.get("success"):
                        messages.success(request, test_payload.get("message") or str(_("Connection test succeeded.")))
                    else:
                        messages.error(request, test_payload.get("message") or str(_("Connection test failed.")))
                    form = PluginConfigForm(plugin)
                else:
                    return redirect(reverse("admin:plugins_plugin_change", args=[plugin.id]))
        else:
            form = PluginConfigForm(plugin)

        context = self._build_admin_context(
            request,
            plugin=plugin,
            title=str(_("Configure plugin")),
        )
        context["form"] = form
        context["test_payload"] = test_payload
        context["required_field_labels"] = [field.label for field in form.fields.values() if field.required]
        context["env_resolved_fields"] = form.env_resolved_fields
        context["env_vars_mapping"] = form.env_vars_mapping
        return TemplateResponse(request, "admin/plugins/plugin/configure.html", context)

    @admin.display(description=_("Package"))
    def package_info(self, obj):
        if not obj or not getattr(obj, "pk", None):
            return "-"
        plugin_dir = Path(str(obj.package_path or "").strip())
        if not plugin_dir.exists():
            plugin_dir = get_plugin_dir(obj.slug)

        manifest_path = plugin_dir / "manifest.json"
        if not manifest_path.exists():
            return format_html(
                '<span class="inline-flex items-center gap-1 text-sm text-amber-600 dark:text-amber-400">'
                '<span class="material-symbols-outlined" style="font-size:14px">warning</span>{}</span>',
                _("Plugin files not found on disk — upload a ZIP or place files in the plugins/ directory."),
            )
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return format_html(
                '<span class="text-sm text-red-600 dark:text-red-400">{}</span>',
                _("Invalid manifest.json"),
            )

        version = str(manifest.get("version") or "—")
        entrypoint_file = str(manifest.get("entrypoint") or "entrypoint.py")
        scopes = [str(s) for s in (manifest.get("scopes") or [])]
        path_str = str(plugin_dir)

        scope_badges = "".join(
            f'<span style="background:rgba(124,58,237,0.08);border:1px solid rgba(124,58,237,0.25);'
            f'color:#7c3aed;border-radius:9999px;padding:2px 8px;font-size:11px;font-weight:500;">{s}</span>'
            for s in scopes
        ) or '<span style="color:#9ca3af;font-size:11px;">none</span>'

        file_parts = []
        if plugin_dir.exists():
            for f in sorted(plugin_dir.iterdir()):
                if f.is_file() and "__pycache__" not in str(f):
                    sz = f.stat().st_size
                    sz_str = f"{sz/1024:.1f}KB" if sz >= 1024 else f"{sz}B"
                    file_parts.append(
                        f'<span style="font-family:monospace;font-size:11px;background:#f3f4f6;'
                        f'border:1px solid #e5e7eb;border-radius:4px;padding:2px 7px;">'
                        f'{f.name}<span style="color:#9ca3af;margin-left:4px">{sz_str}</span></span>'
                    )
        files_row = (
            f'<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:6px;">{"".join(file_parts)}</div>'
            if file_parts else ""
        )

        return format_html(
            '<div style="font-size:13px;line-height:1.6;">'
            '<div style="display:flex;flex-wrap:wrap;gap:16px;align-items:center;">'
            '<span><span style="color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.04em;font-weight:600;">VERSION</span> '
            '<code style="font-size:12px;">{}</code></span>'
            '<span><span style="color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.04em;font-weight:600;">ENTRYPOINT</span> '
            '<code style="font-size:12px;">{}</code></span>'
            '<span style="display:inline-flex;align-items:center;gap:4px;">'
            '<span style="color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.04em;font-weight:600;">SCOPES</span> {}</span>'
            '</div>'
            '{}'
            '<div style="margin-top:4px;color:#374151;font-size:11px;font-family:monospace;">{}</div>'
            '</div>',
            version,
            entrypoint_file,
            mark_safe(scope_badges),
            mark_safe(files_row),
            path_str,
        )

    def scaffold_view(self, request: HttpRequest):
        """Generate and download a ready-to-upload starter plugin ZIP."""
        if not self.has_add_permission(request):
            raise PermissionDenied

        from django.utils.text import slugify

        slug = request.GET.get("slug", "").strip().lower()
        name = request.GET.get("name", "").strip()
        has_config = bool(request.GET.get("has_config"))

        if slug and name:
            # Sanitize slug
            slug = slugify(slug) or "my-plugin"
            manifest = _scaffold_manifest(slug, name, "1.0.0", has_config)
            entrypoint = _scaffold_entrypoint(slug)
            schema = _scaffold_schema() if has_config else None

            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(f"{slug}/manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
                zf.writestr(f"{slug}/entrypoint.py", entrypoint)
                if schema:
                    zf.writestr(f"{slug}/config.schema.json", json.dumps(schema, indent=2, ensure_ascii=False))
            buf.seek(0)
            response = HttpResponse(buf.read(), content_type="application/zip")
            response["Content-Disposition"] = f'attachment; filename="{slug}-scaffold.zip"'
            return response

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": str(_("Generate plugin scaffold")),
        }
        return TemplateResponse(request, "admin/plugins/plugin/scaffold.html", context)

    def download_zip_view(self, request: HttpRequest, plugin_id: int):
        if not self.has_change_permission(request):
            raise PermissionDenied

        plugin = Plugin.objects.filter(id=plugin_id).first()
        if not plugin:
            messages.error(request, _("Plugin not found."))
            return redirect(reverse("admin:plugins_plugin_changelist"))

        plugin_dir = Path(plugin.package_path or "")
        if not plugin_dir.exists():
            plugin_dir = get_plugin_dir(plugin.slug)

        if not plugin_dir.exists():
            messages.error(request, _("Plugin files not found on disk."))
            return redirect(reverse("admin:plugins_plugin_change", args=[plugin_id]))

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in sorted(plugin_dir.rglob("*")):
                if file_path.is_file() and "__pycache__" not in file_path.parts:
                    zf.write(file_path, file_path.relative_to(plugin_dir))

        buffer.seek(0)
        response = HttpResponse(buffer.read(), content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{plugin.slug}.zip"'
        return response

    def upload_zip_view(self, request: HttpRequest, plugin_id: int | None = None):
        if plugin_id is None:
            if not self.has_add_permission(request):
                raise PermissionDenied
        else:
            self._require_change_permission(request)

        locked_plugin = None
        if plugin_id is not None:
            locked_plugin = Plugin.objects.filter(id=plugin_id).first()
            if not locked_plugin:
                messages.error(request, _("Plugin not found."))
                return redirect(reverse("admin:plugins_plugin_changelist"))

        if request.method == "POST":
            form = PluginUploadZipForm(request.POST, request.FILES)
            if form.is_valid():
                archive = form.cleaned_data["archive"]
                activate_after_install = bool(form.cleaned_data.get("activate_after_install"))
                strict_validation = bool(form.cleaned_data.get("strict_validation"))

                temp_path: Path | None = None
                try:
                    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                        for chunk in archive.chunks():
                            tmp.write(chunk)
                        temp_path = Path(tmp.name)

                    report = PluginZipValidator(temp_path).validate()

                    if report.manifest and locked_plugin and report.manifest.slug != locked_plugin.slug:
                        messages.error(
                            request,
                            _("Uploaded package slug '%(uploaded)s' does not match selected plugin '%(expected)s'.")
                            % {"uploaded": report.manifest.slug, "expected": locked_plugin.slug},
                        )
                        return redirect(reverse("admin:plugins_plugin_change", args=[locked_plugin.id]))

                    has_blocking_errors = bool(report.errors)
                    warnings_block_install = strict_validation and bool(report.warnings)
                    self._emit_zip_validation_messages(request, report, strict=strict_validation)

                    if has_blocking_errors or warnings_block_install:
                        if warnings_block_install and not has_blocking_errors:
                            messages.error(
                                request,
                                _("Strict validation blocked installation because warnings were found."),
                            )
                    else:
                        plugin = PluginLifecycleManager.install_or_update_from_zip(temp_path, user=request.user)

                        if activate_after_install and plugin.status != PluginStatus.ACTIVATED:
                            PluginLifecycleManager.activate(plugin, user=request.user)
                        sync_and_load_plugins()
                        messages.success(request, _("Plugin package uploaded successfully."))
                        return redirect(reverse("admin:plugins_plugin_change", args=[plugin.id]))

                except Exception as exc:
                    messages.error(request, _("Failed to upload plugin package: %(error)s") % {"error": str(exc)})
                finally:
                    if temp_path and temp_path.exists():
                        temp_path.unlink(missing_ok=True)
        else:
            form = PluginUploadZipForm()

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": (
                str(_("Upload plugin package"))
                if not locked_plugin
                else str(_("Upload plugin package for %(plugin)s")) % {"plugin": locked_plugin.name}
            ),
            "form": form,
            "plugin": locked_plugin,
        }
        return TemplateResponse(request, "admin/plugins/plugin/upload_zip.html", context)

    def get_deleted_objects(self, objs, request):
        """Keep delete confirmation fast by summarizing related rows instead of enumerating them."""
        if hasattr(objs, "model") and objs.model is self.model:
            plugin_queryset = objs
        else:
            plugin_ids = [obj.pk for obj in objs if getattr(obj, "pk", None)]
            plugin_queryset = self.model.objects.filter(pk__in=plugin_ids)

        plugin_count = plugin_queryset.count()
        if not plugin_count:
            return [], {}, set(), []

        deleted_objects = [
            str(_("Plugin: %(name)s") % {"name": plugin})
            for plugin in plugin_queryset.order_by("pk")[: self.delete_related_preview_limit]
        ]
        if plugin_count > self.delete_related_preview_limit:
            hidden_plugins_count = plugin_count - self.delete_related_preview_limit
            deleted_objects.append(
                str(_("%(count)s additional plugins are hidden.") % {"count": hidden_plugins_count})
            )

        model_count = {str(self.model._meta.verbose_name_plural): plugin_count}
        perms_needed = set()

        related_models = (
            PluginKVData,
            PluginMigrationState,
            PluginWebhookEvent,
            PluginLog,
        )
        for related_model in related_models:
            related_count = related_model.objects.filter(plugin__in=plugin_queryset).count()
            if not related_count:
                continue

            model_count[str(related_model._meta.verbose_name_plural)] = related_count
            deleted_objects.append(
                str(
                    _("%(model)s: %(count)s related objects (not listed individually).")
                    % {
                        "model": related_model._meta.verbose_name_plural,
                        "count": related_count,
                    }
                )
            )

            delete_perm = get_permission_codename("delete", related_model._meta)
            if not request.user.has_perm(f"{related_model._meta.app_label}.{delete_perm}"):
                perms_needed.add(str(related_model._meta.verbose_name))

        return deleted_objects, model_count, perms_needed, []

    def _delete_plugin(self, request: HttpRequest, plugin: Plugin) -> None:
        if plugin.slug in _get_bundled_plugin_slugs():
            plugin_dir = _resolve_plugin_directory_for_backup(plugin)
            if plugin_dir is not None:
                _write_plugin_backup_zip(plugin_dir, _resolve_bundled_plugin_zip_path(plugin.slug))

        PluginLifecycleManager.uninstall(plugin, purge_data=False, user=request.user)
        PluginLifecycleManager.remove_plugin_files(plugin)
        plugin.delete()

    def delete_model(self, request: HttpRequest, obj: Plugin) -> None:
        self._delete_plugin(request, obj)
        sync_and_load_plugins()

    def delete_queryset(self, request: HttpRequest, queryset) -> None:
        for plugin in queryset:
            self._delete_plugin(request, plugin)
        sync_and_load_plugins()


@admin.register(PluginWebhookEvent)
class PluginWebhookEventAdmin(HistoryModelAdmin):
    list_display = ("created_at", "plugin", "hook_name", "status", "provider_event_id")
    list_filter = ("status", "plugin", "hook_name")
    search_fields = ("provider_event_id", "payload_hash", "error_message")
    readonly_fields = (
        "plugin",
        "hook_name",
        "status",
        "provider_event_id",
        "payload_hash",
        "payload",
        "processed_at",
        "error_message",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PluginKVData)
class PluginKVDataAdmin(HistoryModelAdmin):
    list_display = ("plugin", "namespace", "key", "updated_at")
    list_filter = ("plugin", "namespace")
    search_fields = ("key",)


@admin.register(PluginMigrationState)
class PluginMigrationStateAdmin(HistoryModelAdmin):
    list_display = ("plugin", "version", "migration_name", "direction", "applied", "updated_at")
    list_filter = ("applied", "direction", "plugin")
    search_fields = ("migration_name", "version")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PluginLog)
class PluginLogAdmin(HistoryModelAdmin):
    list_display = ("created_at", "plugin", "owner_event", "owner_result", "owner_impact", "technical_details")
    list_filter = ("level", "event_type", "plugin")
    search_fields = ("message", "event_type", "correlation_id")
    readonly_fields = (
        "plugin",
        "level",
        "event_type",
        "message",
        "payload",
        "correlation_id",
        "user",
        "created_at",
    )
    list_per_page = 50
    ordering = ("-created_at",)

    @admin.display(description=_("What happened"))
    def owner_event(self, obj):
        return _humanize_event_type(obj.event_type)

    @admin.display(description=_("Result"))
    def owner_result(self, obj):
        return _owner_result(obj.level)

    @admin.display(description=_("Description"))
    def owner_impact(self, obj):
        return _owner_impact(obj.event_type, obj.level)

    @admin.display(description=_("Details"))
    def technical_details(self, obj):
        return _technical_details_markup(obj)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
