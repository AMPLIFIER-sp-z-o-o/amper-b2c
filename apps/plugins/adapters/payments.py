from __future__ import annotations

from typing import TYPE_CHECKING

from apps.plugins.engine.exceptions import PluginScopeError
from apps.plugins.models import Plugin, PluginKVData

if TYPE_CHECKING:
    from apps.cart.models import PaymentMethod

PAYMENT_METHOD_BINDING_NAMESPACE = "payments"
PAYMENT_METHOD_BINDING_KEY = "payment_method_binding"


def _require_scope(plugin: Plugin, scope: str) -> None:
    if scope not in (plugin.scopes or []):
        raise PluginScopeError(f"Plugin '{plugin.slug}' requires scope '{scope}'.")


def ensure_plugin_payment_method(
    plugin: Plugin,
    *,
    name: str,
    default_payment_time: int | None = 1,
    is_active: bool = True,
) -> PaymentMethod:
    from apps.cart.models import PaymentMethod as _PaymentMethod

    _require_scope(plugin, "payments:write")

    target_name = str(name or "").strip() or str(plugin.name or "").strip() or plugin.slug
    manifest_name = str((plugin.manifest or {}).get("name") or "").strip()

    method: _PaymentMethod | None = None
    binding = PluginKVData.objects.filter(
        plugin=plugin,
        namespace=PAYMENT_METHOD_BINDING_NAMESPACE,
        key=PAYMENT_METHOD_BINDING_KEY,
    ).first()
    if binding and isinstance(binding.value, dict):
        bound_id = binding.value.get("id")
        try:
            method = _PaymentMethod.objects.filter(pk=int(bound_id)).first()
        except Exception:
            method = None

    if method is None and target_name:
        method = _PaymentMethod.objects.filter(name=target_name).order_by("id").first()

    # Backward compatibility: migrate legacy seeded rows (manifest name) to target name.
    if method is None and manifest_name and manifest_name != target_name:
        method = _PaymentMethod.objects.filter(name=manifest_name).order_by("id").first()

    if method is None:
        method = _PaymentMethod.objects.create(
            name=target_name,
            default_payment_time=default_payment_time,
            is_active=is_active,
        )

    updates = []
    if target_name and method.name != target_name:
        method.name = target_name
        updates.append("name")
    if method.default_payment_time != default_payment_time:
        method.default_payment_time = default_payment_time
        updates.append("default_payment_time")
    if method.is_active != is_active:
        method.is_active = is_active
        updates.append("is_active")
    if updates:
        method.save(update_fields=updates)

    PluginKVData.objects.update_or_create(
        plugin=plugin,
        namespace=PAYMENT_METHOD_BINDING_NAMESPACE,
        key=PAYMENT_METHOD_BINDING_KEY,
        defaults={"value": {"id": method.id}},
    )
    return method
