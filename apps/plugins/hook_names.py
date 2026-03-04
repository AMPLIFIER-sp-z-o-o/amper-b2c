from __future__ import annotations

# Canonical provider-agnostic hook names.
CHECKOUT_REDIRECT_URL_RESOLVE = "checkout.redirect_url.resolve"
PLUGIN_FLOW_START = "plugin.flow.start"
PLUGIN_FLOW_RETURN = "plugin.flow.return"
PLUGIN_WEBHOOK_RECEIVED = "plugin.webhook.received"
PLUGIN_TEST_CONNECTION = "plugin.test_connection"

# Checkout/order lifecycle hooks.
PAYMENT_METHODS_LOAD = "payment.methods.load"
DELIVERY_METHODS_LOAD = "delivery.methods.load"
CHECKOUT_RENDER = "checkout.render"
ORDER_CREATED = "order.created"
ORDER_STATUS_CHANGED = "order.status.changed"
ORDER_SHIPPED = "order.shipped"
NOTIFICATION_EMAIL_BEFORE_SEND = "notification.email.before_send"

# Backward-compatible legacy aliases.
LEGACY_CHECKOUT_REDIRECT_URL_RESOLVE = "payment.redirect_url.resolve"
LEGACY_PLUGIN_FLOW_START = "payment.provider.start"
LEGACY_PLUGIN_FLOW_RETURN = "payment.provider.return"
LEGACY_PLUGIN_WEBHOOK_RECEIVED = "payment.callback.received"
