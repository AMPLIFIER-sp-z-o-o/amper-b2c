from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.plugins.models import Plugin


logger = logging.getLogger(__name__)


def log_plugin_event(
    *,
    plugin: Plugin | None,
    event_type: str,
    message: str,
    level: str = "info",
    payload: dict[str, Any] | None = None,
    correlation_id: str = "",
    user=None,
) -> None:
    """Persist a structured log entry for plugin diagnostics."""
    from apps.plugins.models import PluginLog

    try:
        PluginLog.objects.create(
            plugin=plugin,
            event_type=event_type,
            message=message,
            level=level,
            payload=payload or {},
            correlation_id=correlation_id or "",
            user=user,
        )
    except Exception:
        logger.debug(
            "Could not persist plugin log (event_type=%s, plugin=%s): %s",
            event_type,
            getattr(plugin, "slug", None),
            message,
        )
