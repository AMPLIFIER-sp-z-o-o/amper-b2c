from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any

from apps.plugins.engine.lifecycle import get_plugin_dir
from apps.plugins.engine.log_utils import log_plugin_event
from apps.plugins.models import Plugin, PluginLogLevel

logger = logging.getLogger(__name__)


def run_plugin_lifecycle_callback(plugin: Plugin, callback_name: str, **kwargs: Any) -> bool:
    """
    Execute an optional lifecycle callback from plugin entrypoint.

    This is intentionally generic (plugin-level events only). Domain-specific
    side effects stay inside the plugin package implementation.
    """
    callback_name = str(callback_name or "").strip()
    if not callback_name:
        return False

    plugin_dir = _resolve_plugin_dir(plugin)
    if plugin_dir is None:
        return False

    entrypoint_name = str(plugin.entrypoint or "entrypoint.py").strip() or "entrypoint.py"
    entrypoint = plugin_dir / entrypoint_name
    if not entrypoint.exists():
        return False

    module_name = f"plugin_lifecycle_{plugin.slug}_{callback_name}"
    spec = importlib.util.spec_from_file_location(module_name, entrypoint)
    if not spec or not spec.loader:
        return False

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        callback = getattr(module, callback_name, None)
        if not callable(callback):
            return False

        callback(plugin=plugin, **kwargs)
        if callback_name != "on_plugin_before_delete":
            log_plugin_event(
                plugin=plugin,
                event_type="lifecycle.callback.executed",
                message=f"Executed lifecycle callback '{callback_name}'.",
                payload={"callback": callback_name},
            )
        return True
    except Exception as exc:  # pragma: no cover - defensive
        log_plugin_event(
            plugin=plugin,
            event_type="lifecycle.callback.failed",
            level=PluginLogLevel.ERROR,
            message=f"Lifecycle callback '{callback_name}' failed.",
            payload={"callback": callback_name, "error": str(exc)},
        )
        logger.exception("Plugin lifecycle callback failed: %s (%s)", plugin.slug, callback_name)
        return False


def _resolve_plugin_dir(plugin: Plugin) -> Path | None:
    package_path = str(plugin.package_path or "").strip()
    if package_path:
        path = Path(package_path)
        if path.exists():
            return path

    fallback = get_plugin_dir(plugin.slug)
    if fallback.exists():
        return fallback

    return None
