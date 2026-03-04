from __future__ import annotations

import json
import os
from itertools import count
from pathlib import Path

from django import forms
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.plugins.engine.lifecycle import PluginLifecycleManager, get_plugin_dir
from apps.plugins.models import Plugin, PluginStatus

_SECRET_UNCHANGED = "__secret_unchanged__"


def _normalize_env_vars_mapping(env_vars_raw) -> dict[str, str]:
    if not isinstance(env_vars_raw, dict):
        return {}
    return {
        str(key).strip(): str(value).strip()
        for key, value in env_vars_raw.items()
        if str(key).strip() and str(value).strip()
    }


def _load_schema_from_plugin_files(plugin: Plugin) -> tuple[dict, dict[str, str]]:
    package_path_raw = str(plugin.package_path or "").strip()
    if not package_path_raw:
        return {}, {}
    package_path = Path(package_path_raw)

    schema_path = package_path / "config.schema.json"
    if not schema_path.exists() or not schema_path.is_file():
        return {}, {}

    try:
        raw_schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except Exception:
        return {}, {}

    if not isinstance(raw_schema, dict):
        return {}, {}

    env_vars = _normalize_env_vars_mapping(raw_schema.get("env_vars"))
    if not env_vars:
        env_vars = _normalize_env_vars_mapping(raw_schema.get("x_env_vars"))

    if not env_vars:
        properties = raw_schema.get("properties") or {}
        if isinstance(properties, dict):
            for key, field_schema in properties.items():
                if not isinstance(field_schema, dict):
                    continue
                env_var_name = str(
                    field_schema.get("env_var")
                    or field_schema.get("x_env_var")
                    or field_schema.get("x-env-var")
                    or ""
                ).strip()
                if env_var_name:
                    env_vars[str(key).strip()] = env_var_name

    return raw_schema, env_vars


def _looks_like_secret_field(key: str, field_schema: dict) -> bool:
    fmt = str(field_schema.get("format") or "").lower()
    if fmt == "password":
        return True

    normalized = key.lower()
    if "secret" in normalized or "password" in normalized:
        return True
    if normalized in {
        "api_key",
        "crc_key",
        "access_key",
        "private_key",
        "client_secret",
        "auth_token",
        "token",
    }:
        return True
    if normalized.endswith("_token"):
        return True
    return normalized.endswith("_key") and normalized not in {"site_key", "public_key"}


def _build_schema_field(*, key: str, field_schema: dict, required: bool, initial):
    field_type = str(field_schema.get("type") or "string")
    label = str(field_schema.get("title") or key.replace("_", " ").title())
    help_text = str(field_schema.get("description") or "")
    enum_values = field_schema.get("enum")

    if isinstance(enum_values, list) and enum_values:
        choices = [(str(item), str(item)) for item in enum_values]
        return forms.ChoiceField(
            label=label,
            help_text=help_text,
            required=required,
            choices=choices,
            initial="" if initial is None else str(initial),
        )

    if field_type == "boolean":
        return forms.BooleanField(label=label, help_text=help_text, required=False, initial=bool(initial))

    if field_type == "integer":
        return forms.IntegerField(label=label, help_text=help_text, required=required, initial=initial)

    if field_type == "number":
        return forms.FloatField(label=label, help_text=help_text, required=required, initial=initial)

    widget = None
    if str(field_schema.get("format") or "").lower() == "password":
        # Do not render stored secrets back into HTML after save.
        widget = forms.PasswordInput(
            render_value=True,
            attrs={"data-secret-field": "true", "autocomplete": "new-password"},
        )

    return forms.CharField(
        label=label,
        help_text=help_text,
        required=required,
        initial="" if initial is None else str(initial),
        widget=widget,
    )


class PluginAdminForm(forms.ModelForm):
    class Meta:
        model = Plugin
        fields = ("name", "status")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._generated_slug = ""
        self._resolved_plugin_dir = None

    def _build_unique_slug(self, name: str) -> str:
        base_slug = slugify(name) or "plugin"
        candidate = base_slug[:120].strip("-") or "plugin"

        queryset = Plugin.objects.all()
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)

        if not queryset.filter(slug=candidate).exists():
            return candidate

        for idx in count(2):
            suffix = f"-{idx}"
            trimmed = base_slug[: max(1, 120 - len(suffix))].rstrip("-") or "plugin"
            candidate = f"{trimmed}{suffix}"
            if not queryset.filter(slug=candidate).exists():
                return candidate

    def clean(self):
        cleaned = super().clean()
        if self.instance.pk:
            return cleaned

        name = str(cleaned.get("name") or "").strip()
        self._generated_slug = self._build_unique_slug(name)

        plugin_dir = get_plugin_dir(self._generated_slug)
        if (plugin_dir / "manifest.json").exists():
            self._resolved_plugin_dir = plugin_dir

        return cleaned

    def save(self, commit=True):
        if self.instance.pk:
            plugin = super().save(commit=False)
        elif self._resolved_plugin_dir is not None:
            plugin = PluginLifecycleManager.install_or_update_from_directory(self._resolved_plugin_dir)
            plugin.name = self.cleaned_data.get("name") or plugin.name
            plugin.slug = self._generated_slug or plugin.slug
        else:
            plugin = super().save(commit=False)
            plugin.slug = self._generated_slug or plugin.slug

        plugin.status = self.cleaned_data.get("status") or PluginStatus.DEACTIVATED

        if not plugin.package_path:
            plugin.package_path = str(get_plugin_dir(plugin.slug))
        if not plugin.entrypoint:
            plugin.entrypoint = "entrypoint.py"
        if not plugin.version:
            plugin.version = "0.0.0"

        if commit:
            plugin.save()
        return plugin


class PluginConfigForm(forms.Form):
    """Simple schema-driven form for non-technical plugin config editing."""

    def __init__(self, plugin: Plugin, *args, **kwargs):
        self.plugin = plugin
        self._secret_fields: set[str] = set()
        self._env_resolved_fields: dict[str, str] = {}
        self._env_vars: dict[str, str] = {}
        super().__init__(*args, **kwargs)

        schema = plugin.config_schema or {}
        env_vars = _normalize_env_vars_mapping((plugin.manifest or {}).get("env_vars"))

        has_schema_properties = bool((schema or {}).get("properties")) if isinstance(schema, dict) else False
        if not has_schema_properties or not env_vars:
            file_schema, file_env_vars = _load_schema_from_plugin_files(plugin)
            if not has_schema_properties and file_schema:
                schema = file_schema
            if not env_vars and file_env_vars:
                env_vars = file_env_vars

        self._env_vars = dict(env_vars)
        properties = schema.get("properties") or {}
        required_fields = set(schema.get("required") or [])

        for key, field_schema in properties.items():
            initial = (plugin.config or {}).get(key, field_schema.get("default"))
            is_secret = _looks_like_secret_field(key, field_schema)

            # Check if this field has an env-var override.
            env_var_name = env_vars.get(key, "")
            env_var_value = os.environ.get(env_var_name) if env_var_name else None
            env_is_set = env_var_value is not None and env_var_name

            if is_secret:
                self._secret_fields.add(key)
                if env_is_set:
                    # Env var overrides the stored secret – show placeholder, not actual value.
                    initial = _SECRET_UNCHANGED
                else:
                    has_existing_secret = str((plugin.config or {}).get(key) or "").strip() != ""
                    initial = _SECRET_UNCHANGED if has_existing_secret else ""

            # For existing configured secrets allow blank submit to preserve current value.
            has_existing_secret = is_secret and str((plugin.config or {}).get(key) or "").strip() != ""
            required = (key in required_fields) and not has_existing_secret and not env_is_set
            self.fields[key] = _build_schema_field(
                key=key,
                field_schema=field_schema,
                required=required,
                initial=initial,
            )

            field = self.fields[key]

            # If value comes from environment variable, show resolved value and mark field.
            if env_is_set:
                self._env_resolved_fields[key] = env_var_name
                field.required = False
                env_help = _(
                    "Effective value comes from environment variable %(var)s. "
                    "You can still save a fallback value here, used when the variable is not set."
                ) % {"var": env_var_name}
                existing_help = str(field.help_text or "").strip()
                field.help_text = f"{existing_help} — {env_help}" if existing_help else str(env_help)

            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                existing = str(widget.attrs.get("class") or "").strip()
                widget.attrs["class"] = (
                    (existing + " ") if existing else ""
                ) + "h-4 w-4 rounded border-base-300 text-primary-600 focus:ring-primary-600"
            else:
                existing = str(widget.attrs.get("class") or "").strip()
                widget.attrs["class"] = ((existing + " ") if existing else "") + (
                    "w-full rounded-default border border-base-300 bg-white px-3 py-2 text-sm "
                    "text-font-important-light shadow-xs focus:border-primary-500 focus:outline-none "
                    "focus:ring-2 focus:ring-primary-500/20 dark:border-base-700 dark:bg-base-900 "
                    "dark:text-font-important-dark"
                )

            if isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("rows", 4)

    @property
    def env_resolved_fields(self) -> dict[str, str]:
        """Return mapping of field key → env var name for fields resolved from environment."""
        return dict(self._env_resolved_fields)

    @property
    def env_vars_mapping(self) -> list[dict[str, str]]:
        """Return full env_vars mapping with status for each variable."""
        result = []
        for key, var_name in self._env_vars.items():
            env_value = os.environ.get(var_name)
            result.append(
                {
                    "config_key": key,
                    "env_var": var_name,
                    "is_set": env_value is not None,
                    "label": str((self.fields[key].label or key) if key in self.fields else key),
                }
            )
        return result

    def to_config_payload(self) -> dict:
        payload = dict(self.plugin.config or {})
        for key in self.fields:
            value = self.cleaned_data.get(key)

            if key in self._secret_fields:
                if value == _SECRET_UNCHANGED:
                    # Preserve stored secret when user did not touch this field.
                    continue
                if str(value or "").strip() == "":
                    # Preserve stored secret when field is submitted empty.
                    continue
            payload[key] = value
        return payload


class PluginUploadZipForm(forms.Form):
    archive = forms.FileField(label=_("Plugin ZIP package"))
    activate_after_install = forms.BooleanField(
        label=_("Activate after install"),
        required=False,
        initial=True,
    )
    strict_validation = forms.BooleanField(
        label=_("Strict validation (block install on warnings)"),
        required=False,
        initial=False,
        help_text=_("When enabled, warnings from ZIP preflight validation are treated as blocking issues."),
    )

    def clean_archive(self):
        archive = self.cleaned_data["archive"]
        name = str(getattr(archive, "name", "")).lower()
        if not name.endswith(".zip"):
            raise forms.ValidationError(_("Only .zip files are supported."))
        return archive
