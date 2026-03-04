from __future__ import annotations

import hashlib
import json

from django.contrib import messages
from django.db import IntegrityError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.orders.models import Order
from apps.plugins.engine.loader import sync_and_load_plugins
from apps.plugins.engine.registry import registry
from apps.plugins.hook_names import (
    LEGACY_PLUGIN_FLOW_RETURN,
    LEGACY_PLUGIN_FLOW_START,
    LEGACY_PLUGIN_WEBHOOK_RECEIVED,
    PLUGIN_FLOW_RETURN,
    PLUGIN_FLOW_START,
    PLUGIN_WEBHOOK_RECEIVED,
)
from apps.plugins.models import Plugin, PluginWebhookEvent, PluginWebhookEventStatus
from apps.plugins.tasks import process_plugin_webhook_event


def _default_start_result() -> dict:
    return {
        "success": False,
        "redirect_url": "",
        "message": str(_("Payment provider is unavailable.")),
    }


def _default_return_result(order: Order) -> dict:
    return {
        "success": False,
        "redirect_url": reverse("orders:summary", kwargs={"token": order.tracking_token}),
        "message": str(_("Payment pending confirmation.")),
        "level": "info",
    }


def _push_message(request: HttpRequest, level: str, message: str) -> None:
    normalized = str(level or "").strip().lower()
    if normalized == "success":
        messages.success(request, message)
        return
    if normalized == "warning":
        messages.warning(request, message)
        return
    if normalized == "error":
        messages.error(request, message)
        return
    messages.info(request, message)


def _ensure_flow_filters_loaded() -> None:
    # Guard against stale/empty in-memory registry in long-running processes.
    if registry.has_filter(PLUGIN_FLOW_START) or registry.has_filter(LEGACY_PLUGIN_FLOW_START):
        return
    sync_and_load_plugins()


@require_GET
def provider_flow_start(request: HttpRequest, plugin_slug: str, token: str):
    order = get_object_or_404(Order, tracking_token=token)
    _ensure_flow_filters_loaded()
    normalized_plugin_slug = str(plugin_slug or "").strip()
    hook_name = PLUGIN_FLOW_START if registry.has_filter(PLUGIN_FLOW_START) else LEGACY_PLUGIN_FLOW_START
    result = registry.apply_filter_for_plugin(
        hook_name,
        _default_start_result(),
        target_plugin_slug=normalized_plugin_slug,
        request=request,
        order=order,
    )

    result = result if isinstance(result, dict) else _default_start_result()
    fallback_pay_url = (
        f"{reverse('orders:pay', kwargs={'token': order.tracking_token})}?provider_error=1"
    )
    if not bool(result.get("success")):
        messages.error(request, str(result.get("message") or _("Payment initialization failed.")))
        return redirect(fallback_pay_url)

    redirect_url = str(result.get("redirect_url") or "").strip()
    if not redirect_url:
        messages.error(request, str(_("Payment provider did not return a redirect URL.")))
        return redirect(fallback_pay_url)

    return redirect(redirect_url)


@require_GET
def provider_flow_return(request: HttpRequest, plugin_slug: str, token: str):
    order = get_object_or_404(Order, tracking_token=token)
    _ensure_flow_filters_loaded()
    normalized_plugin_slug = str(plugin_slug or "").strip()
    hook_name = PLUGIN_FLOW_RETURN if registry.has_filter(PLUGIN_FLOW_RETURN) else LEGACY_PLUGIN_FLOW_RETURN
    result = registry.apply_filter_for_plugin(
        hook_name,
        _default_return_result(order),
        target_plugin_slug=normalized_plugin_slug,
        request=request,
        order=order,
    )

    result = result if isinstance(result, dict) else _default_return_result(order)
    message_text = str(result.get("message") or "").strip()
    if message_text:
        _push_message(request, str(result.get("level") or "info"), message_text)

    redirect_url = str(result.get("redirect_url") or "").strip()
    if not redirect_url:
        redirect_url = reverse("orders:summary", kwargs={"token": order.tracking_token})
    return redirect(redirect_url)


@csrf_exempt
@require_POST
def plugin_webhook(request: HttpRequest, plugin_slug: str) -> HttpResponse:
    slug = str(plugin_slug or "").strip()
    plugin = Plugin.objects.filter(slug=slug).first()
    if not plugin:
        return JsonResponse({"success": False, "message": str(_("Plugin is not installed."))}, status=404)

    raw_body = request.body or b""
    content_type = (request.headers.get("Content-Type") or "").lower()
    if "application/json" in content_type:
        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except Exception:
            return JsonResponse({"success": False, "message": str(_("Invalid JSON payload."))}, status=400)
    else:
        payload = {key: value for key, value in request.POST.items()}

    provider_event_id = str(
        payload.get("event_id") or payload.get("eventId") or payload.get("id") or payload.get("orderId") or ""
    ).strip()

    if raw_body:
        payload_hash = hashlib.sha256(raw_body).hexdigest()
    else:
        canonical_payload = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        payload_hash = hashlib.sha256(canonical_payload).hexdigest()

    duplicate = PluginWebhookEvent.objects.filter(plugin=plugin, payload_hash=payload_hash).first()
    if duplicate:
        return JsonResponse({"success": True, "duplicate": True})

    if provider_event_id and PluginWebhookEvent.objects.filter(
        plugin=plugin,
        provider_event_id=provider_event_id,
    ).exists():
        return JsonResponse({"success": True, "duplicate": True})

    explicit_hook = str(payload.get("hook_name") or "").strip()
    hook_name = explicit_hook
    if not hook_name:
        hook_name = (
            PLUGIN_WEBHOOK_RECEIVED
            if registry.has_async_action(PLUGIN_WEBHOOK_RECEIVED)
            else LEGACY_PLUGIN_WEBHOOK_RECEIVED
        )
    try:
        event = PluginWebhookEvent.objects.create(
            plugin=plugin,
            provider_event_id=provider_event_id,
            payload_hash=payload_hash,
            hook_name=hook_name,
            status=PluginWebhookEventStatus.PENDING,
            payload=payload,
        )
    except IntegrityError:
        # Concurrent callbacks can hit uniqueness constraints at the same time.
        return JsonResponse({"success": True, "duplicate": True})

    process_plugin_webhook_event.delay(event.id)
    return JsonResponse({"success": True, "queued": True, "event_id": event.id})


# Backward-compatible view aliases for older URL imports.
payment_provider_start = provider_flow_start
payment_provider_return = provider_flow_return
