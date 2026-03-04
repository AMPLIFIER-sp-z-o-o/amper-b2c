from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path

from django.db import OperationalError, ProgrammingError

from apps.plugins.engine.api import PluginAPI
from apps.plugins.engine.lifecycle import PluginLifecycleManager, get_plugins_root
from apps.plugins.engine.log_utils import log_plugin_event
from apps.plugins.engine.registry import registry
from apps.plugins.models import Plugin, PluginLogLevel, PluginStatus

logger = logging.getLogger(__name__)

_BOOTSTRAP_SKIP_COMMANDS = {"makemigrations", "migrate", "collectstatic", "shell"}


def sync_and_load_plugins() -> bool:
    if any(cmd in sys.argv for cmd in _BOOTSTRAP_SKIP_COMMANDS):
        return False

    try:
        registry.clear()
        _sync_plugins_from_disk()
        _mark_zombie_plugins()
        _load_active_plugins()
        return True
    except (OperationalError, ProgrammingError):
        # DB not ready yet (during first migrate/startup)
        return False
    except Exception:
        logger.exception("Plugin bootstrap failed")
        return False


def _discover_plugin_directories() -> list[Path]:
    root = get_plugins_root()
    if not root.exists():
        return []
    return [path for path in root.iterdir() if path.is_dir() and (path / "manifest.json").exists()]


def _sync_plugins_from_disk() -> None:
    for plugin_dir in _discover_plugin_directories():
        try:
            PluginLifecycleManager.install_or_update_from_directory(plugin_dir)
        except (OperationalError, ProgrammingError):
            return
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Failed to sync plugin directory %s", plugin_dir)
            slug = plugin_dir.name
            plugin = Plugin.objects.filter(slug=slug).first()
            if plugin:
                plugin.status = PluginStatus.DEACTIVATED
                plugin.last_error = str(exc)
                plugin.save(update_fields=["status", "last_error", "updated_at"])
                log_plugin_event(
                    plugin=plugin,
                    event_type="bootstrap.sync_failed",
                    level=PluginLogLevel.ERROR,
                    message=f"Failed to sync plugin directory '{plugin_dir}'.",
                    payload={"error": str(exc)},
                )


def _mark_zombie_plugins() -> None:
    root = get_plugins_root()
    for plugin in Plugin.objects.filter(status=PluginStatus.ACTIVATED):
        plugin_dir = root / plugin.slug
        if plugin_dir.exists() and (plugin_dir / "manifest.json").exists():
            continue
        plugin.status = PluginStatus.DEACTIVATED
        plugin.last_error = "Plugin code is missing on disk (zombie plugin)."
        plugin.save(update_fields=["status", "last_error", "updated_at"])
        log_plugin_event(
            plugin=plugin,
            event_type="bootstrap.zombie_plugin",
            level=PluginLogLevel.ERROR,
            message=f"Plugin '{plugin.slug}' was active but its code is missing on disk.",
        )


def _load_active_plugins() -> None:
    for plugin in Plugin.objects.filter(status=PluginStatus.ACTIVATED):
        _load_single_plugin(plugin)


def _load_single_plugin(plugin: Plugin) -> None:
    plugin_dir = Path(plugin.package_path or "")
    if not plugin_dir.exists():
        plugin.status = PluginStatus.DEACTIVATED
        plugin.last_error = "Plugin package path does not exist."
        plugin.save(update_fields=["status", "last_error", "updated_at"])
        return

    entrypoint = plugin_dir / plugin.entrypoint
    if not entrypoint.exists():
        plugin.status = PluginStatus.DEACTIVATED
        plugin.last_error = f"Entrypoint '{plugin.entrypoint}' not found."
        plugin.save(update_fields=["status", "last_error", "updated_at"])
        return

    module_name = f"plugin_runtime_{plugin.slug}"
    spec = importlib.util.spec_from_file_location(module_name, entrypoint)
    if not spec or not spec.loader:
        plugin.status = PluginStatus.DEACTIVATED
        plugin.last_error = "Unable to load plugin entrypoint."
        plugin.save(update_fields=["status", "last_error", "updated_at"])
        return

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        register_func = getattr(module, "register", None)
        if not callable(register_func):
            raise RuntimeError("Plugin entrypoint must expose callable register(api).")

        api = PluginAPI(plugin)
        register_func(api)
        log_plugin_event(
            plugin=plugin,
            event_type="bootstrap.loaded",
            message=f"Loaded plugin '{plugin.slug}' callbacks.",
        )
    except Exception as exc:  # pragma: no cover - defensive
        plugin.status = PluginStatus.DEACTIVATED
        plugin.last_error = str(exc)
        plugin.save(update_fields=["status", "last_error", "updated_at"])
        log_plugin_event(
            plugin=plugin,
            event_type="bootstrap.load_failed",
            level=PluginLogLevel.ERROR,
            message=f"Failed to load plugin '{plugin.slug}'.",
            payload={"error": str(exc)},
        )
        logger.exception("Failed to load plugin %s", plugin.slug)
