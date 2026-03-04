from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from django.db import transaction

from apps.plugins.engine.exceptions import PluginAbortAction, PluginScopeError
from apps.plugins.engine.log_utils import log_plugin_event
from apps.plugins.engine.registry import registry
from apps.plugins.models import Plugin, PluginKVData, PluginLogLevel


class PluginDataAPI:
    def __init__(self, plugin: Plugin) -> None:
        self.plugin = plugin

    def get(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        item = PluginKVData.objects.filter(plugin=self.plugin, namespace=namespace, key=key).first()
        if not item:
            return default
        return item.value

    def set(self, key: str, value: Any, namespace: str = "default") -> None:
        self._require_scope("data:write")
        with transaction.atomic():
            PluginKVData.objects.update_or_create(
                plugin=self.plugin,
                namespace=namespace,
                key=key,
                defaults={"value": value},
            )

    def delete(self, key: str, namespace: str = "default") -> None:
        self._require_scope("data:write")
        PluginKVData.objects.filter(plugin=self.plugin, namespace=namespace, key=key).delete()

    def list_namespace(self, namespace: str = "default") -> dict[str, Any]:
        items = PluginKVData.objects.filter(plugin=self.plugin, namespace=namespace).values_list("key", "value")
        return {key: value for key, value in items}

    def _require_scope(self, scope: str) -> None:
        if scope not in (self.plugin.scopes or []):
            raise PluginScopeError(f"Plugin '{self.plugin.slug}' requires scope '{scope}'.")


class PluginHTTPAPI:
    def __init__(self, plugin: Plugin) -> None:
        self.plugin = plugin

    def get(self, url: str, *, headers: dict[str, str] | None = None, timeout_seconds: float = 4.0) -> dict[str, Any]:
        return self.request("GET", url, headers=headers, timeout_seconds=timeout_seconds)

    def post(
        self,
        url: str,
        *,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout_seconds: float = 4.0,
    ) -> dict[str, Any]:
        return self.request("POST", url, body=body, headers=headers, timeout_seconds=timeout_seconds)

    def request(
        self,
        method: str,
        url: str,
        *,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout_seconds: float = 4.0,
    ) -> dict[str, Any]:
        self._require_scope("http:outbound")
        payload = b""
        if body is not None:
            payload = json.dumps(body).encode("utf-8")

        req_headers = {"Content-Type": "application/json"}
        req_headers.update(headers or {})
        request_obj = urllib.request.Request(url=url, method=method.upper(), data=payload or None, headers=req_headers)

        started = time.monotonic()
        try:
            with urllib.request.urlopen(request_obj, timeout=timeout_seconds) as response:  # noqa: S310
                raw = response.read().decode("utf-8")
                duration_ms = int((time.monotonic() - started) * 1000)
                log_plugin_event(
                    plugin=self.plugin,
                    event_type="http.request",
                    message=f"{method.upper()} {url}",
                    payload={"status_code": response.status, "duration_ms": duration_ms},
                )
                try:
                    parsed = json.loads(raw) if raw else {}
                except Exception:
                    parsed = {"raw": raw}
                return {"ok": True, "status_code": response.status, "data": parsed}
        except urllib.error.HTTPError as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            log_plugin_event(
                plugin=self.plugin,
                event_type="http.request",
                level=PluginLogLevel.WARNING,
                message=f"{method.upper()} {url}",
                payload={"status_code": exc.code, "duration_ms": duration_ms},
            )
            return {"ok": False, "status_code": exc.code, "data": {"error": str(exc)}}
        except Exception as exc:  # pragma: no cover - defensive
            duration_ms = int((time.monotonic() - started) * 1000)
            log_plugin_event(
                plugin=self.plugin,
                event_type="http.request",
                level=PluginLogLevel.ERROR,
                message=f"{method.upper()} {url}",
                payload={"duration_ms": duration_ms, "error": str(exc)},
            )
            return {"ok": False, "status_code": 0, "data": {"error": str(exc)}}

    def _require_scope(self, scope: str) -> None:
        if scope not in (self.plugin.scopes or []):
            raise PluginScopeError(f"Plugin '{self.plugin.slug}' requires scope '{scope}'.")


class PluginAPI:
    AbortAction = PluginAbortAction

    def __init__(self, plugin: Plugin) -> None:
        self.plugin = plugin
        self.data = PluginDataAPI(plugin)
        self.http = PluginHTTPAPI(plugin)

    def register_action(self, hook_name: str, callback, *, priority: int = 50, timeout_ms: int | None = None) -> None:
        registry.register_action(
            hook_name,
            callback,
            plugin_slug=self.plugin.slug,
            priority=priority,
            timeout_ms=timeout_ms,
        )

    def register_async_action(self, hook_name: str, callback, *, priority: int = 50) -> None:
        registry.register_async_action(hook_name, callback, plugin_slug=self.plugin.slug, priority=priority)

    def register_filter(self, hook_name: str, callback, *, priority: int = 50, timeout_ms: int | None = None) -> None:
        registry.register_filter(
            hook_name,
            callback,
            plugin_slug=self.plugin.slug,
            priority=priority,
            timeout_ms=timeout_ms,
        )
