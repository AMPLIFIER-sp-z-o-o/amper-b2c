"""
Tpay payment plugin for AMPER-B2C.

Provider-specific behavior lives in this plugin package only.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

PLUGIN_SLUG = "tpay"
TPAY_API_BASE_PRODUCTION = "https://api.tpay.com"
TPAY_API_BASE_SANDBOX = "https://openapi.sandbox.tpay.com"
LEGACY_PAYMENT_METHOD_NAME = "Tpay"
PAYMENT_METHOD_BINDING_NAMESPACE = "payments"
PAYMENT_METHOD_BINDING_KEY = "payment_method_binding"


def _is_truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _resolve_api_base(cfg: dict | None) -> str:
    env_name = str((cfg or {}).get("environment") or "sandbox").strip().lower()
    return TPAY_API_BASE_SANDBOX if env_name == "sandbox" else TPAY_API_BASE_PRODUCTION


def resolve_config(plugin_config: dict | None) -> dict:
    """Merge admin config with environment variable overrides."""
    config: dict[str, str] = {
        "client_id": "",
        "client_secret": "",
        "environment": "sandbox",
    }

    plugin_config = plugin_config or {}
    for key in ("client_id", "client_secret", "environment"):
        raw = plugin_config.get(key)
        if raw is not None and str(raw).strip():
            config[key] = str(raw).strip()

    env_client_id = os.getenv("PAYMENTS_TPAY_CLIENT_ID", "")
    if env_client_id:
        config["client_id"] = env_client_id

    env_client_secret = os.getenv("PAYMENTS_TPAY_CLIENT_SECRET", "")
    if env_client_secret:
        config["client_secret"] = env_client_secret

    env_sandbox = os.getenv("PAYMENTS_TPAY_SANDBOX", "")
    if env_sandbox:
        config["environment"] = "sandbox" if _is_truthy(env_sandbox) else "production"

    return config


def _http_post_form(url: str, data: dict, timeout: int = 12) -> dict:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "AMPER-B2C-Tpay-Plugin/1.0")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return {"ok": True, "status_code": resp.status, "data": json.loads(resp.read() or b"{}")}
    except urllib.error.HTTPError as exc:
        try:
            err_data = json.loads(exc.read() or b"{}")
        except Exception:
            err_data = {"raw": str(exc)}
        return {"ok": False, "status_code": exc.code, "data": err_data}
    except Exception as exc:
        return {"ok": False, "status_code": 0, "data": {"error": str(exc)}}


def _http_post_json(url: str, data: dict, token: str, timeout: int = 12) -> dict:
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("User-Agent", "AMPER-B2C-Tpay-Plugin/1.0")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return {"ok": True, "status_code": resp.status, "data": json.loads(resp.read() or b"{}")}
    except urllib.error.HTTPError as exc:
        try:
            err_data = json.loads(exc.read() or b"{}")
        except Exception:
            err_data = {"raw": str(exc)}
        return {"ok": False, "status_code": exc.code, "data": err_data}
    except Exception as exc:
        return {"ok": False, "status_code": 0, "data": {"error": str(exc)}}


def _http_get_json(url: str, token: str, timeout: int = 12) -> dict:
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "AMPER-B2C-Tpay-Plugin/1.0")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return {"ok": True, "status_code": resp.status, "data": json.loads(resp.read() or b"{}")}
    except urllib.error.HTTPError as exc:
        try:
            err_data = json.loads(exc.read() or b"{}")
        except Exception:
            err_data = {"raw": str(exc)}
        return {"ok": False, "status_code": exc.code, "data": err_data}
    except Exception as exc:
        return {"ok": False, "status_code": 0, "data": {"error": str(exc)}}


def _log(plugin, message: str, payload: dict | None = None, level: str = "info") -> None:
    try:
        from apps.plugins.engine.log_utils import log_plugin_event

        log_plugin_event(
            plugin=plugin,
            event_type="tpay.event",
            message=message,
            payload=payload or {},
            level=level,
        )
    except Exception:
        pass


def _log_error(plugin, message: str, payload: dict | None = None) -> None:
    _log(plugin, message, payload=payload, level="error")


def _get_plugin():
    from apps.plugins.models import Plugin

    return Plugin.objects.filter(slug=PLUGIN_SLUG).first()


def _get_access_token(cfg: dict) -> str | None:
    """Get and cache OAuth token in PluginKVData."""
    from apps.plugins.models import PluginKVData

    plugin = _get_plugin()
    if plugin:
        cached = PluginKVData.objects.filter(
            plugin=plugin,
            namespace="auth",
            key="access_token",
        ).first()
        if cached:
            token_data = cached.value or {}
            if time.time() < float(token_data.get("expires_at") or 0) - 120:
                return str(token_data.get("access_token") or "") or None

    api_base = _resolve_api_base(cfg)
    resp = _http_post_form(
        f"{api_base}/oauth/auth",
        {
            "client_id": cfg.get("client_id", ""),
            "client_secret": cfg.get("client_secret", ""),
        },
    )
    if not resp.get("ok"):
        _log_error(plugin, "Tpay OAuth token request failed", payload=resp.get("data") or {})
        return None

    payload = resp.get("data") or {}
    access_token = str(payload.get("access_token") or "").strip()
    expires_in = int(payload.get("expires_in") or 7200)
    if not access_token:
        _log_error(plugin, "Tpay OAuth response missing access_token", payload=payload)
        return None

    if plugin:
        PluginKVData.objects.update_or_create(
            plugin=plugin,
            namespace="auth",
            key="access_token",
            defaults={
                "value": {
                    "access_token": access_token,
                    "expires_at": time.time() + expires_in,
                }
            },
        )

    return access_token


def _order_amount(order) -> float:
    for attr in ("total_price_gross", "total_gross", "total_price", "total", "amount"):
        raw = getattr(order, attr, None)
        if raw is None:
            continue
        try:
            return round(float(raw), 2)
        except (TypeError, ValueError):
            continue
    return 0.0


def _order_email(order) -> str:
    raw = getattr(order, "email", None)
    if raw:
        return str(raw)
    user = getattr(order, "user", None)
    if user and getattr(user, "email", None):
        return str(user.email)
    return ""


def _order_name(order) -> str:
    for attr in ("billing_full_name", "billing_name", "full_name"):
        raw = getattr(order, attr, None)
        if raw:
            return str(raw)
    user = getattr(order, "user", None)
    if user:
        full_name = getattr(user, "get_full_name", lambda: "")()
        if full_name:
            return str(full_name)
        if getattr(user, "email", None):
            return str(user.email)
    return "Customer"


def _mark_order_paid(order, plugin, transaction_ref: str) -> bool:
    try:
        if hasattr(order, "confirm") and callable(order.confirm):
            order.confirm()
            return True
        if hasattr(order, "mark_as_paid") and callable(order.mark_as_paid):
            order.mark_as_paid()
            return True

        for candidate_status in ("paid", "confirmed"):
            try:
                order.status = candidate_status
                order.save(update_fields=["status"])
                return True
            except Exception:
                continue
    except Exception as exc:
        _log_error(
            plugin,
            f"Failed to mark order #{getattr(order, 'id', 'unknown')} as paid",
            payload={"transaction_ref": transaction_ref, "error": str(exc)},
        )
    return False


def _resolve_payment_method_display_name(plugin) -> str:
    if plugin is not None:
        plugin_name = str(getattr(plugin, "name", "") or "").strip()
        if plugin_name:
            return plugin_name
        manifest_name = str((getattr(plugin, "manifest", {}) or {}).get("name") or "").strip()
        if manifest_name:
            return manifest_name
    return LEGACY_PAYMENT_METHOD_NAME


def _resolve_supported_payment_method_names(plugin) -> set[str]:
    """Return all acceptable payment method names for order matching."""
    from apps.cart.models import PaymentMethod
    from apps.plugins.models import PluginKVData

    aliases = {
        str(LEGACY_PAYMENT_METHOD_NAME).strip().lower(),
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
            if method and str(method.name or "").strip():
                aliases.add(str(method.name).strip().lower())

    return {name for name in aliases if name}


def register(api) -> None:
    from apps.plugins.adapters.payments import ensure_plugin_payment_method

    plugin = getattr(api, "plugin", None)
    if plugin:
        ensure_plugin_payment_method(
            plugin,
            name="Tpay",
            default_payment_time=1,
            is_active=True,
        )

    api.register_filter("checkout.redirect_url.resolve", resolve_redirect, priority=20)
    api.register_filter("plugin.flow.start", start_flow, priority=20)
    api.register_filter("plugin.flow.return", handle_return, priority=20)
    api.register_filter("plugin.test_connection", test_connection, priority=20, timeout_ms=1100)
    api.register_async_action("plugin.webhook.received", handle_webhook, priority=20)


def on_plugin_activated(plugin=None, **kwargs) -> None:
    if not plugin:
        return
    try:
        from apps.cart.models import PaymentMethod
        from apps.plugins.models import PluginKVData

        binding = PluginKVData.objects.filter(
            plugin=plugin,
            namespace="payments",
            key="payment_method_binding",
        ).first()
        bound_id = (binding.value or {}).get("id") if binding else None
        if bound_id:
            PaymentMethod.objects.filter(id=bound_id).update(is_active=True)
    except Exception:
        pass


def on_plugin_deactivated(plugin=None, **kwargs) -> None:
    if not plugin:
        return
    try:
        from apps.cart.models import PaymentMethod
        from apps.plugins.models import PluginKVData

        binding = PluginKVData.objects.filter(
            plugin=plugin,
            namespace="payments",
            key="payment_method_binding",
        ).first()
        bound_id = (binding.value or {}).get("id") if binding else None
        if bound_id:
            PaymentMethod.objects.filter(id=bound_id).update(is_active=False)
    except Exception:
        pass


def resolve_redirect(value, order=None, request=None, **kwargs):
    from django.urls import reverse

    from apps.plugins.models import PluginStatus

    if not order:
        return value

    plugin = _get_plugin()
    if not plugin or plugin.status != PluginStatus.ACTIVATED:
        return value

    supported_names = _resolve_supported_payment_method_names(plugin)
    selected_name = str(getattr(order, "payment_method_name", "") or "").strip().lower()
    if selected_name not in supported_names:
        return value

    return reverse(
        "plugins:provider_flow_start",
        kwargs={"plugin_slug": PLUGIN_SLUG, "token": order.tracking_token},
    )


def start_flow(value, request=None, order=None, plugin_slug=None, **kwargs):
    from django.urls import reverse

    from apps.plugins.models import PluginKVData

    if plugin_slug != PLUGIN_SLUG:
        return value

    plugin = _get_plugin()
    cfg = resolve_config(plugin.config if plugin else None)
    api_base = _resolve_api_base(cfg)

    if not cfg.get("client_id") or not cfg.get("client_secret"):
        _log_error(plugin, "Tpay credentials are missing")
        return {"success": False, "message": "Tpay is not configured. Please contact support."}

    token = _get_access_token(cfg)
    if not token:
        return {"success": False, "message": "Tpay authentication failed. Please try again."}

    if request:
        return_url = request.build_absolute_uri(
            reverse(
                "plugins:provider_flow_return",
                kwargs={"plugin_slug": PLUGIN_SLUG, "token": order.tracking_token},
            )
        )
        webhook_url = request.build_absolute_uri(
            reverse("plugins:plugin_webhook", kwargs={"plugin_slug": PLUGIN_SLUG})
        )
    else:
        return_url = f"/plugins/flow/{PLUGIN_SLUG}/return/{order.tracking_token}/"
        webhook_url = f"/plugins/webhooks/{PLUGIN_SLUG}/"

    amount = _order_amount(order)
    payload = {
        "amount": f"{amount:.2f}",
        "currency": "PLN",
        "description": f"Order #{order.id}",
        "hiddenDescription": str(order.tracking_token),
        "payer": {
            "email": _order_email(order) or "customer@example.com",
            "name": _order_name(order),
        },
        "lang": "pl",
        "callbacks": {
            "payerUrls": {
                "success": return_url,
                "error": return_url,
            },
            "notification": {
                "url": webhook_url,
            },
        },
    }

    response = _http_post_json(f"{api_base}/transactions", payload, token)
    if not response.get("ok"):
        _log_error(
            plugin,
            f"Failed to create Tpay transaction for order #{order.id}",
            payload={"status_code": response.get("status_code"), "data": response.get("data")},
        )
        return {"success": False, "message": "Failed to initialize payment. Please try again."}

    data = response.get("data") or {}
    transaction_id = str(data.get("transactionId") or "").strip()
    payment_url = str(data.get("transactionPaymentUrl") or "").strip()
    if not payment_url:
        _log_error(
            plugin,
            "Tpay transaction response missing transactionPaymentUrl",
            payload=data,
        )
        return {"success": False, "message": "Payment provider did not return redirect URL."}

    if plugin and transaction_id:
        PluginKVData.objects.update_or_create(
            plugin=plugin,
            namespace="transactions",
            key=str(order.tracking_token),
            defaults={
                "value": {
                    "transaction_id": transaction_id,
                    "order_id": order.id,
                    "amount": f"{amount:.2f}",
                }
            },
        )

    _log(
        plugin,
        f"Created Tpay transaction for order #{order.id}",
        payload={"transaction_id": transaction_id, "amount": f"{amount:.2f}"},
    )
    return {"success": True, "redirect_url": payment_url}


def handle_return(value, request=None, order=None, plugin_slug=None, **kwargs):
    from django.urls import reverse

    from apps.plugins.models import PluginKVData

    if plugin_slug != PLUGIN_SLUG:
        return value

    plugin = _get_plugin()
    cfg = resolve_config(plugin.config if plugin else None)
    api_base = _resolve_api_base(cfg)
    summary_url = reverse("orders:summary", kwargs={"token": order.tracking_token})

    transaction_id = ""
    if plugin:
        record = PluginKVData.objects.filter(
            plugin=plugin,
            namespace="transactions",
            key=str(order.tracking_token),
        ).first()
        if record:
            transaction_id = str((record.value or {}).get("transaction_id") or "").strip()

    if not transaction_id:
        _log(plugin, f"No cached Tpay transaction for order #{order.id}", level="warning")
        return {
            "success": False,
            "redirect_url": summary_url,
            "message": "Payment status could not be verified yet.",
            "level": "warning",
        }

    token = _get_access_token(cfg)
    if not token:
        return {
            "success": False,
            "redirect_url": summary_url,
            "message": "Payment verification failed.",
            "level": "error",
        }

    response = _http_get_json(f"{api_base}/transactions/{transaction_id}", token)
    if not response.get("ok"):
        _log_error(
            plugin,
            f"Failed to fetch Tpay transaction {transaction_id}",
            payload=response.get("data") or {},
        )
        return {
            "success": False,
            "redirect_url": summary_url,
            "message": "Payment verification failed.",
            "level": "error",
        }

    status = str((response.get("data") or {}).get("status") or "").strip().lower()
    if status in {"correct", "paid", "success"}:
        _mark_order_paid(order, plugin, transaction_ref=transaction_id)
        return {
            "success": True,
            "redirect_url": summary_url,
            "message": "Payment confirmed. Thank you!",
            "level": "success",
        }

    if status in {"pending", "new", "created", ""}:
        return {
            "success": False,
            "redirect_url": summary_url,
            "message": "Payment is being processed.",
            "level": "info",
        }

    return {
        "success": False,
        "redirect_url": summary_url,
        "message": "Payment was not successful.",
        "level": "error",
    }


def test_connection(value, plugin=None, plugin_slug=None, **kwargs):
    if plugin_slug != PLUGIN_SLUG:
        return value

    plugin = plugin or _get_plugin()
    cfg = resolve_config(plugin.config if plugin else None)

    if not cfg.get("client_id") or not cfg.get("client_secret"):
        return {"success": False, "message": "Client ID or Client Secret is not configured."}

    token = _get_access_token(cfg)
    if token:
        env_name = "Sandbox" if cfg.get("environment") == "sandbox" else "Production"
        return {"success": True, "message": f"Connected to Tpay {env_name} successfully."}

    return {"success": False, "message": "Authentication failed. Verify credentials."}


def handle_webhook(event_id=None, plugin_slug=None, payload=None, **kwargs):
    """Process queued webhook event for Tpay callback payload."""
    if plugin_slug != PLUGIN_SLUG:
        return

    if isinstance(payload, str):
        data = dict(urllib.parse.parse_qsl(payload, keep_blank_values=True))
    elif isinstance(payload, bytes):
        data = dict(urllib.parse.parse_qsl(payload.decode("utf-8"), keep_blank_values=True))
    elif isinstance(payload, dict):
        data = payload
    else:
        return

    transaction_status = str(data.get("tr_status") or "").strip().upper()
    order_token = str(data.get("tr_crc") or data.get("crc") or "").strip()
    transaction_ref = str(data.get("tr_id") or data.get("id") or "").strip()

    plugin = _get_plugin()
    _log(
        plugin,
        "Tpay webhook received",
        payload={
            "event_id": event_id,
            "transaction_status": transaction_status,
            "order_token": order_token,
            "transaction_ref": transaction_ref,
        },
    )

    if transaction_status not in {"TRUE", "PAID", "CORRECT", "SUCCESS"}:
        _log(
            plugin,
            "Tpay webhook ignored due to non-success status",
            payload={"transaction_status": transaction_status, "transaction_ref": transaction_ref},
            level="warning",
        )
        return

    if not order_token:
        _log_error(plugin, "Tpay webhook missing order token")
        return

    try:
        from apps.orders.models import Order

        order = Order.objects.filter(tracking_token=order_token).first()
        if not order:
            _log_error(
                plugin,
                "Order not found for Tpay webhook",
                payload={"order_token": order_token, "transaction_ref": transaction_ref},
            )
            return

        if _mark_order_paid(order, plugin, transaction_ref=transaction_ref):
            _log(
                plugin,
                f"Order #{order.id} confirmed from Tpay webhook",
                payload={"transaction_ref": transaction_ref},
            )
        else:
            _log_error(
                plugin,
                f"Could not update order #{order.id} from Tpay webhook",
                payload={"transaction_ref": transaction_ref},
            )
    except Exception as exc:
        _log_error(
            plugin,
            "Unexpected error while handling Tpay webhook",
            payload={"error": str(exc), "order_token": order_token, "transaction_ref": transaction_ref},
        )
