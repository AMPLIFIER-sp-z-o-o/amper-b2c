from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from typing import Any

from django.db import OperationalError, ProgrammingError

from apps.plugins.engine.exceptions import PluginAbortAction
from apps.plugins.engine.log_utils import log_plugin_event
from apps.plugins.engine.state import get_remaining_budget_seconds
from django.conf import settings as django_settings

from apps.plugins.models import (
    Plugin,
    PluginExecutionMode,
    PluginLogLevel,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class HookCallback:
    callback: Callable
    plugin_slug: str
    priority: int
    timeout_ms: int | None = None


class HookRegistry:
    """Central registry for plugin actions/filters."""

    def __init__(self) -> None:
        self._actions: dict[str, list[HookCallback]] = {}
        self._async_actions: dict[str, list[HookCallback]] = {}
        self._filters: dict[str, list[HookCallback]] = {}
        self._executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="plugin-hook")
        # Cache avoids repeated DB queries for the same plugin slug within a dispatch loop.
        # Invalidated on clear() which is called by sync_and_load_plugins on every reload.
        self._plugin_cache: dict[str, Plugin | None] = {}

    def clear(self) -> None:
        self._actions.clear()
        self._async_actions.clear()
        self._filters.clear()
        self._plugin_cache.clear()

    def has_action(self, hook_name: str) -> bool:
        return bool(self._actions.get(hook_name, []))

    def has_async_action(self, hook_name: str) -> bool:
        return bool(self._async_actions.get(hook_name, []))

    def has_filter(self, hook_name: str) -> bool:
        return bool(self._filters.get(hook_name, []))

    def register_action(
        self,
        hook_name: str,
        callback: Callable,
        *,
        plugin_slug: str,
        priority: int = 50,
        timeout_ms: int | None = None,
    ) -> None:
        self._actions.setdefault(hook_name, []).append(
            HookCallback(callback=callback, plugin_slug=plugin_slug, priority=priority, timeout_ms=timeout_ms)
        )
        self._actions[hook_name].sort(key=lambda cb: cb.priority)

    def register_async_action(
        self,
        hook_name: str,
        callback: Callable,
        *,
        plugin_slug: str,
        priority: int = 50,
    ) -> None:
        self._async_actions.setdefault(hook_name, []).append(
            HookCallback(callback=callback, plugin_slug=plugin_slug, priority=priority)
        )
        self._async_actions[hook_name].sort(key=lambda cb: cb.priority)

    def register_filter(
        self,
        hook_name: str,
        callback: Callable,
        *,
        plugin_slug: str,
        priority: int = 50,
        timeout_ms: int | None = None,
    ) -> None:
        self._filters.setdefault(hook_name, []).append(
            HookCallback(callback=callback, plugin_slug=plugin_slug, priority=priority, timeout_ms=timeout_ms)
        )
        self._filters[hook_name].sort(key=lambda cb: cb.priority)

    def dispatch_action(
        self, hook_name: str, *, request=None, stop_on_abort: bool = False, **kwargs: Any
    ) -> dict[str, Any]:
        callbacks = self._actions.get(hook_name, [])
        aborted = False
        abort_reason = ""
        for callback in callbacks:
            plugin = self._get_plugin(callback.plugin_slug)
            if not plugin or not self._plugin_is_executable(plugin, request=request):
                continue

            timed_out, result, error = self._run_sync_callback(
                callback,
                plugin=plugin,
                request=request,
                kwargs={"request": request, **kwargs},
            )
            if timed_out:
                continue
            if error:
                if isinstance(error, PluginAbortAction):
                    aborted = True
                    abort_reason = str(error)
                    if stop_on_abort:
                        break
                continue
            log_plugin_event(
                plugin=plugin,
                event_type="action.executed",
                message=f"Executed action hook '{hook_name}'.",
                payload={"hook": hook_name, "result": str(result)[:200]},
            )
        return {"aborted": aborted, "reason": abort_reason}

    def apply_filters(self, hook_name: str, value: Any, *, request=None, **kwargs: Any) -> Any:
        filtered_value = value
        callbacks = self._filters.get(hook_name, [])
        for callback in callbacks:
            plugin = self._get_plugin(callback.plugin_slug)
            if not plugin or not self._plugin_is_executable(plugin, request=request):
                continue

            timed_out, result, error = self._run_sync_callback(
                callback,
                plugin=plugin,
                request=request,
                kwargs={"value": filtered_value, "request": request, **kwargs},
            )
            if timed_out or error:
                continue
            filtered_value = result
            log_plugin_event(
                plugin=plugin,
                event_type="filter.applied",
                message=f"Applied filter hook '{hook_name}'.",
                payload={"hook": hook_name},
            )
        return filtered_value

    def apply_filter_for_plugin(
        self,
        hook_name: str,
        value: Any,
        *,
        target_plugin_slug: str,
        request=None,
        **kwargs: Any,
    ) -> Any:
        """Apply a filter hook for a single plugin slug only.

        This path is intended for provider-specific, latency-sensitive flows
        (e.g. payment start/return), where running all plugin callbacks through
        the generic timeout budget can cause false fallbacks.
        """
        filtered_value = value
        callbacks = self._filters.get(hook_name, [])
        for callback in callbacks:
            if callback.plugin_slug != target_plugin_slug:
                continue

            plugin = self._get_plugin(callback.plugin_slug)
            if not plugin or not self._plugin_is_executable(plugin, request=request):
                continue

            try:
                filtered_value = callback.callback(
                    value=filtered_value,
                    request=request,
                    plugin_slug=target_plugin_slug,
                    **kwargs,
                )
                log_plugin_event(
                    plugin=plugin,
                    event_type="filter.applied",
                    message=f"Applied filter hook '{hook_name}'.",
                    payload={"hook": hook_name, "target_plugin_slug": target_plugin_slug},
                )
            except Exception as exc:  # pragma: no cover - defensive
                log_plugin_event(
                    plugin=plugin,
                    event_type="hook.error",
                    message="Synchronous plugin hook failed.",
                    level=PluginLogLevel.ERROR,
                    payload={"error": str(exc)},
                )
                logger.exception("Plugin hook failed for %s", plugin.slug)

            # Provider flow route identifies one plugin, so stop after match.
            break

        return filtered_value

    def dispatch_async_action(self, hook_name: str, payload: dict[str, Any], correlation_id: str = "") -> None:
        from apps.plugins.tasks import run_async_plugin_action

        run_async_plugin_action.delay(hook_name=hook_name, payload=payload, correlation_id=correlation_id)

    def execute_async_action_now(self, hook_name: str, payload: dict[str, Any], correlation_id: str = "") -> dict[str, Any]:
        callbacks = self._async_actions.get(hook_name, [])
        summary: dict[str, Any] = {
            "hook_name": hook_name,
            "total_callbacks": len(callbacks),
            "executed": 0,
            "failed": 0,
            "skipped": 0,
            "errors": [],
        }
        for callback in callbacks:
            plugin = self._get_plugin(callback.plugin_slug)
            if not plugin or not self._plugin_is_executable(plugin, request=None):
                summary["skipped"] += 1
                continue
            try:
                callback.callback(**payload)
                summary["executed"] += 1
                log_plugin_event(
                    plugin=plugin,
                    event_type="async_action.executed",
                    message=f"Executed async hook '{hook_name}'.",
                    payload={"hook": hook_name},
                    correlation_id=correlation_id,
                )
            except Exception as exc:  # pragma: no cover - defensive
                summary["failed"] += 1
                summary["errors"].append(f"{type(exc).__name__}: {exc}")
                log_plugin_event(
                    plugin=plugin,
                    event_type="async_action.error",
                    message=f"Async hook '{hook_name}' failed.",
                    level=PluginLogLevel.ERROR,
                    payload={"hook": hook_name, "error": str(exc)},
                    correlation_id=correlation_id,
                )
                logger.exception("Async plugin hook failed: %s", hook_name)
        return summary

    def _run_sync_callback(
        self,
        callback: HookCallback,
        *,
        plugin: Plugin,
        request,
        kwargs: dict[str, Any],
    ) -> tuple[bool, Any, Exception | None]:
        timeout_s = self._compute_timeout_seconds(callback)
        if timeout_s <= 0:
            log_plugin_event(
                plugin=plugin,
                event_type="hook.skipped",
                message="Global plugin request budget exceeded before callback execution.",
                level=PluginLogLevel.WARNING,
                payload={"plugin": plugin.slug},
            )
            return True, None, None

        # We execute in a worker thread and enforce timeout via future.result(timeout).
        # Python cannot forcibly kill arbitrary running threads, so a timed-out callback
        # is detached and ignored while we continue with the request.
        started = time.monotonic()
        future = self._executor.submit(callback.callback, **kwargs)
        try:
            result = future.result(timeout=timeout_s)
            elapsed_ms = int((time.monotonic() - started) * 1000)
            if elapsed_ms > int(timeout_s * 1000):
                log_plugin_event(
                    plugin=plugin,
                    event_type="hook.timeout.soft",
                    message="Hook exceeded soft timeout budget.",
                    level=PluginLogLevel.WARNING,
                    payload={"elapsed_ms": elapsed_ms, "timeout_ms": int(timeout_s * 1000)},
                )
            return False, result, None
        except TimeoutError:
            log_plugin_event(
                plugin=plugin,
                event_type="hook.timeout",
                message="Synchronous plugin hook timed out.",
                level=PluginLogLevel.ERROR,
                payload={"timeout_ms": int(timeout_s * 1000)},
            )
            return True, None, None
        except Exception as exc:  # pragma: no cover - defensive
            level = PluginLogLevel.WARNING if isinstance(exc, PluginAbortAction) else PluginLogLevel.ERROR
            log_plugin_event(
                plugin=plugin,
                event_type="hook.error",
                message="Synchronous plugin hook failed.",
                level=level,
                payload={"error": str(exc)},
            )
            logger.exception("Plugin hook failed for %s", plugin.slug)
            return False, None, exc

    def _compute_timeout_seconds(self, callback: HookCallback) -> float:
        default_ms = int(getattr(django_settings, "PLUGIN_DEFAULT_HOOK_TIMEOUT_MS", 350))
        per_hook_ms = callback.timeout_ms if callback.timeout_ms is not None else default_ms
        timeout_s = max(per_hook_ms, 1) / 1000.0

        remaining = get_remaining_budget_seconds()
        if remaining is None:
            return timeout_s
        return min(timeout_s, remaining)

    def _plugin_is_executable(self, plugin: Plugin, *, request) -> bool:
        if plugin.execution_mode == PluginExecutionMode.LIVE:
            return True

        if plugin.execution_mode == PluginExecutionMode.SUPERADMIN_ONLY:
            user = getattr(request, "user", None)
            return bool(user and user.is_authenticated and user.is_superuser)

        if plugin.execution_mode == PluginExecutionMode.IP_ALLOWLIST:
            if not request:
                return False
            allowed_ips = {item.strip() for item in (plugin.safe_mode_ip_allowlist or "").split(",") if item.strip()}
            client_ip = (
                request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0] or request.META.get("REMOTE_ADDR") or ""
            ).strip()
            return bool(client_ip and client_ip in allowed_ips)

        return False

    def _get_plugin(self, slug: str) -> Plugin | None:
        if slug in self._plugin_cache:
            return self._plugin_cache[slug]
        try:
            plugin = Plugin.objects.filter(slug=slug).first()
        except (OperationalError, ProgrammingError):
            plugin = None
        self._plugin_cache[slug] = plugin
        return plugin

    def invalidate_plugin_cache(self, slug: str) -> None:
        """Remove a single plugin from the cache, e.g. after status change."""
        self._plugin_cache.pop(slug, None)


registry = HookRegistry()
