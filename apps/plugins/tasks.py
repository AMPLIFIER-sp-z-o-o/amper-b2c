from __future__ import annotations

from celery import shared_task
from django.utils import timezone

from apps.plugins.engine.registry import registry
from apps.plugins.models import PluginWebhookEvent, PluginWebhookEventStatus


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def run_async_plugin_action(self, hook_name: str, payload: dict, correlation_id: str = ""):
    registry.execute_async_action_now(hook_name=hook_name, payload=payload, correlation_id=correlation_id)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_plugin_webhook_event(self, event_id: int):
    event = PluginWebhookEvent.objects.filter(id=event_id).select_related("plugin").first()
    if not event:
        return

    try:
        summary = registry.execute_async_action_now(
            hook_name=event.hook_name,
            payload={"event_id": event.id, "plugin_slug": event.plugin.slug, "payload": event.payload},
            correlation_id=str(event.id),
        )

        if not isinstance(summary, dict):
            summary = {}

        failed_callbacks = int(summary.get("failed") or 0)
        executed_callbacks = int(summary.get("executed") or 0)
        errors = [str(item).strip() for item in (summary.get("errors") or []) if str(item).strip()]

        if failed_callbacks > 0:
            event.status = PluginWebhookEventStatus.FAILED
            event.processed_at = None
            event.error_message = "; ".join(errors)[:1000] if errors else "Webhook callback execution failed."
            event.save(update_fields=["status", "processed_at", "error_message", "updated_at"])
            return

        if executed_callbacks <= 0:
            event.status = PluginWebhookEventStatus.FAILED
            event.processed_at = None
            event.error_message = f"No async handlers registered for hook '{event.hook_name}'."
            event.save(update_fields=["status", "processed_at", "error_message", "updated_at"])
            return

        event.status = PluginWebhookEventStatus.PROCESSED
        event.processed_at = timezone.now()
        event.error_message = ""
        event.save(update_fields=["status", "processed_at", "error_message", "updated_at"])
    except Exception as exc:  # pragma: no cover - defensive
        event.status = PluginWebhookEventStatus.FAILED
        event.error_message = str(exc)
        event.save(update_fields=["status", "error_message", "updated_at"])
        raise
