# Plugin Developer Guide

Complete reference for building a plugin: two required files, optional config schema, available APIs and hooks, full examples.

---

## 1. Quickstart — hello world in 5 minutes

Two files, one ZIP.

**Step 1 — Create the plugin folder**

Use your plugin's slug as the folder name (`kebab-case`, lowercase, no spaces):

```
hello-world/
```

**Step 2 — `hello-world/manifest.json`**

```json
{
  "slug": "hello-world",
  "name": "Hello World",
  "version": "1.0.0",
  "entrypoint": "entrypoint.py",
  "scopes": [],
  "dependencies": [],
  "default_config": {}
}
```

**Step 3 — `hello-world/entrypoint.py`**

```python
PLUGIN_SLUG = "hello-world"


def register(api):
    """Called once when the plugin is loaded. Register all hooks here."""
    api.register_action("order.status.changed", on_order_status_changed, priority=20)


def on_order_status_changed(order=None, previous_status=None, status=None, **kwargs):
    """Called whenever any order changes status."""
    print(f"[hello-world] order {getattr(order, 'id', '?')} changed: {previous_status} → {status}")
```

**Step 4 — Package as a ZIP**

```
hello-world.zip
└── hello-world/
    ├── manifest.json
    └── entrypoint.py
```

```bash
# Linux / macOS
zip -r hello-world.zip hello-world/

# Windows PowerShell
Compress-Archive -Path hello-world -DestinationPath hello-world.zip
```

**Step 5 — Validate**

```bash
uv run manage.py plugins_validate_zip hello-world.zip
uv run manage.py plugins_validate_zip hello-world.zip --strict
```

Fix every `ERROR` before delivering. `WARNING` items are advisory. See [§13 — Packaging & validation](#13-packaging--validation).

### Bundled plugins: delete + seed restore behavior

For bundled plugins (for example `przelewy24`, `tpay`), admin deletion now follows this flow:

1. Create/update a backup ZIP in `plugins/dist/<slug>.zip`
2. Remove plugin source directory from `plugins/<slug>/`
3. Delete plugin DB record

`make reset-db-seed` restores bundled plugins from seed data (`assets/seeds/generated/plugins_data.json`) and ZIP packages in `plugins/dist/` when source folders are missing.

If both source directory and ZIP are missing, seed cannot restore that plugin and logs `Plugin skipped (not found): <slug>`.

---

> **Developer checklist**
>
> - `register(api)` is a plain synchronous `def` — never `async def`
> - Every hook callback accepts `**kwargs` to stay forward-compatible
> - Provider-flow callbacks guard by slug: `if plugin_slug != PLUGIN_SLUG: return value`
> - Provider flow routes use `plugins:provider_flow_start` and `plugins:provider_flow_return`
> - Provider webhook route uses `plugins:plugin_webhook`
> - No hardcoded secrets — use `env_vars` in the manifest
> - `http:outbound` is in `scopes` if your code calls external APIs

---

## 2. Plugin structure

```text
my-plugin/
├── manifest.json         # required — plugin metadata
├── entrypoint.py         # required — register(api) function
├── config.schema.json    # optional — config fields (JSON Schema)
└── migrations.py         # optional — custom DB table migrations
```

---

## 3. `manifest.json`

### Minimal (no config)

```json
{
  "slug": "my-plugin",
  "name": "My Plugin",
  "version": "1.0.0",
  "entrypoint": "entrypoint.py",
  "scopes": [],
  "dependencies": [],
  "default_config": {}
}
```

### With API keys and config

```json
{
  "slug": "my-plugin",
  "name": "My Plugin",
  "version": "1.0.0",
  "entrypoint": "entrypoint.py",
  "scopes": ["http:outbound"],
  "dependencies": [],
  "default_config": {
    "environment": "sandbox"
  },
  "env_vars": {
    "api_key": "MY_PLUGIN_API_KEY",
    "environment": "MY_PLUGIN_ENV"
  }
}
```

### Field reference

| Field                  | Required | Description                                                               |
| ---------------------- | -------- | ------------------------------------------------------------------------- |
| `slug`                 | ✅       | Unique plugin ID — `kebab-case`, lowercase                                |
| `name`                 | ✅       | Human-readable display name                                               |
| `version`              | ✅       | SemVer (e.g. `1.0.0`)                                                     |
| `entrypoint`           | ❌       | Python file with `register(api)` — default: `entrypoint.py`               |
| `scopes`               | ❌       | Permissions — see scope table below                                       |
| `dependencies`         | ❌       | List of other plugin slugs this plugin requires                           |
| `core_version_min/max` | ❌       | Platform version constraints                                              |
| `config_schema`        | ❌       | Inline JSON Schema for config fields (prefer `config.schema.json`)        |
| `default_config`       | ❌       | Default config values applied on first install                            |
| `env_vars`             | ❌       | Maps config keys → environment variable names (highest-priority override) |

### Scopes

| Scope            | Required when                                           |
| ---------------- | ------------------------------------------------------- |
| `http:outbound`  | Your code calls `api.http.*`                            |
| `data:write`     | Your code calls `api.data.set()` or `api.data.delete()` |
| `payments:write` | Your code calls `ensure_plugin_payment_method()`        |

### `env_vars` — environment variable mapping

Maps config field names to environment variable names. The platform reads these env vars at runtime and overlays them on top of any stored config. Config precedence (highest → lowest):

1. Environment variable
2. Stored config / `default_config`
3. Hardcoded safe default (non-secret only)

Implement this in `resolve_config()` in your `entrypoint.py` — see the template in §5.

---

## 4. `config.schema.json`

Include this file when your plugin has configurable fields (API keys, URLs, feature flags). The platform reads it and presents the fields as a configuration form.

```json
{
  "type": "object",
  "required": ["api_key"],
  "properties": {
    "api_key": {
      "type": "string",
      "title": "API Key",
      "format": "password"
    },
    "environment": {
      "type": "string",
      "title": "Environment",
      "default": "sandbox",
      "enum": ["sandbox", "production"]
    },
    "webhook_secret": {
      "type": "string",
      "title": "Webhook Secret",
      "format": "password"
    },
    "enabled": {
      "type": "boolean",
      "title": "Enabled",
      "default": true
    }
  }
}
```

### Field types

| `type`                            | Rendered as           |
| --------------------------------- | --------------------- |
| `string`                          | Text input            |
| `string` + `"format": "password"` | Masked password input |
| `string` + `"enum": [...]`        | Dropdown select       |
| `boolean`                         | Checkbox              |
| `integer` / `number`              | Number input          |

You can also embed the schema inline in `manifest.json` under `config_schema`, but a separate file is cleaner.

### Alternative: declare `env_vars` inside `config.schema.json`

If `manifest.json` does not contain an `env_vars` key, the platform also looks for it in `config.schema.json`. Supported locations (tried in order):

1. Top-level `"env_vars"` key in the schema object (same format as in `manifest.json`)
2. Top-level `"x_env_vars"` key (alias)
3. Per-property `"env_var"` / `"x_env_var"` / `"x-env-var"` field inside each property definition

Example — per-property style:

```json
{
  "type": "object",
  "required": ["api_key"],
  "properties": {
    "api_key": {
      "type": "string",
      "title": "API Key",
      "format": "password",
      "env_var": "MY_PLUGIN_API_KEY"
    }
  }
}
```

All three styles are equivalent at runtime. The simplest approach is to keep `env_vars` in `manifest.json`; use these alternatives only if you prefer to colocate the mapping with the schema.

---

## 5. `entrypoint.py`

Full template with every available feature:

```python
from __future__ import annotations

import os


PLUGIN_SLUG = "my-plugin"


# ─── Config resolution ────────────────────────────────────────────────────────
# Call this in every hook callback to get the effective runtime config.

def resolve_config(plugin_config: dict | None) -> dict:
    """Merge stored config with environment variable overrides."""
    config = {
        "api_key": "",
        "environment": "sandbox",
    }

    # Layer 1: stored config
    plugin_config = plugin_config or {}
    for key in config:
        value = plugin_config.get(key)
        if value is not None and str(value).strip():
            config[key] = value

    # Layer 2: env vars (highest priority)
    env_api_key = os.getenv("MY_PLUGIN_API_KEY", "")
    if env_api_key:
        config["api_key"] = env_api_key

    env_mode = os.getenv("MY_PLUGIN_ENV", "")
    if env_mode:
        config["environment"] = env_mode

    return config


# ─── Hook registration (REQUIRED) ─────────────────────────────────────────────
# register(api) MUST be synchronous (def, not async def).

def register(api):
    """Called once when plugin is loaded. Register all hooks here."""

    # Filter — transforms a value and must return it
    api.register_filter("my.domain.hook", my_filter_callback, priority=20)

    # Action — fire-and-forget, return value ignored
    api.register_action("my.domain.event", my_action_callback, priority=20)

    # Async action — runs in a Celery background worker
    api.register_async_action("plugin.webhook.received", handle_webhook, priority=20)


# ─── Lifecycle callbacks (OPTIONAL) ───────────────────────────────────────────
# Define these functions and the platform calls them automatically via signals.
# No registration needed.

def on_plugin_status_changed(plugin=None, previous_status=None, current_status=None, created=False, **kwargs):
    """Called on every plugin save after status is resolved."""
    pass

def on_plugin_created(plugin=None, **kwargs):
    """Called once when a new plugin record is first created."""
    pass

def on_plugin_activated(plugin=None, **kwargs):
    """Called when the plugin is activated."""
    pass

def on_plugin_deactivated(plugin=None, **kwargs):
    """Called when the plugin is deactivated."""
    pass

def on_plugin_before_delete(plugin=None, **kwargs):
    """Called before the plugin record is deleted."""
    pass


# ─── Hook callbacks ────────────────────────────────────────────────────────────

def my_filter_callback(value, request=None, **kwargs):
    """Filter: receives value, must return transformed value."""
    return value


def my_action_callback(request=None, **kwargs):
    """Action: fire-and-forget, return value is ignored."""
    pass


async def handle_webhook(event_id=None, plugin_slug=None, payload=None, **kwargs):
    """Async action: runs in Celery background worker."""
    if plugin_slug != PLUGIN_SLUG:
        return
    # process payload
```

---

## 6. `PluginAPI` — available methods

The `api` object is passed to `register(api)` only. It is **not** available inside hook callbacks.

| Method                                                                          | Scope required  |
| ------------------------------------------------------------------------------- | --------------- |
| `api.register_filter(hook, callback, priority=50, timeout_ms=None)`             | —               |
| `api.register_action(hook, callback, priority=50, timeout_ms=None)`             | —               |
| `api.register_async_action(hook, callback, priority=50)`                        | —               |
| `api.AbortAction`                                                               | —               |
| `api.data.get(key, namespace="default", default=None)`                          | —               |
| `api.data.set(key, value, namespace="default")`                                 | `data:write`    |
| `api.data.delete(key, namespace="default")`                                     | `data:write`    |
| `api.data.list_namespace(namespace="default") -> dict`                          | —               |
| `api.http.get(url, headers=None, timeout_seconds=4.0)`                          | `http:outbound` |
| `api.http.post(url, body=None, headers=None, timeout_seconds=4.0)`              | `http:outbound` |
| `api.http.request(method, url, body=None, headers=None, timeout_seconds=4.0)`   | `http:outbound` |
| `api.plugin` — raw Plugin ORM instance (`.slug`, `.name`, `.config`, `.status`) | —               |

### `api` is only available inside `register(api)`

Hook callbacks are plain functions and do not receive `api`. To read plugin config inside a callback, fetch the plugin instance from the DB:

```python
def start_flow(value, order=None, plugin_slug=None, **kwargs):
    if plugin_slug != PLUGIN_SLUG:
        return value
    from apps.plugins.models import Plugin
    plugin = Plugin.objects.filter(slug=PLUGIN_SLUG).first()
    cfg = resolve_config(plugin.config if plugin else None)
    # ...
```

To read KV data inside a callback, use the ORM directly:

```python
from apps.plugins.models import PluginKVData

record = PluginKVData.objects.filter(plugin=plugin, namespace="payments", key="binding").first()
```

### `api.payments` does NOT exist

```python
# ✅ correct
from apps.plugins.adapters.payments import ensure_plugin_payment_method
ensure_plugin_payment_method(plugin, name="My Plugin", default_payment_time=1, is_active=True)

# ❌ wrong — AttributeError → plugin force-deactivated
api.payments.ensure_payment_method(...)
```

### `api.http` response format

```python
{
    "ok": True,           # False on HTTP error or network failure
    "status_code": 200,   # 0 on connection failure
    "data": {...}         # parsed JSON, or {"raw": "..."} if not JSON
}
```

Never raises — always check `response["ok"]` before reading `response["data"]`.

### `timeout_ms` and execution budget

Sync callbacks run in a separate thread. If a callback exceeds its per-hook timeout the thread is detached and the hook is skipped without propagating an exception.

- Default per-hook timeout: **350 ms**
- Global request budget: **1200 ms** total across all plugin hooks in one request
- Override per hook: `api.register_filter("my.hook", cb, timeout_ms=800)`

Provider flow reliability note:

- Generic timeout/budget behavior applies to standard `dispatch_action` / `apply_filters` execution.
- Provider routes (`provider_flow_start` / `provider_flow_return`) run the target plugin callback directly.
- Keep `timeout_ms` tuned for hooks that still use generic dispatch (for example `plugin.test_connection`).

### Logging from plugin code

```python
from apps.plugins.engine.log_utils import log_plugin_event
from apps.plugins.models import Plugin

def start_flow(value, plugin_slug=None, order=None, **kwargs):
    if plugin_slug != PLUGIN_SLUG:
        return value
    plugin = Plugin.objects.filter(slug=PLUGIN_SLUG).first()
    log_plugin_event(
        plugin=plugin,
        event_type="payment.start",
        message=f"Starting payment for order {order.id}",
        payload={"order_id": order.id},  # any JSON-serialisable dict
        level="info",                    # "info" | "warning" | "error"
    )
```

---

## 7. Available hooks

### Core hooks

| Hook name                        | Type         | Context kwargs                       | Returns                                                                |
| -------------------------------- | ------------ | ------------------------------------ | ---------------------------------------------------------------------- |
| `checkout.redirect_url.resolve`  | Filter       | `order`, `request`                   | URL string                                                             |
| `plugin.flow.start`              | Filter       | `order`, `request`, `plugin_slug`    | `{"success": bool, "redirect_url": str}`                               |
| `plugin.flow.return`             | Filter       | `order`, `request`, `plugin_slug`    | `{"success": bool, "redirect_url": str, "message": str, "level": str}` |
| `plugin.webhook.received`        | Async Action | `event_id`, `plugin_slug`, `payload` | —                                                                      |
| `plugin.test_connection`         | Filter       | `plugin`, `plugin_slug`, `request`   | `{"success": bool, "message": str}`                                    |
| `delivery.methods.load`          | Filter       | `request`, `cart`                    | modified methods list                                                  |
| `payment.methods.load`           | Filter       | `request`, `cart`                    | modified methods list                                                  |
| `order.status.changed`           | Action       | `order`, `previous_status`, `status` | —                                                                      |
| `order.shipped`                  | Action       | `order`, `previous_status`, `status` | —                                                                      |
| `notification.email.before_send` | Filter       | `order`, `notification_type`         | modified email payload                                                 |

You can register on **any hook name** — the system is fully open.

> **Note**: `checkout.render` and `order.created` exist as reserved names in the codebase but are not dispatched by the platform yet. Registering on them does nothing until they are wired up in a future release.

Legacy aliases (core also dispatches these for backwards compatibility):

- `payment.redirect_url.resolve` → `checkout.redirect_url.resolve`
- `payment.provider.start` → `plugin.flow.start`
- `payment.provider.return` → `plugin.flow.return`
- `payment.callback.received` → `plugin.webhook.received`

### UI injection hooks

Register a filter on any of these — return a string and the platform injects it into every storefront page automatically. No template changes needed.

| Hook name                    | Injected into          |
| ---------------------------- | ---------------------- |
| `storefront.base.head`       | `<head>`               |
| `storefront.base.body.start` | right after `<body>`   |
| `storefront.base.body.end`   | right before `</body>` |

Use `window.location.pathname` inside injected JS to limit execution to specific pages:

| Page               | Path pattern               |
| ------------------ | -------------------------- |
| Product detail     | `/product/<slug>/`         |
| Category / listing | `/category/` or `/search/` |
| Cart               | `/cart/`                   |
| Checkout           | `/cart/checkout/`          |
| Order summary      | `/orders/`                 |

### Guard pattern — required for shared hooks

Multiple plugins can register on the same hook. Each callback **must guard by slug**:

```python
def start_flow(value, plugin_slug=None, order=None, **kwargs):
    if plugin_slug != PLUGIN_SLUG:
        return value  # not for us — pass through unchanged
    # ... our logic ...
    return {"success": True, "redirect_url": "https://..."}
```

Apply to: `plugin.flow.start`, `plugin.flow.return`, `plugin.test_connection`, `plugin.webhook.received`, `checkout.redirect_url.resolve`.

### Abort pattern

`api.AbortAction` is only accessible inside `register(api)`. To use it in a hook callback, save a module-level reference in `register()`:

```python
_AbortAction = None


def register(api):
    global _AbortAction
    _AbortAction = api.AbortAction
    api.register_filter("plugin.flow.start", start_flow, priority=20)


def start_flow(value, plugin_slug=None, **kwargs):
    if plugin_slug != PLUGIN_SLUG:
        return value
    if not is_provider_enabled():
        raise _AbortAction("Provider temporarily disabled")
    return {"success": True, "redirect_url": "https://..."}
```

Raising `AbortAction` stops hook processing cleanly — it is not treated as an error.

### Provider-flow contract (critical)

Provider routes are plugin-targeted:

- `/plugins/flow/<slug>/start/<token>/` runs only the selected plugin's `plugin.flow.start` callback.
- `/plugins/flow/<slug>/return/<token>/` runs only the selected plugin's `plugin.flow.return` callback.
- This prevents cross-plugin interference and reduces false fallbacks.

Expected return contracts:

- `plugin.flow.start` -> `{"success": bool, "redirect_url": str, "message": str?}`
- `plugin.flow.return` -> `{"success": bool, "redirect_url": str, "message": str?, "level": "success|info|warning|error"?}`

If `plugin.flow.start` does not return a valid success payload with `redirect_url`, checkout falls back to:

- `/orders/pay/<token>/?provider_error=1`

The fallback is intentional and indicates payment-provider initialization failed.

### Webhook route and ACK semantics

- Canonical webhook route name: `plugins:plugin_webhook`
- URL pattern: `/plugins/webhooks/<plugin_slug>/`
- Do not use incorrect route names (for example `plugins:webhook`).

ACK body can be provider-specific:

- Default behavior is JSON (`{"success": true, ...}`).
- Some providers require strict plain-text ACK values (for example Tpay expects `TRUE` / `FALSE`).

Before production launch, verify required webhook ACK success/error bodies in provider documentation and test real callbacks.

---

## 8. Payment plugin — complete example

### `manifest.json`

```json
{
  "slug": "my-payment-plugin",
  "name": "My Payment Plugin",
  "version": "1.0.0",
  "entrypoint": "entrypoint.py",
  "scopes": ["payments:write", "http:outbound"],
  "dependencies": [],
  "default_config": { "environment": "sandbox" },
  "env_vars": {
    "merchant_id": "PAYMENTS_MY_MERCHANT_ID",
    "api_key": "PAYMENTS_MY_API_KEY"
  }
}
```

### `entrypoint.py`

```python
from __future__ import annotations
import os
from apps.plugins.adapters.payments import ensure_plugin_payment_method

PLUGIN_SLUG = "my-payment-plugin"


def resolve_config(plugin_config):
    config = {"merchant_id": "", "api_key": "", "environment": "sandbox"}
    plugin_config = plugin_config or {}
    for key in config:
        val = plugin_config.get(key)
        if val is not None and str(val).strip():
            config[key] = val
    if v := os.getenv("PAYMENTS_MY_MERCHANT_ID"): config["merchant_id"] = v
    if v := os.getenv("PAYMENTS_MY_API_KEY"):     config["api_key"] = v
    return config


def register(api):
    plugin = getattr(api, "plugin", None)
    if plugin:
        ensure_plugin_payment_method(plugin, name=plugin.name, default_payment_time=1, is_active=True)

    api.register_filter("checkout.redirect_url.resolve", resolve_redirect, priority=20)
    api.register_filter("plugin.flow.start",             start_flow,        priority=20)
    api.register_filter("plugin.flow.return",            handle_return,     priority=20)
    api.register_filter("plugin.test_connection",        test_connection,   priority=20)
    api.register_async_action("plugin.webhook.received", handle_webhook,    priority=20)


def resolve_redirect(value, order=None, request=None, **kwargs):
    from apps.plugins.models import Plugin, PluginStatus, PluginKVData
    from django.urls import reverse

    if not order:
        return value
    plugin = Plugin.objects.filter(slug=PLUGIN_SLUG, status=PluginStatus.ACTIVATED).first()
    if not plugin:
        return value
    binding = PluginKVData.objects.filter(
        plugin=plugin, namespace="payments", key="payment_method_binding"
    ).first()
    if not binding:
        return value
    bound_id = (binding.value or {}).get("id")
    pm = getattr(order, "payment_method", None)
    if pm is None or pm.id != bound_id:
        return value
    return reverse("plugins:provider_flow_start",
                   kwargs={"plugin_slug": PLUGIN_SLUG, "token": order.tracking_token})


def start_flow(value, request=None, order=None, plugin_slug=None, **kwargs):
    if plugin_slug != PLUGIN_SLUG:
        return value
    from apps.plugins.models import Plugin
    from django.urls import reverse

    plugin = Plugin.objects.filter(slug=PLUGIN_SLUG).first()
    cfg = resolve_config(plugin.config if plugin else None)

    return_url = request.build_absolute_uri(
        reverse("plugins:provider_flow_return", kwargs={"plugin_slug": PLUGIN_SLUG, "token": order.tracking_token})
    ) if request else f"/plugins/flow/{PLUGIN_SLUG}/return/{order.tracking_token}/"
    webhook_url = request.build_absolute_uri(
        reverse("plugins:plugin_webhook", kwargs={"plugin_slug": PLUGIN_SLUG})
    ) if request else f"/plugins/webhooks/{PLUGIN_SLUG}/"

    # TODO: call provider API — register transaction, get redirect URL
    # TODO: include return_url + webhook_url in provider payload if required
    # return {"success": True, "redirect_url": "https://provider.example.com/pay?token=..."}
    return {"success": False, "message": "Not implemented yet"}


def handle_return(value, request=None, order=None, plugin_slug=None, **kwargs):
    if plugin_slug != PLUGIN_SLUG:
        return value
    # TODO: verify payment status with provider API
    # return {"success": True, "redirect_url": f"/orders/summary/{order.tracking_token}/",
    #         "message": "Payment confirmed!", "level": "success"}
    return {"success": False, "redirect_url": "/", "message": "Not implemented yet"}


def test_connection(value, plugin=None, plugin_slug=None, **kwargs):
    if plugin_slug != PLUGIN_SLUG:
        return value
    # TODO: call provider API to verify credentials
    return {"success": True, "message": "Connection OK"}


async def handle_webhook(event_id=None, plugin_slug=None, payload=None, **kwargs):
    if plugin_slug != PLUGIN_SLUG:
        return
    import urllib.parse
    if isinstance(payload, str):
        data = dict(urllib.parse.parse_qsl(payload))
    else:
        data = payload or {}
    # TODO: verify signature, update order status
```

### How the platform calls your code

1. **Checkout submit** → platform calls `checkout.redirect_url.resolve`
   → `resolve_redirect()` checks the order's payment method and returns the start URL.

2. **Flow start** — user hits `/plugins/flow/<slug>/start/<token>/`
   → platform calls `plugin.flow.start`
   → `start_flow()` calls the external provider, returns `{"success": True, "redirect_url": "https://..."}`.

3. **Flow return** — user returns to `/plugins/flow/<slug>/return/<token>/`
   → platform calls `plugin.flow.return`
   → `handle_return()` verifies with the provider, returns `{"success": True, "redirect_url": "/orders/summary/...", "message": "Payment confirmed!", "level": "success"}`.

4. **Webhook** — provider POSTs to `/plugins/webhooks/<slug>/`
   → platform deduplicates, queues a Celery task, calls `plugin.webhook.received`
   → `handle_webhook()` verifies the signature, updates the order.

   Provider-specific ACK note: some gateways require strict text responses (for example `TRUE` / `FALSE`) instead of JSON.

   Deduplication: duplicate raw body (SHA-256) or duplicate `provider_event_id` returns `{"success": true, "duplicate": true}` immediately. `provider_event_id` is auto-extracted from `event_id`, `eventId`, `id`, or `orderId` in the payload.

### `ensure_plugin_payment_method()`

Payment plugins **must** call this in `register()`. Without it the payment option won't appear in checkout.

- Creates a `PaymentMethod` row if none exists
- Updates name / active status if it already exists
- Stores a binding in `PluginKVData` so the plugin knows which `PaymentMethod` it owns
- Requires scope `payments:write` in `manifest.json`

### Payment-provider hardening checklist

Use this checklist before releasing a payment plugin:

- Build provider start/return URLs with named routes: `plugins:provider_flow_start` and `plugins:provider_flow_return`.
- Build webhook URL with `plugins:plugin_webhook`.
- Validate provider payload field names strictly against provider docs (avoid undocumented fields).
- Verify required outbound HTTP headers (`Content-Type`, auth headers, and `User-Agent` if required).
- Implement provider-required webhook authenticity checks (signature/certificate/checksum).
- Confirm required webhook ACK body format (JSON vs strict text response).
- Simulate provider failure and verify fallback behavior (`provider_error=1`) is reached only on real initialization errors.
- Run `uv run manage.py plugins_validate_zip /path/to/plugin.zip --strict` before upload.

---

## 9. Delivery plugin — complete example

### `manifest.json`

```json
{
  "slug": "my-delivery-plugin",
  "name": "My Delivery Plugin",
  "version": "1.0.0",
  "entrypoint": "entrypoint.py",
  "scopes": ["http:outbound"],
  "dependencies": [],
  "default_config": { "environment": "sandbox" },
  "env_vars": { "api_key": "DELIVERY_MY_API_KEY" }
}
```

### `entrypoint.py`

```python
PLUGIN_SLUG = "my-delivery-plugin"


def register(api):
    api.register_filter("delivery.methods.load",  add_methods,     priority=20)
    api.register_action("order.shipped",          create_label,    priority=20)
    api.register_filter("plugin.test_connection", test_connection, priority=20)


def add_methods(value, request=None, cart=None, **kwargs):
    """Append shipping options to the available delivery methods list."""
    # value is the current list — return it extended with your options
    return value


def create_label(order=None, **kwargs):
    """Call the provider API to generate a shipping label."""
    pass


def test_connection(value, plugin=None, plugin_slug=None, **kwargs):
    if plugin_slug != PLUGIN_SLUG:
        return value
    return {"success": True, "message": "API responding"}
```

---

## 10. UI / theme injection — complete example

### `manifest.json`

```json
{
  "slug": "my-ui-plugin",
  "name": "My UI Plugin",
  "version": "1.0.0",
  "entrypoint": "entrypoint.py",
  "scopes": [],
  "dependencies": [],
  "default_config": {}
}
```

### `entrypoint.py`

```python
PLUGIN_SLUG = "my-ui-plugin"


def register(api):
    api.register_filter("storefront.base.head",     inject_head,     priority=10)
    api.register_filter("storefront.base.body.end", inject_body_end, priority=10)


def inject_head(value, request=None, **kwargs):
    return value + '<link rel="stylesheet" href="https://example.com/widget.css">'


def inject_body_end(value, request=None, **kwargs):
    return value + """
<script>
document.addEventListener('DOMContentLoaded', function () {
    // use window.location.pathname to target specific pages:
    //   /product/<slug>/   — product detail
    //   /category/         — category listing
    //   /cart/             — cart
    //   /cart/checkout/    — checkout
    //   /orders/           — order summary
    if (window.location.pathname.startsWith('/product/')) {
        var el = document.querySelector('#product-description-body');
        if (el) el.insertAdjacentHTML('afterend', '<p>My plugin content</p>');
    }
});
</script>
"""
```

---

## 11. Data storage

Plugins cannot ship `models.py`/`migrations/` — they are not Django apps. Use the built-in KV store or a custom `migrations.py`.

### KV store inside `register(api)`

`set()` and `delete()` require scope `data:write`. `get()` and `list_namespace()` are read-only and work without any scope.

```python
api.data.set("last_sync", {"order_id": 42, "ts": "2025-01-01"})  # requires data:write
last = api.data.get("last_sync", default=None)                    # no scope needed
api.data.delete("last_sync")                                       # requires data:write
all_keys = api.data.list_namespace(namespace="cache")             # no scope needed
```

### KV store inside hook callbacks

```python
from apps.plugins.models import PluginKVData, Plugin

plugin = Plugin.objects.filter(slug=PLUGIN_SLUG).first()
record = PluginKVData.objects.filter(plugin=plugin, namespace="cache", key="token").first()
```

### Custom DB tables — `migrations.py`

```python
# my-plugin/migrations.py
from django.db import connection


def upgrade(from_version, to_version, plugin):
    """Called when installing a newer version. Runs inside a DB transaction."""
    with connection.cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS plugin_my_plugin_data (
                id serial PRIMARY KEY,
                plugin_id integer NOT NULL,
                value jsonb NOT NULL DEFAULT '{}'
            )
        """)


def downgrade(from_version, to_version, plugin):
    """Called when rolling back. Runs inside a DB transaction."""
    with connection.cursor() as cursor:
        cursor.execute("DROP TABLE IF EXISTS plugin_my_plugin_data")
```

- `upgrade` — called when installing a newer version
- `downgrade` — called when rolling back to an older version
- both run inside a DB transaction
- if the callable is missing, install proceeds without migration

---

## 12. Secrets

- **Never include real credentials in the ZIP**
- Declare secret fields in `config.schema.json` with `"format": "password"` — values are masked at rest
- Map those field names in `env_vars` so the value can be supplied via a server environment variable
- Non-secret defaults go in `default_config`

```json
{
  "env_vars": {
    "api_key": "MY_PLUGIN_API_KEY",
    "environment": "MY_PLUGIN_ENV"
  },
  "default_config": {
    "environment": "sandbox"
  }
}
```

Always implement `resolve_config()` in `entrypoint.py` (see §5) to apply env var overrides at runtime.

Where values live (important):

- ZIP contains only variable names (mapping), for example `"api_key": "MY_PLUGIN_API_KEY"` in `manifest.json`.
- ZIP must not contain real secret values and does not ship a `.env` file.
- Real values are provided outside ZIP:
  - server/container environment (`.env`, deployment variables, secrets manager), or
  - plugin configuration form in Admin (stored fallback when env var is not set).

Effective precedence at runtime:

1. Environment variable value (if non-empty)
2. Value saved in plugin configuration form
3. `default_config` from manifest (non-secret defaults)

---

## 13. Packaging & validation

### ZIP layout

```text
my-plugin.zip
└── my-plugin/              ← folder name is irrelevant; slug comes from manifest.json
    ├── manifest.json       ← required
    ├── entrypoint.py       ← required
    ├── config.schema.json  ← optional
    └── migrations.py       ← optional
```

Rules:

- exactly one `manifest.json` per ZIP
- path traversal is rejected at upload
- `manifest.json` may be at archive root or inside a folder
- install path is always derived from `manifest.slug`
- when updating an existing plugin the ZIP slug must match the existing slug exactly

### Validation command

```bash
uv run manage.py plugins_validate_zip /path/to/plugin.zip
uv run manage.py plugins_validate_zip /path/to/plugin.zip --strict
```

**Blocking errors** stop installation. **Warnings** stop installation only in strict mode.

What is checked:

- ZIP safety (no path traversal)
- `manifest.json` presence and required fields (`slug`, `name`, `version`)
- `entrypoint.py` importability (Python syntax)
- `register(api)` function exists with correct signature
- Declared scopes match API methods actually used in code
- Hook registrations are detected

### Activation gate (runtime hard block)

Activation is blocked when contract requirements are not met. In particular:

- Missing plugin files (`manifest.json` / entrypoint) on disk
- Missing required config fields from schema when no config value and no env override is present
- Payment plugins (`payments:write`) missing required flow hooks:
  - `checkout.redirect_url.resolve` (or legacy `payment.redirect_url.resolve`)
  - `plugin.flow.start` (or legacy `payment.provider.start`)
  - `plugin.flow.return` (or legacy `payment.provider.return`)

This ensures uploaded plugins are runnable by contract before they can be activated.
