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
from apps.cart.checkout import CHECKOUT_SESSION_KEY
from apps.cart.services import _annotate_lines_with_stock_issues, _clear_cart_id, _get_cart_from_request
from apps.utils.tasks import send_email_task
from apps.web.models import SiteSettings

from .models import Order, OrderLine


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

    cart = _get_cart_from_request(request, cart_id)
    if not cart:
        response = redirect("cart:cart_page")
        return _clear_cart_id(request, response=response)

    lines = list(cart.lines.select_related("product").all())
    stock_issues = _annotate_lines_with_stock_issues(lines)
    if stock_issues:
        messages.error(request, _("Some items in your cart are no longer available. Please review your cart."))
        return redirect("cart:cart_page")

    details = request.session.get(CHECKOUT_SESSION_KEY) or {}
    required = [
        "first_name",
        "last_name",
        "email",
        "phone_country_code",
        "phone_number",
        "shipping_city",
        "shipping_postal_code",
        "shipping_street",
        "shipping_building_number",
    ]
    if any(not details.get(k) for k in required):
        messages.error(request, _("Please complete your delivery details before placing the order."))
        return redirect("cart:checkout_page")

    # Delivery and payment must be selected before placing the order.
    if not cart.delivery_method:
        messages.error(request, _("Please select a delivery method before placing the order."))
        return redirect("cart:checkout_page")
    if not cart.payment_method:
        messages.error(request, _("Please select a payment method before placing the order."))
        return redirect("cart:checkout_page")

    # Store-wide VAT rate.
    try:
        cart.tax_rate_percent = Decimal(SiteSettings.get_settings().vat_rate_percent or 0).quantize(Decimal("0.01"))
    except Exception:
        cart.tax_rate_percent = Decimal("0.00")
    cart.recalculate()

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

    first_name = (details.get("first_name") or "").strip()
    last_name = (details.get("last_name") or "").strip()
    full_name = (" ".join([p for p in (first_name, last_name) if p])).strip()

    phone = (" ".join([
        (details.get("phone_country_code") or "").strip(),
        (details.get("phone_number") or "").strip(),
    ])).strip()

    street = (details.get("shipping_street") or "").strip()
    building = (details.get("shipping_building_number") or "").strip()
    apt = (details.get("shipping_apartment_number") or "").strip()
    address_line = f"{street} {building}".strip()
    if apt:
        address_line = f"{address_line}/{apt}".strip()

    with transaction.atomic():
        order = Order.objects.create(
            customer=request.user if request.user.is_authenticated else None,
            tracking_token=tracking_token,
            email=details.get("email", ""),
            full_name=full_name,
            company=(details.get("company") or "").strip(),
            phone=phone,
            shipping_postal_code=(details.get("shipping_postal_code") or "").strip(),
            shipping_city=details.get("shipping_city", ""),
            shipping_address=address_line,
            delivery_method_name=(cart.delivery_method.name if cart.delivery_method else ""),
            payment_method_name=(cart.payment_method.name if cart.payment_method else ""),
            subtotal=cart.subtotal,
            tax_rate_percent=cart.tax_rate_percent,
            tax_total=cart.tax_total,
            discount_total=cart.discount_total,
            coupon_code=cart.coupon_code,
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
