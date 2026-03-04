from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from django.conf import settings
from django.db import transaction

from apps.plugins.engine.exceptions import PluginDependencyError, PluginManifestError
from apps.plugins.engine.log_utils import log_plugin_event
from apps.plugins.engine.manifest import PluginManifest, parse_manifest
from apps.plugins.models import (
    Plugin,
    PluginMigrationState,
    PluginStatus,
)


_VERSION_NUMBER_RE = re.compile(r"\d+")
_REGISTERED_HOOK_RE = re.compile(r"api\.register_(?:filter|action|async_action)\(\s*[\"']([^\"']+)[\"']")


def _numeric_version_parts(version: str) -> tuple[int, ...]:
    raw = str(version or "").strip()
    if not raw:
        return (0,)

    numbers = [int(token) for token in _VERSION_NUMBER_RE.findall(raw)]
    return tuple(numbers or [0])


def _is_version_lower(current_version: str, min_version: str) -> bool:
    current_parts = list(_numeric_version_parts(current_version))
    required_parts = list(_numeric_version_parts(min_version))
    max_len = max(len(current_parts), len(required_parts))

    current_parts.extend([0] * (max_len - len(current_parts)))
    required_parts.extend([0] * (max_len - len(required_parts)))
    return tuple(current_parts) < tuple(required_parts)


def get_plugins_root() -> Path:
    raw = getattr(settings, "PLUGINS_DIR", settings.BASE_DIR / "plugins")
    return Path(raw)


def get_plugin_dir(slug: str) -> Path:
    return get_plugins_root() / slug


def clear_runtime_plugin_directories(*, preserve: set[str] | None = None) -> list[str]:
    """Delete plugin directories from PLUGINS_DIR, preserving selected top-level names."""
    root = get_plugins_root()
    if not root.exists():
        return []

    preserved = set(preserve or set())
    removed: list[str] = []
    for path in root.iterdir():
        if not path.is_dir() or path.name in preserved:
            continue
        shutil.rmtree(path, ignore_errors=True)
        removed.append(path.name)
    return removed


def calculate_directory_checksum(path: Path) -> str:
    hasher = hashlib.sha256()
    for file_path in sorted(path.rglob("*")):
        if file_path.is_dir() or ".git" in file_path.parts or "__pycache__" in file_path.parts:
            continue
        rel = str(file_path.relative_to(path)).replace("\\", "/")
        hasher.update(rel.encode("utf-8"))
        hasher.update(file_path.read_bytes())
    return hasher.hexdigest()


def _normalize_env_vars_mapping(env_vars_raw: dict | None) -> dict[str, str]:
    if not isinstance(env_vars_raw, dict):
        return {}
    return {
        str(key).strip(): str(value).strip()
        for key, value in env_vars_raw.items()
        if str(key).strip() and str(value).strip()
    }


def _key_looks_like_secret(key: str) -> bool:
    normalized = key.lower()
    if "secret" in normalized or "password" in normalized:
        return True
    if normalized in {"api_key", "crc_key", "access_key", "private_key", "client_secret", "auth_token", "token"}:
        return True
    if normalized.endswith("_token"):
        return True
    return normalized.endswith("_key") and normalized not in {"site_key", "public_key"}


def _infer_config_schema_from_manifest(default_config: dict, env_vars: dict) -> dict:
    """Auto-generate a minimal config_schema from default_config + env_vars in manifest."""
    all_keys = list(dict.fromkeys(list(default_config.keys()) + list(env_vars.keys())))
    if not all_keys:
        return {}

    properties: dict = {}
    for key in all_keys:
        default = default_config.get(key)
        field: dict = {}

        if isinstance(default, bool):
            field["type"] = "boolean"
        elif isinstance(default, int):
            field["type"] = "integer"
        elif isinstance(default, float):
            field["type"] = "number"
        else:
            field["type"] = "string"

        field["title"] = key.replace("_", " ").title()

        if default is not None:
            field["default"] = default

        if field["type"] == "string" and _key_looks_like_secret(key):
            field["format"] = "password"

        properties[key] = field

    schema: dict = {"type": "object", "properties": properties}
    if env_vars:
        schema["env_vars"] = dict(env_vars)
    return schema


def _load_config_schema_bundle_from_directory(plugin_dir: Path) -> tuple[dict, dict[str, str]]:
    schema_path = plugin_dir / "config.schema.json"
    if not schema_path.exists() or not schema_path.is_file():
        return {}, {}

    try:
        raw_schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PluginManifestError(f"Invalid config.schema.json in {plugin_dir}") from exc

    if not isinstance(raw_schema, dict):
        raise PluginManifestError("config.schema.json must be a JSON object.")

    env_vars = _normalize_env_vars_mapping(raw_schema.get("env_vars"))
    if not env_vars:
        env_vars = _normalize_env_vars_mapping(raw_schema.get("x_env_vars"))

    if not env_vars:
        properties = raw_schema.get("properties") or {}
        if isinstance(properties, dict):
            for key, field_schema in properties.items():
                if not isinstance(field_schema, dict):
                    continue
                env_name = str(
                    field_schema.get("env_var")
                    or field_schema.get("x_env_var")
                    or field_schema.get("x-env-var")
                    or ""
                ).strip()
                if env_name:
                    env_vars[str(key).strip()] = env_name

    return raw_schema, env_vars


def load_manifest_from_directory(plugin_dir: Path) -> PluginManifest:
    manifest_path = plugin_dir / "manifest.json"
    if not manifest_path.exists():
        raise PluginManifestError(f"Missing manifest.json in {plugin_dir}")

    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PluginManifestError(f"Invalid manifest.json in {plugin_dir}") from exc

    if not isinstance(raw, dict):
        raise PluginManifestError("manifest.json must be a JSON object.")

    file_schema, file_env_vars = _load_config_schema_bundle_from_directory(plugin_dir)
    if not (raw.get("config_schema") or {}):
        raw["config_schema"] = file_schema
    if not (raw.get("env_vars") or {}) and file_env_vars:
        raw["env_vars"] = file_env_vars

    # Auto-generate schema from default_config + env_vars when no explicit schema provided.
    if not (raw.get("config_schema") or {}):
        default_cfg = raw.get("default_config") or {}
        env_vars_raw = raw.get("env_vars") or {}
        if isinstance(default_cfg, dict) and isinstance(env_vars_raw, dict):
            inferred = _infer_config_schema_from_manifest(default_cfg, env_vars_raw)
            if inferred:
                raw["config_schema"] = inferred

    return parse_manifest(raw)


def _safe_extract_zip(archive: zipfile.ZipFile, destination: Path) -> None:
    destination_resolved = destination.resolve()
    for member in archive.infolist():
        relative = Path(member.filename)
        if relative.is_absolute() or ".." in relative.parts:
            raise PluginManifestError("Invalid ZIP archive path.")

        target = (destination / relative).resolve()
        try:
            target.relative_to(destination_resolved)
        except ValueError as exc:  # pragma: no cover - safety check
            raise PluginManifestError("ZIP archive contains unsafe paths.") from exc

    archive.extractall(destination)


def _resolve_zip_plugin_root(extract_root: Path) -> Path:
    root_manifest = extract_root / "manifest.json"
    if root_manifest.exists():
        return extract_root

    manifest_paths = [
        path for path in extract_root.rglob("manifest.json") if path.is_file() and "__MACOSX" not in path.parts
    ]
    if not manifest_paths:
        raise PluginManifestError("ZIP package must include manifest.json.")
    if len(manifest_paths) > 1:
        raise PluginManifestError("ZIP package contains multiple manifests; exactly one plugin is required.")

    return manifest_paths[0].parent


def _merge_missing_config_values(existing: dict, defaults: dict) -> dict:
    merged = dict(existing or {})
    for key, value in (defaults or {}).items():
        current = merged.get(key)
        if key not in merged or current is None or (isinstance(current, str) and not current.strip()):
            merged[key] = value
    return merged


def _has_effective_value(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _collect_registered_hooks(plugin_dir: Path) -> set[str]:
    hooks: set[str] = set()
    for py_file in plugin_dir.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        try:
            source = py_file.read_text(encoding="utf-8")
        except Exception:
            source = py_file.read_text(encoding="utf-8", errors="ignore")

        for hook_name in _REGISTERED_HOOK_RE.findall(source):
            normalized = str(hook_name or "").strip()
            if normalized:
                hooks.add(normalized)

    return hooks


class PluginLifecycleManager:
    @classmethod
    def install_or_update_from_zip(cls, archive_path: str | Path, *, user=None) -> Plugin:
        source_path = Path(archive_path)
        if not source_path.exists():
            raise PluginManifestError(f"Plugin package not found: {source_path}")

        with tempfile.TemporaryDirectory(prefix="plugin_upload_") as temp_dir:
            temp_root = Path(temp_dir)
            try:
                with zipfile.ZipFile(source_path, "r") as archive:
                    _safe_extract_zip(archive, temp_root)
            except zipfile.BadZipFile as exc:
                raise PluginManifestError("Uploaded file is not a valid ZIP archive.") from exc

            extracted_plugin_dir = _resolve_zip_plugin_root(temp_root)
            manifest = load_manifest_from_directory(extracted_plugin_dir)

            plugin_dir = get_plugin_dir(manifest.slug)
            plugin_dir.parent.mkdir(parents=True, exist_ok=True)
            if plugin_dir.exists():
                shutil.rmtree(plugin_dir)
            shutil.copytree(extracted_plugin_dir, plugin_dir)

            return cls.install_or_update_from_directory(plugin_dir, user=user)

    @classmethod
    def install_or_update_from_directory(cls, plugin_dir: Path, *, user=None) -> Plugin:
        manifest = load_manifest_from_directory(plugin_dir)
        checksum = calculate_directory_checksum(plugin_dir)

        plugin, created = Plugin.objects.get_or_create(
            slug=manifest.slug,
            defaults={
                "name": manifest.name,
                "version": manifest.version,
                "status": PluginStatus.DEACTIVATED,
                "package_path": str(plugin_dir),
                "entrypoint": manifest.entrypoint,
                "checksum_sha256": checksum,
                "manifest": {
                    "slug": manifest.slug,
                    "name": manifest.name,
                    "version": manifest.version,
                    "entrypoint": manifest.entrypoint,
                    "scopes": manifest.scopes,
                    "dependencies": [dep.__dict__ for dep in manifest.dependencies],
                    "default_config": manifest.default_config,
                    "env_vars": manifest.env_vars,
                },
                "config_schema": manifest.config_schema,
                "config": manifest.default_config,
                "scopes": manifest.scopes,
                "dependencies": [dep.__dict__ for dep in manifest.dependencies],
                "core_version_min": manifest.core_version_min,
                "core_version_max": manifest.core_version_max,
            },
        )

        if created:
            log_plugin_event(
                plugin=plugin,
                event_type="lifecycle.install",
                message=f"Installed plugin '{plugin.slug}' version {plugin.version}.",
                user=user,
            )
            return plugin

        previous_version = plugin.version
        previous_status = plugin.status
        needs_update = plugin.version != manifest.version or plugin.checksum_sha256 != checksum

        if not needs_update:
            return plugin

        try:
            cls._run_plugin_migrations(
                plugin=plugin,
                plugin_dir=plugin_dir,
                from_version=previous_version,
                to_version=manifest.version,
                direction="up",
            )
            plugin.name = manifest.name
            plugin.version = manifest.version
            plugin.package_path = str(plugin_dir)
            plugin.entrypoint = manifest.entrypoint
            plugin.checksum_sha256 = checksum
            plugin.manifest = {
                "slug": manifest.slug,
                "name": manifest.name,
                "version": manifest.version,
                "entrypoint": manifest.entrypoint,
                "scopes": manifest.scopes,
                "dependencies": [dep.__dict__ for dep in manifest.dependencies],
                "default_config": manifest.default_config,
                "env_vars": manifest.env_vars,
            }
            plugin.config_schema = manifest.config_schema
            plugin.config = _merge_missing_config_values(plugin.config or {}, manifest.default_config)
            plugin.scopes = manifest.scopes
            plugin.dependencies = [dep.__dict__ for dep in manifest.dependencies]
            plugin.core_version_min = manifest.core_version_min
            plugin.core_version_max = manifest.core_version_max
            if previous_status == PluginStatus.ACTIVATED:
                plugin.status = PluginStatus.ACTIVATED
            else:
                plugin.status = PluginStatus.DEACTIVATED
            plugin.last_error = ""
            plugin.save()
            log_plugin_event(
                plugin=plugin,
                event_type="lifecycle.update",
                message=f"Updated plugin '{plugin.slug}' from {previous_version} to {manifest.version}.",
                user=user,
            )
            return plugin
        except Exception as exc:
            plugin.status = PluginStatus.DEACTIVATED
            plugin.last_error = str(exc)
            plugin.save(update_fields=["status", "last_error", "updated_at"])
            log_plugin_event(
                plugin=plugin,
                event_type="lifecycle.update_failed",
                message=f"Update failed for plugin '{plugin.slug}'.",
                payload={"error": str(exc)},
                user=user,
            )
            return plugin

    @classmethod
    def activate(cls, plugin: Plugin, *, user=None) -> Plugin:
        cls._validate_dependencies(plugin)
        cls._validate_activation_contract(plugin)
        plugin.status = PluginStatus.ACTIVATED
        plugin.last_error = ""
        plugin.save(update_fields=["status", "last_error", "updated_at"])
        log_plugin_event(
            plugin=plugin,
            event_type="lifecycle.activate",
            message=f"Activated plugin '{plugin.slug}'.",
            user=user,
        )
        return plugin

    @classmethod
    def _resolve_plugin_dir_for_activation(cls, plugin: Plugin) -> Path:
        package_path = str(plugin.package_path or "").strip()
        if package_path:
            candidate = Path(package_path)
            if candidate.exists() and candidate.is_dir():
                return candidate

        fallback = get_plugin_dir(plugin.slug)
        if fallback.exists() and fallback.is_dir():
            return fallback

        raise PluginManifestError(
            f"Cannot activate plugin '{plugin.slug}' because package files are missing on disk."
        )

    @classmethod
    def _validate_activation_contract(cls, plugin: Plugin) -> None:
        plugin_dir = cls._resolve_plugin_dir_for_activation(plugin)
        manifest = load_manifest_from_directory(plugin_dir)

        if manifest.slug != plugin.slug:
            raise PluginManifestError(
                f"Cannot activate plugin '{plugin.slug}' because manifest slug '{manifest.slug}' does not match."
            )

        entrypoint_path = plugin_dir / manifest.entrypoint
        if not entrypoint_path.exists() or not entrypoint_path.is_file():
            raise PluginManifestError(
                f"Cannot activate plugin '{plugin.slug}' because entrypoint '{manifest.entrypoint}' is missing."
            )

        cls._validate_required_config_values(plugin, manifest)
        cls._validate_required_hooks(plugin, manifest, _collect_registered_hooks(plugin_dir))

    @classmethod
    def _validate_required_config_values(cls, plugin: Plugin, manifest: PluginManifest) -> None:
        schema = manifest.config_schema or {}
        required_raw = schema.get("required") if isinstance(schema, dict) else []
        required_keys = [str(item).strip() for item in (required_raw or []) if str(item).strip()]
        if not required_keys:
            return

        config = plugin.config or {}
        defaults = manifest.default_config or {}
        env_vars = manifest.env_vars or {}

        missing: list[str] = []
        for key in required_keys:
            if _has_effective_value(config.get(key)) or _has_effective_value(defaults.get(key)):
                continue

            env_name = str(env_vars.get(key) or "").strip()
            env_value = str(os.getenv(env_name) or "").strip() if env_name else ""
            if env_value:
                continue

            if env_name:
                missing.append(f"{key} (or set {env_name})")
            else:
                missing.append(key)

        if missing:
            missing_str = ", ".join(missing)
            raise PluginManifestError(
                f"Missing required config fields for activation: {missing_str}."
            )

    @classmethod
    def _validate_required_hooks(
        cls,
        plugin: Plugin,
        manifest: PluginManifest,
        registered_hooks: set[str],
    ) -> None:
        scopes = set(manifest.scopes or []) | {str(scope).strip() for scope in (plugin.scopes or []) if str(scope).strip()}
        if "payments:write" not in scopes:
            return

        hook_groups: list[tuple[str, str]] = [
            ("checkout.redirect_url.resolve", "payment.redirect_url.resolve"),
            ("plugin.flow.start", "payment.provider.start"),
            ("plugin.flow.return", "payment.provider.return"),
        ]

        missing_groups: list[str] = []
        for modern, legacy in hook_groups:
            if modern not in registered_hooks and legacy not in registered_hooks:
                missing_groups.append(f"{modern} (or {legacy})")

        if missing_groups:
            missing = ", ".join(missing_groups)
            raise PluginManifestError(
                f"Cannot activate payment plugin '{plugin.slug}': missing required flow hooks: {missing}."
            )

    @classmethod
    def deactivate(cls, plugin: Plugin, *, user=None) -> Plugin:
        plugin.status = PluginStatus.DEACTIVATED
        plugin.save(update_fields=["status", "updated_at"])
        log_plugin_event(
            plugin=plugin,
            event_type="lifecycle.deactivate",
            message=f"Deactivated plugin '{plugin.slug}'.",
            user=user,
        )
        return plugin

    @classmethod
    def uninstall(
        cls,
        plugin: Plugin,
        *,
        purge_data: bool = False,
        user=None,
    ) -> Plugin:
        plugin.status = PluginStatus.DEACTIVATED
        plugin.save(update_fields=["status", "updated_at"])
        if purge_data:
            plugin.kv_items.all().delete()
            plugin.webhook_events.all().delete()
            plugin.logs.all().delete()
        log_plugin_event(
            plugin=plugin,
            event_type="lifecycle.uninstall",
            message=f"Uninstalled plugin '{plugin.slug}'.",
            payload={"purge_data": purge_data},
            user=user,
        )
        return plugin

    @classmethod
    def remove_plugin_files(cls, plugin: Plugin) -> bool:
        plugin_dir = cls._resolve_removable_plugin_dir(plugin)
        if plugin_dir is None or not plugin_dir.exists():
            return False

        shutil.rmtree(plugin_dir, ignore_errors=True)
        return True

    @classmethod
    def _resolve_removable_plugin_dir(cls, plugin: Plugin) -> Path | None:
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

    @classmethod
    def _run_plugin_migrations(
        cls,
        *,
        plugin: Plugin,
        plugin_dir: Path,
        from_version: str,
        to_version: str,
        direction: str,
    ) -> None:
        migrations_file = plugin_dir / "migrations.py"
        if not migrations_file.exists():
            return

        module_name = f"plugins_{plugin.slug}_migrations"
        spec = importlib.util.spec_from_file_location(module_name, migrations_file)
        if not spec or not spec.loader:
            return
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        func_name = "upgrade" if direction == "up" else "downgrade"
        migration_func = getattr(module, func_name, None)
        if not callable(migration_func):
            return

        with transaction.atomic():
            migration_func(from_version=from_version, to_version=to_version, plugin=plugin)
            PluginMigrationState.objects.update_or_create(
                plugin=plugin,
                version=to_version,
                migration_name=f"{plugin.slug}:{func_name}",
                direction=direction,
                defaults={"applied": True},
            )

    @classmethod
    def _validate_dependencies(cls, plugin: Plugin) -> None:
        deps = plugin.dependencies or []
        for dep in deps:
            dep_slug = str(dep.get("slug") or "").strip()
            if not dep_slug:
                continue
            dep_plugin = Plugin.objects.filter(slug=dep_slug).first()
            if not dep_plugin or dep_plugin.status != PluginStatus.ACTIVATED:
                raise PluginDependencyError(f"Plugin '{plugin.slug}' depends on '{dep_slug}', which is not activated.")
            min_version = str(dep.get("min_version") or "").strip()
            if min_version and _is_version_lower(dep_plugin.version, min_version):
                raise PluginDependencyError(
                    f"Plugin '{plugin.slug}' requires '{dep_slug}>={min_version}', found {dep_plugin.version}."
                )
