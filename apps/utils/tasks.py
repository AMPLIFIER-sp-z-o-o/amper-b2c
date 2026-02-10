"""
Celery tasks for non-blocking email dispatch.
"""

import logging

from celery import shared_task
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_email_task(self, subject, body, from_email, recipient_list, html_message=None):
    """
    Dispatch an email through the ``DatabaseSmtpBackend``.

    All arguments must be JSON-serializable so Celery can enqueue them.
    Retries up to 3 times with exponential back-off on SMTP errors.
    """
    from apps.utils.email_backend import DatabaseSmtpBackend

    try:
        backend = DatabaseSmtpBackend()
        msg = EmailMultiAlternatives(
            subject=subject,
            body=body,
            from_email=from_email,
            to=recipient_list,
            connection=backend,
        )
        if html_message:
            msg.attach_alternative(html_message, "text/html")
        msg.send()
        logger.info("Email sent to %s (subject=%r)", recipient_list, subject)
    except Exception as exc:
        logger.warning(
            "Email send failed (attempt %d/%d): %s",
            self.request.retries + 1,
            self.max_retries + 1,
            exc,
        )
        try:
            raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            logger.error(
                "Max retries exceeded for email to %s (subject=%r). Giving up.",
                recipient_list,
                subject,
            )
