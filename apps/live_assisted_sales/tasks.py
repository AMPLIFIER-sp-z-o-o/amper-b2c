"""Celery tasks for the Live Assisted Sales durable event outbox."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def deliver_outbox_event(self, outbox_id):
    """Deliver a single outbox event (enqueued when a durable event is produced)."""
    from .client import deliver_outbox_row

    deliver_outbox_row(outbox_id)


@shared_task
def relay_pending_outbox_task():
    """Periodic sweep: deliver any outbox events the fast path didn't confirm."""
    from .client import relay_pending_outbox

    return relay_pending_outbox()
