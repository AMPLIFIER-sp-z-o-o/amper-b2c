from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from apps.cart.models import Cart
from apps.cart.views import _annotate_lines_with_stock_issues
from apps.utils.tasks import send_email_task
from apps.web.models import SiteSettings

from .models import Order, OrderLine


CHECKOUT_SESSION_KEY = "checkout_details"


def _get_site_base_url(request: HttpRequest) -> str:
    try:
        site_url = (SiteSettings.get_settings().site_url or "").strip().rstrip("/")
    except Exception:
        site_url = ""
    if site_url:
        return site_url
    try:
        return request.build_absolute_uri("/").rstrip("/")
    except Exception:
        return ""


def _send_tracking_email(*, to_email: str, tracking_url: str, order_id: int | None) -> None:
    if not to_email or not tracking_url:
        return

    subject = _("Your order tracking link")
    body = _("You can track your order here: {url}").format(url=tracking_url)

    try:
        send_email_task.apply_async(
            kwargs={
                "subject": str(subject),
                "body": str(body),
                "from_email": settings.DEFAULT_FROM_EMAIL,
                "recipient_list": [to_email],
                "html_message": None,
            },
            retry=False,
        )
    except Exception:
        # Email is best-effort; do not block order placement.
        return


@require_POST
def place_order(request: HttpRequest) -> HttpResponse:
    cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")
    if not cart_id:
        return redirect("cart:cart_page")

    cart = get_object_or_404(Cart, id=cart_id)

    lines = list(cart.lines.select_related("product").all())
    stock_issues = _annotate_lines_with_stock_issues(lines)
    if stock_issues:
        messages.error(request, _("Some items in your cart are no longer available. Please review your cart."))
        return redirect("cart:cart_page")

    details = request.session.get(CHECKOUT_SESSION_KEY) or {}
    required = ["full_name", "email", "shipping_country", "shipping_city", "shipping_address"]
    if any(not details.get(k) for k in required):
        messages.error(request, _("Please complete your delivery details before placing the order."))
        return redirect("cart:checkout_page")

    tracking_token = Order.generate_tracking_token()

    # Ensure token uniqueness (very low collision probability, but guard anyway)
    while Order.objects.filter(tracking_token=tracking_token).exists():
        tracking_token = Order.generate_tracking_token()

    delivery_cost = cart.delivery_method.get_cost_for_cart(cart.subtotal) if cart.delivery_method else Decimal("0.00")
    payment_cost = (
        Decimal(cart.payment_method.additional_fees)
        if cart.payment_method and cart.payment_method.additional_fees
        else Decimal("0.00")
    )

    try:
        site_settings = SiteSettings.get_settings()
        currency = site_settings.currency or ""
    except Exception:
        currency = ""

    with transaction.atomic():
        order = Order.objects.create(
            customer=request.user if request.user.is_authenticated else None,
            tracking_token=tracking_token,
            email=details.get("email", ""),
            full_name=details.get("full_name", ""),
            phone=details.get("phone", ""),
            shipping_country=details.get("shipping_country", ""),
            shipping_city=details.get("shipping_city", ""),
            shipping_address=details.get("shipping_address", ""),
            delivery_method_name=(cart.delivery_method.name if cart.delivery_method else ""),
            payment_method_name=(cart.payment_method.name if cart.payment_method else ""),
            subtotal=cart.subtotal,
            delivery_cost=delivery_cost,
            payment_cost=payment_cost,
            total=cart.total,
            currency=currency,
        )

        for line in lines:
            OrderLine.objects.create(
                order=order,
                product=line.product,
                quantity=line.quantity,
                unit_price=line.price,
                line_total=line.subtotal,
            )

        # Clear cart after successful order placement
        cart.lines.all().delete()
        cart.delete()

    request.session.pop("cart_id", None)
    request.session.pop(CHECKOUT_SESSION_KEY, None)

    base_url = _get_site_base_url(request)
    tracking_path = order.get_tracking_url()
    tracking_url = f"{base_url}{tracking_path}" if base_url else tracking_path

    _send_tracking_email(to_email=order.email, tracking_url=tracking_url, order_id=order.id)

    messages.success(request, _("Order placed. Save your tracking link."))

    response = redirect("orders:track", token=order.tracking_token)
    # Clear stale cookie cart_id (session takes precedence but cookie can confuse other flows)
    response.delete_cookie("cart_id")
    return response


@require_GET
def track_order(request: HttpRequest, token: str) -> HttpResponse:
    if not token:
        raise Http404

    order = get_object_or_404(Order.objects.prefetch_related("lines__product"), tracking_token=token)

    if order.email_verified_at is None:
        try:
            Order.objects.filter(pk=order.pk, email_verified_at__isnull=True).update(email_verified_at=timezone.now())
            order.email_verified_at = timezone.now()
        except Exception:
            pass

    return render(
        request,
        "orders/order_tracking.html",
        {
            "order": order,
            "lines": order.lines.all(),
            "now": timezone.now(),
        },
    )
