from __future__ import annotations

from datetime import datetime

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.utils.translation import gettext as _

from apps.utils.tasks import send_email_task
from apps.web.models import SiteSettings, SystemSettings

from .models import Order


def _send_email_sync(*, subject: str, body: str, from_email: str, recipient_list: list[str], html_message: str = "") -> None:
    """Send email synchronously using the configured Django backend."""

    connection = get_connection()
    message = EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email=from_email,
        to=recipient_list,
        connection=connection,
    )
    if html_message:
        message.attach_alternative(html_message, "text/html")
    message.send()


def _build_and_send_order_confirmation_email(*, order_id: int, base_url: str, tracking_url: str, payment_url: str = "") -> None:
    """Prepare and send order confirmation email using configured dispatch mode."""

    try:
        order = Order.objects.prefetch_related("lines__product__images").get(pk=order_id)
    except Order.DoesNotExist:
        return

    to_email = (order.email or "").strip()
    if not to_email or not tracking_url:
        return

    lines = list(order.lines.select_related("product").prefetch_related("product__images").all())

    branding = _get_site_branding(base_url=base_url)
    currency_symbol = branding.get("currency_symbol") or ""
    if not currency_symbol:
        currency_symbol = SiteSettings.CURRENCY_SYMBOLS.get(order.currency or "", order.currency or "")

    cta_url = payment_url or tracking_url
    cta_text = str(_("Pay for your order")) if payment_url else str(_("Track your order"))

    context = {
        **branding,
        "order": order,
        "lines": lines,
        "tracking_url": tracking_url,
        "payment_url": payment_url,
        "cta_url": cta_url,
        "cta_text": cta_text,
        "currency_symbol": currency_symbol,
    }

    subject = render_to_string("orders/email/order_confirmation_subject.txt", context).strip().replace("\n", " ")
    body = render_to_string("orders/email/order_confirmation_message.txt", context)
    html_message = render_to_string("orders/email/order_confirmation_message.html", context)

    email_kwargs = {
        "subject": str(subject),
        "body": str(body),
        "from_email": _get_from_email(),
        "recipient_list": [to_email],
        "html_message": str(html_message),
    }

    use_celery = bool(getattr(settings, "ORDER_EMAIL_USE_CELERY", not settings.DEBUG))
    if use_celery:
        try:
            send_email_task.apply_async(kwargs=email_kwargs, retry=False)
            return
        except Exception:
            return

    try:
        _send_email_sync(**email_kwargs)
    except Exception:
        return


def _get_site_branding(*, base_url: str) -> dict:
    """Return shared email branding context (store_name/site_url/logo_url/year)."""

    store_name = settings.PROJECT_METADATA.get("NAME", "Store")
    site_url = base_url or ""
    logo_url = ""
    currency_symbol = ""

    try:
        site_settings = SiteSettings.get_settings()
        store_name = (site_settings.store_name or "").strip() or store_name
        currency_symbol = getattr(site_settings, "currency_symbol", "") or ""
        logo_url = getattr(site_settings, "logo_url", "") or ""
    except Exception:
        pass

    # Email clients do not reliably support SVG images.
    if logo_url and str(logo_url).lower().endswith(".svg"):
        logo_url = ""

    # Make logo URL absolute (relative URLs do not work in email clients).
    if logo_url and site_url and not str(logo_url).startswith(("http://", "https://")):
        if not str(logo_url).startswith("/"):
            logo_url = f"/{logo_url}"
        logo_url = f"{site_url.rstrip('/')}{logo_url}"

    return {
        "store_name": store_name,
        "site_url": site_url,
        "logo_url": logo_url,
        "current_year": datetime.now().year,
        "currency_symbol": currency_symbol,
    }


def _get_from_email() -> str:
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "")
    try:
        system_settings = SystemSettings.get_settings()
        if system_settings.smtp_default_from_email:
            from_email = system_settings.smtp_default_from_email
    except Exception:
        pass
    return from_email


def send_order_confirmation_email(
    *,
    order: Order,
    base_url: str,
    tracking_url: str,
    payment_url: str = "",
) -> None:
    """Dispatch order confirmation email.

    Local/dev defaults to sync (ORDER_EMAIL_USE_CELERY=False) so emails are
    visible immediately without worker dependencies. Non-local defaults to
    async through Celery.
    """
    to_email = (order.email or "").strip()
    if not to_email or not tracking_url:
        return

    use_celery = bool(getattr(settings, "ORDER_EMAIL_USE_CELERY", not settings.DEBUG))
    if not use_celery:
        _build_and_send_order_confirmation_email(
            order_id=order.pk,
            base_url=base_url,
            tracking_url=tracking_url,
            payment_url=payment_url or "",
        )
        return

    try:
        _send_order_confirmation_email_task.apply_async(
            kwargs={
                "order_id": order.pk,
                "base_url": base_url,
                "tracking_url": tracking_url,
                "payment_url": payment_url or "",
            },
            retry=False,
        )
    except Exception:
        return


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def _send_order_confirmation_email_task(self, order_id, base_url, tracking_url, payment_url=""):
    """Celery task wrapper around order confirmation email preparation/sending."""

    _build_and_send_order_confirmation_email(
        order_id=order_id,
        base_url=base_url,
        tracking_url=tracking_url,
        payment_url=payment_url,
    )
