from __future__ import annotations

import base64
import hashlib
import json
import os
from decimal import Decimal
from typing import Any
from urllib import error, request

from django.db import transaction
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.cart.models import PaymentMethod
from apps.orders.models import Order, OrderStatus
from apps.plugins.adapters.payments import ensure_plugin_payment_method
from apps.plugins.models import Plugin
from apps.plugins.models import PluginKVData
from apps.plugins.models import PluginStatus

PLUGIN_SLUG = "przelewy24"
DEFAULT_CURRENCY = "PLN"
LEGACY_PAYMENT_METHOD_NAME = "Przelewy24"
PAYMENT_METHOD_BINDING_NAMESPACE = "payments"
PAYMENT_METHOD_BINDING_KEY = "payment_method_binding"


def _non_empty(value: Any) -> str:
    return str(value or "").strip()


def _as_int_or_str(value: Any) -> int | str:
    text = _non_empty(value)
    try:
        return int(text)
    except Exception:
        return text


def _json_compact(data: dict) -> str:
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


def _sign(payload: dict) -> str:
    return hashlib.sha384(_json_compact(payload).encode("utf-8")).hexdigest()


def _get_env(name: str, default: str = "") -> str:
    return _non_empty(os.getenv(name, default))


def _is_truthy(value: Any) -> bool:
    return _non_empty(value).lower() in {"1", "true", "yes", "on"}


def resolve_config(plugin_config: dict | None) -> dict:
    config = {
        "environment": "sandbox",
        "merchant_id": "",
        "pos_id": "",
        "crc_key": "",
        "api_key": "",
        "auto_capture": True,
    }

    plugin_config = plugin_config or {}
    for key in ["environment", "merchant_id", "pos_id", "crc_key", "api_key"]:
        value = plugin_config.get(key)
        if _non_empty(value):
            config[key] = _non_empty(value)

    if "auto_capture" in plugin_config:
        config["auto_capture"] = bool(plugin_config.get("auto_capture"))

    # Environment variables override plugin config when provided.
    merchant_id = _get_env("PAYMENTS_P24_MERCHANT_ID")
    pos_id = _get_env("PAYMENTS_P24_POS_ID")
    crc_key = _get_env("PAYMENTS_P24_CRC")
    api_key = _get_env("PAYMENTS_P24_API_KEY")
    sandbox_raw = os.getenv("PAYMENTS_P24_SANDBOX")

    if merchant_id:
        config["merchant_id"] = merchant_id
    if pos_id:
        config["pos_id"] = pos_id
    if crc_key:
        config["crc_key"] = crc_key
    if api_key:
        config["api_key"] = api_key
    if sandbox_raw is not None:
        config["environment"] = "sandbox" if _is_truthy(sandbox_raw) else "production"

    if not _non_empty(config.get("pos_id")):
        config["pos_id"] = _non_empty(config.get("merchant_id"))

    return config


def missing_required(config: dict) -> list[str]:
    required = ["environment", "merchant_id", "crc_key", "api_key"]
    return [key for key in required if not _non_empty(config.get(key))]


def api_base_url(environment: str) -> str:
    env = _non_empty(environment).lower()
    if env in {"prod", "production", "live"}:
        return "https://secure.przelewy24.pl/api/v1"
    return "https://sandbox.przelewy24.pl/api/v1"


def gateway_base_url(environment: str) -> str:
    env = _non_empty(environment).lower()
    if env in {"prod", "production", "live"}:
        return "https://secure.przelewy24.pl"
    return "https://sandbox.przelewy24.pl"


def _auth_header(pos_id: str, api_key: str) -> str:
    raw = f"{_non_empty(pos_id)}:{_non_empty(api_key)}".encode()
    return "Basic " + base64.b64encode(raw).decode("ascii")


def _http_post_json(
    base_url: str, path: str, payload: dict, *, auth_header: str, timeout: int = 20
) -> tuple[int, dict]:
    return _http_json(base_url, path, payload, auth_header=auth_header, method="POST", timeout=timeout)


def _http_json(
    base_url: str,
    path: str,
    payload: dict | None = None,
    *,
    auth_header: str,
    method: str,
    timeout: int = 20,
) -> tuple[int, dict]:
    body = _json_compact(payload or {}).encode("utf-8") if payload is not None else None
    req = request.Request(
        url=f"{base_url.rstrip('/')}/{path.lstrip('/')}",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": auth_header,
        },
        method=method,
    )

    try:
        with request.urlopen(req, timeout=timeout) as response:
            status_code = int(getattr(response, "status", 200) or 200)
            text = response.read().decode("utf-8")
    except error.HTTPError as exc:
        status_code = int(getattr(exc, "code", 500) or 500)
        text = exc.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return 0, {"error": str(exc)}

    try:
        data = json.loads(text or "{}")
    except Exception:
        data = {"raw": text}
    return status_code, data


def _http_get_json(base_url: str, path: str, *, auth_header: str, timeout: int = 20) -> tuple[int, dict]:
    return _http_json(base_url, path, None, auth_header=auth_header, method="GET", timeout=timeout)


def _extract_nested(data: dict, keys: list[str]) -> Any:
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _extract_token(data: dict) -> str:
    candidates = [
        _extract_nested(data, ["data", "token"]),
        data.get("token") if isinstance(data, dict) else None,
        _extract_nested(data, ["data", "sessionId"]),
    ]
    for candidate in candidates:
        value = _non_empty(candidate)
        if value:
            return value
    return ""


def _extract_order_id(data: dict) -> str:
    candidates = [
        _extract_nested(data, ["data", "orderId"]),
        data.get("orderId") if isinstance(data, dict) else None,
    ]
    for candidate in candidates:
        value = _non_empty(candidate)
        if value:
            return value
    return ""


def _is_success(status_code: int, data: dict) -> bool:
    if status_code < 200 or status_code >= 300:
        return False
    if not isinstance(data, dict):
        return True

    response_code = data.get("responseCode")
    if response_code not in (None, 0, "0", ""):
        return False

    if _non_empty(data.get("error")):
        return False

    return not (isinstance(data.get("data"), dict) and _non_empty(data["data"].get("error")))


def test_access(config: dict) -> tuple[bool, str]:
    missing = missing_required(config)
    if missing:
        return False, f"Missing required configuration: {', '.join(missing)}"

    status_code, data = _http_get_json(
        api_base_url(config.get("environment") or "sandbox"),
        "testAccess",
        auth_header=_auth_header(config.get("pos_id") or config.get("merchant_id"), config.get("api_key")),
    )
    if _is_success(status_code, data):
        return True, "Connection to Przelewy24 succeeded."

    message = _non_empty(data.get("error") if isinstance(data, dict) else "")
    if not message:
        message = f"Przelewy24 testAccess failed (HTTP {status_code})."
    return False, message


def register_transaction(
    *,
    config: dict,
    session_id: str,
    amount_grosz: int,
    currency: str,
    description: str,
    email: str,
    country: str,
    url_return: str,
    url_status: str,
) -> dict:
    missing = missing_required(config)
    if missing:
        return {"success": False, "message": f"Missing required configuration: {', '.join(missing)}"}

    merchant_id = config.get("merchant_id")
    pos_id = config.get("pos_id") or merchant_id
    crc_key = config.get("crc_key")

    sign_payload = {
        "sessionId": _non_empty(session_id),
        "merchantId": _as_int_or_str(merchant_id),
        "amount": int(amount_grosz),
        "currency": _non_empty(currency) or DEFAULT_CURRENCY,
        "crc": _non_empty(crc_key),
    }

    payload = {
        "merchantId": _as_int_or_str(merchant_id),
        "posId": _as_int_or_str(pos_id),
        "sessionId": _non_empty(session_id),
        "amount": int(amount_grosz),
        "currency": _non_empty(currency) or DEFAULT_CURRENCY,
        "description": _non_empty(description),
        "email": _non_empty(email),
        "country": (_non_empty(country) or "PL").upper(),
        "language": "pl",
        "urlReturn": _non_empty(url_return),
        "urlStatus": _non_empty(url_status),
        "sign": _sign(sign_payload),
    }

    status_code, data = _http_post_json(
        api_base_url(config.get("environment") or "sandbox"),
        "transaction/register",
        payload,
        auth_header=_auth_header(pos_id, config.get("api_key")),
    )

    if not _is_success(status_code, data):
        message = _non_empty(data.get("error") if isinstance(data, dict) else "")
        if not message:
            message = f"Przelewy24 register failed (HTTP {status_code})."
        return {"success": False, "message": message, "raw": data}

    token = _extract_token(data)
    if not token:
        return {
            "success": False,
            "message": "Przelewy24 did not return a payment token.",
            "raw": data,
        }

    redirect_url = f"{gateway_base_url(config.get('environment') or 'sandbox').rstrip('/')}/trnRequest/{token}"
    return {"success": True, "redirect_url": redirect_url, "token": token, "raw": data}


def verify_transaction(
    *,
    config: dict,
    session_id: str,
    order_id: str,
    amount_grosz: int,
    currency: str,
) -> tuple[bool, str]:
    missing = missing_required(config)
    if missing:
        return False, f"Missing required configuration: {', '.join(missing)}"

    merchant_id = config.get("merchant_id")
    pos_id = config.get("pos_id") or merchant_id
    crc_key = config.get("crc_key")

    sign_payload = {
        "sessionId": _non_empty(session_id),
        "orderId": _as_int_or_str(order_id),
        "amount": int(amount_grosz),
        "currency": _non_empty(currency) or DEFAULT_CURRENCY,
        "crc": _non_empty(crc_key),
    }

    payload = {
        "merchantId": _as_int_or_str(merchant_id),
        "posId": _as_int_or_str(pos_id),
        "sessionId": _non_empty(session_id),
        "amount": int(amount_grosz),
        "currency": _non_empty(currency) or DEFAULT_CURRENCY,
        "orderId": _as_int_or_str(order_id),
        "sign": _sign(sign_payload),
    }

    status_code, data = _http_json(
        api_base_url(config.get("environment") or "sandbox"),
        "transaction/verify",
        payload,
        auth_header=_auth_header(pos_id, config.get("api_key")),
        method="PUT",
    )

    if _is_success(status_code, data):
        return True, "Transaction verified."

    message = _non_empty(data.get("error") if isinstance(data, dict) else "")
    if not message:
        message = f"Przelewy24 verify failed (HTTP {status_code})."
    return False, message


def amount_to_grosz(amount: Decimal | int | float | str) -> int:
    return int((Decimal(str(amount)) * 100).quantize(Decimal("1")))


def _resolve_transaction_currency(config: dict, order_currency: Any) -> str:
    """
    Resolve currency used for Przelewy24 API calls.

    Sandbox merchant profiles commonly expose payment walls only for PLN.
    If checkout/order currency differs (e.g. USD from seed data), the sandbox
    can return no available methods. Keep production unchanged, but in sandbox
    normalize to PLN so payment methods are visible in test environments.
    """
    configured = _non_empty(order_currency).upper()
    if not configured:
        configured = DEFAULT_CURRENCY

    environment = _non_empty(config.get("environment")).lower()
    if environment not in {"prod", "production", "live"} and configured != DEFAULT_CURRENCY:
        return DEFAULT_CURRENCY

    return configured


def _extract_order_id_from_query(request) -> str:
    keys = ["orderId", "p24_order_id", "order_id"]
    for key in keys:
        value = str(request.GET.get(key) or "").strip()
        if value:
            return value
    return ""


def _extract_amount_from_query(request) -> str:
    keys = ["amount", "p24_amount"]
    for key in keys:
        value = str(request.GET.get(key) or "").strip()
        if value:
            return value
    return ""


def _extract_currency_from_query(request) -> str:
    keys = ["currency", "p24_currency"]
    for key in keys:
        value = str(request.GET.get(key) or "").strip()
        if value:
            return value
    return ""


def _resolve_payment_method_display_name(plugin: Plugin | None) -> str:
    if plugin is not None:
        plugin_name = _non_empty(plugin.name)
        if plugin_name:
            return plugin_name
        manifest_name = _non_empty((plugin.manifest or {}).get("name"))
        if manifest_name:
            return manifest_name
    return LEGACY_PAYMENT_METHOD_NAME


def _resolve_supported_payment_method_names(plugin: Plugin | None) -> set[str]:
    aliases = {
        _non_empty(LEGACY_PAYMENT_METHOD_NAME).lower(),
        _resolve_payment_method_display_name(plugin).lower(),
    }

    if plugin is not None:
        binding = PluginKVData.objects.filter(
            plugin=plugin,
            namespace=PAYMENT_METHOD_BINDING_NAMESPACE,
            key=PAYMENT_METHOD_BINDING_KEY,
        ).first()
        if binding and isinstance(binding.value, dict):
            bound_id = binding.value.get("id")
            try:
                method = PaymentMethod.objects.filter(pk=int(bound_id)).first()
            except Exception:
                method = None
            if method and _non_empty(method.name):
                aliases.add(_non_empty(method.name).lower())

    return {name for name in aliases if name}


def _resolve_bound_payment_method(plugin: Plugin | None) -> PaymentMethod | None:
    if plugin is None:
        plugin = Plugin.objects.filter(slug=PLUGIN_SLUG).first()
    if plugin is None:
        return None

    binding = PluginKVData.objects.filter(
        plugin=plugin,
        namespace=PAYMENT_METHOD_BINDING_NAMESPACE,
        key=PAYMENT_METHOD_BINDING_KEY,
    ).first()

    if binding and isinstance(binding.value, dict):
        bound_id = binding.value.get("id")
        try:
            method = PaymentMethod.objects.filter(pk=int(bound_id)).first()
        except Exception:
            method = None
        if method is not None:
            return method

    names = {
        _resolve_payment_method_display_name(plugin),
        LEGACY_PAYMENT_METHOD_NAME,
    }
    candidates = [name for name in names if _non_empty(name)]
    if not candidates:
        return None
    return PaymentMethod.objects.filter(name__in=candidates).order_by("id").first()


def _sync_payment_method_state(plugin: Plugin | None, *, is_active: bool) -> None:
    method = _resolve_bound_payment_method(plugin)
    if method is None:
        return
    if method.is_active != is_active:
        method.is_active = is_active
        method.save(update_fields=["is_active"])


def register(api):
    plugin = getattr(api, "plugin", None)
    if plugin is not None:
        ensure_plugin_payment_method(
            plugin,
            name=_resolve_payment_method_display_name(plugin),
            default_payment_time=1,
            is_active=True,
        )
    # Keep canonical hook names as string literals so lifecycle activation
    # preflight can statically detect required payment hooks.
    api.register_filter("payment.methods.load", filter_payment_methods, priority=20)
    api.register_filter("checkout.redirect_url.resolve", resolve_payment_redirect, priority=20)
    api.register_filter("plugin.flow.start", start_payment, priority=20)
    api.register_filter("plugin.flow.return", handle_return, priority=20)
    api.register_filter("plugin.test_connection", test_connection, priority=20)
    api.register_async_action("plugin.webhook.received", handle_payment_callback, priority=20)


def on_plugin_activated(plugin=None, **kwargs):
    _sync_payment_method_state(plugin, is_active=True)


def on_plugin_deactivated(plugin=None, **kwargs):
    _sync_payment_method_state(plugin, is_active=False)


def on_plugin_before_delete(plugin=None, **kwargs):
    _sync_payment_method_state(plugin, is_active=False)


def filter_payment_methods(value, request=None, cart=None):
    # Keep method synchronized in DB and return untouched queryset/list.
    return value


def resolve_payment_redirect(value, order=None, request=None):
    if not order:
        return value

    plugin = Plugin.objects.filter(slug=PLUGIN_SLUG, status=PluginStatus.ACTIVATED).first()
    if plugin is None:
        return value

    supported_names = _resolve_supported_payment_method_names(plugin)
    selected_name = _non_empty(getattr(order, "payment_method_name", "")).lower()
    if selected_name not in supported_names:
        return value

    return reverse(
        "plugins:provider_flow_start",
        kwargs={"plugin_slug": PLUGIN_SLUG, "token": order.tracking_token},
    )


def start_payment(value, request=None, plugin_slug=None, order=None):
    if plugin_slug != PLUGIN_SLUG:
        return value
    if not order or not request:
        return {
            "success": False,
            "redirect_url": "",
            "message": "Order context is missing for payment initialization.",
        }

    plugin = Plugin.objects.filter(slug=PLUGIN_SLUG).first()
    config = resolve_config((plugin.config or {}) if plugin else {})
    session_id = order.tracking_token
    amount_grosz = amount_to_grosz(order.total)
    currency = _resolve_transaction_currency(config, order.currency)

    return register_transaction(
        config=config,
        session_id=session_id,
        amount_grosz=amount_grosz,
        currency=currency,
        description=f"Order #{order.id}",
        email=order.email,
        country="PL",
        url_return=request.build_absolute_uri(
            reverse(
                "plugins:provider_flow_return",
                kwargs={"plugin_slug": PLUGIN_SLUG, "token": order.tracking_token},
            )
        ),
        url_status=request.build_absolute_uri(reverse("plugins:plugin_webhook", kwargs={"plugin_slug": PLUGIN_SLUG})),
    )


def handle_return(value, request=None, plugin_slug=None, order=None):
    if plugin_slug != PLUGIN_SLUG:
        return value
    if not order or not request:
        return {
            "success": False,
            "redirect_url": value.get("redirect_url") if isinstance(value, dict) else "",
            "message": "Order context is missing for payment confirmation.",
            "level": "error",
        }

    plugin = Plugin.objects.filter(slug=PLUGIN_SLUG).first()
    config = resolve_config((plugin.config or {}) if plugin else {})

    order_id = _extract_order_id_from_query(request)
    if not order_id:
        return {
            "success": False,
            "redirect_url": reverse("orders:summary", kwargs={"token": order.tracking_token}),
            "message": str(_("Payment pending confirmation from Przelewy24.")),
            "level": "info",
        }

    amount_text = _extract_amount_from_query(request)
    amount_grosz = int(amount_text) if amount_text.isdigit() else amount_to_grosz(order.total)
    currency = _extract_currency_from_query(request) or _resolve_transaction_currency(config, order.currency)

    verified, message = verify_transaction(
        config=config,
        session_id=order.tracking_token,
        order_id=order_id,
        amount_grosz=amount_grosz,
        currency=currency,
    )
    if not verified:
        return {
            "success": False,
            "redirect_url": reverse("orders:summary", kwargs={"token": order.tracking_token}),
            "message": message,
            "level": "error",
        }

    with transaction.atomic():
        if order.status != OrderStatus.PAID:
            order.status = OrderStatus.PAID
            order.save(update_fields=["status", "updated_at"])

    return {
        "success": True,
        "redirect_url": reverse("orders:summary", kwargs={"token": order.tracking_token}),
        "message": str(_("Payment successful. Thank you for your order!")),
        "level": "success",
    }


def test_connection(value, plugin_slug=None, plugin=None, request=None):
    if plugin_slug != PLUGIN_SLUG:
        return value
    config = resolve_config((plugin.config or {}) if plugin else {})
    success, message = test_access(config)
    return {"success": success, "message": message}


def handle_payment_callback(event_id=None, plugin_slug=None, payload=None):
    if plugin_slug != PLUGIN_SLUG:
        return

    data = payload or {}
    token = str(
        data.get("tracking_token")
        or data.get("order_token")
        or data.get("sessionId")
        or data.get("p24_session_id")
        or ""
    ).strip()
    order_id = str(data.get("orderId") or data.get("p24_order_id") or "").strip()
    if not token:
        return

    order = Order.objects.filter(tracking_token=token).first()
    if not order:
        return

    plugin = Plugin.objects.filter(slug=PLUGIN_SLUG).first()
    config = resolve_config((plugin.config or {}) if plugin else {})
    auto_capture = bool((plugin.config or {}).get("auto_capture", True)) if plugin else True
    if not auto_capture:
        return

    if not order_id:
        return

    amount = int(data.get("amount") or data.get("p24_amount") or amount_to_grosz(order.total))
    currency = (
        _non_empty(data.get("currency") or data.get("p24_currency"))
        or _resolve_transaction_currency(config, order.currency)
    )

    verified, message = verify_transaction(
        config=config,
        session_id=token,
        order_id=order_id,
        amount_grosz=amount,
        currency=currency,
    )
    if not verified:
        raise RuntimeError(message)

    if order.status != OrderStatus.PAID:
        order.status = OrderStatus.PAID
        order.save(update_fields=["status", "updated_at"])
