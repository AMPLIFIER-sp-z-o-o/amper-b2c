from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import DecimalField, F, Value
from django.db.models.expressions import ExpressionWrapper
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from apps.cart.checkout import clear_checkout_session, get_checkout_state
from apps.cart.models import Cart, CartLine
from apps.cart.services import (
    _annotate_lines_with_stock_issues,
    _clear_cart_id,
    _get_cart_from_request,
    ensure_cart_methods_active,
    refresh_cart_totals_from_db,
)
from apps.catalog.models import Product, ProductStatus
from apps.utils.tasks import send_email_task  # noqa: F401
from apps.web.models import SiteSettings

from .emails import send_order_confirmation_email
from .models import Coupon, Order, OrderLine, OrderStatus


ORDER_PLACED_MESSAGE_TOKEN_SESSION_KEY = "orders_order_placed_message_token"


@require_GET
def payment_gateway_placeholder(request: HttpRequest, token: str) -> HttpResponse:
    if not token:
        raise Http404

    order = get_object_or_404(
        Order.objects.prefetch_related("lines__product", "lines__product__images"), tracking_token=token
    )

    return render(
        request,
        "orders/payment_gateway_placeholder.html",
        {
            "order": order,
            "lines": order.lines.all(),
            "now": timezone.now(),
        },
    )


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


@require_POST
def place_order(request: HttpRequest) -> HttpResponse:
    cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")
    if not cart_id:
        return redirect("cart:cart_page")

    cart = _get_cart_from_request(request, cart_id)
    if not cart:
        response = redirect("cart:cart_page")
        return _clear_cart_id(request, response=response)

    # Delivery/payment can become invalid (disabled) after user selected them.
    methods_changed = ensure_cart_methods_active(cart)
    if methods_changed.get("delivery_method_cleared") or methods_changed.get("payment_method_cleared"):
        messages.error(request, _("Please re-select your delivery and payment methods."))
        return redirect("cart:checkout_page")

    # Re-price and recompute totals/discounts from current DB state.
    refresh_result = refresh_cart_totals_from_db(cart)
    # If the coupon was cleared during refresh, the user must review and accept the new total.
    if refresh_result.get("coupon_cleared"):
        messages.error(request, _("Your promo code is no longer valid. We've updated your order total."))
        return redirect("cart:summary_page")

    lines = list(cart.lines.select_related("product").all())
    stock_issues = _annotate_lines_with_stock_issues(lines)
    if stock_issues:
        messages.error(request, _("Some items in your cart are no longer available. Please review your cart."))
        return redirect("cart:cart_page")

    state = get_checkout_state(request)
    if state.expired:
        messages.error(request, _("Your checkout session expired. Please enter your delivery details again."))
        return redirect("cart:checkout_page")

    details = state.active_details
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

    # Some payment methods require a follow-up "payment" step after the order is placed
    # (e.g. bank transfer instructions / external gateway). For now we route such methods
    # to an internal placeholder gateway page.
    should_redirect_to_payment = bool(cart.payment_method and cart.payment_method.default_payment_time is not None)

    # Final safety: re-calc totals right before persisting the order.
    cart.recalculate()

    tracking_token = Order.generate_tracking_token()

    # Ensure token uniqueness (very low collision probability, but guard anyway)
    while Order.objects.filter(tracking_token=tracking_token).exists():
        tracking_token = Order.generate_tracking_token()

    delivery_cost = cart.delivery_method.get_cost_for_cart(cart.subtotal) if cart.delivery_method else Decimal("0.00")

    try:
        site_settings = SiteSettings.get_settings()
        currency = site_settings.currency or ""
        base_url = (site_settings.site_url or "").strip().rstrip("/") or request.build_absolute_uri("/").rstrip("/")
    except Exception:
        currency = ""
        base_url = request.build_absolute_uri("/").rstrip("/")

    first_name = (details.get("first_name") or "").strip()
    last_name = (details.get("last_name") or "").strip()
    full_name = (" ".join([p for p in (first_name, last_name) if p])).strip()

    phone = (
        " ".join(
            [
                (details.get("phone_country_code") or "").strip(),
                (details.get("phone_number") or "").strip(),
            ]
        )
    ).strip()

    street = (details.get("shipping_street") or "").strip()
    building = (details.get("shipping_building_number") or "").strip()
    apt = (details.get("shipping_apartment_number") or "").strip()
    address_line = f"{street} {building}".strip()
    if apt:
        address_line = f"{address_line}/{apt}".strip()

    with transaction.atomic():
        # ---- Atomic stock + coupon guards ----
        # Two concurrent checkouts can both pass the earlier read-only stock/coupon validation.
        # We must lock and re-validate inside the transaction to avoid overselling and
        # exceeding coupon usage limits.

        # Aggregate required quantities per product.
        required_by_product_id: dict[int, int] = {}
        revenue_by_product_id: dict[int, Decimal] = {}
        for line in lines:
            quantity = int(line.quantity or 0)
            if quantity <= 0:
                continue

            required_by_product_id[line.product_id] = required_by_product_id.get(line.product_id, 0) + quantity
            revenue_by_product_id[line.product_id] = revenue_by_product_id.get(line.product_id, Decimal("0.00")) + (
                Decimal(line.subtotal or 0).quantize(Decimal("0.01"))
            )

        # Lock products in a stable order to minimize deadlock risk.
        locked_products = list(
            Product.objects.select_for_update().filter(id__in=list(required_by_product_id.keys())).order_by("id")
        )

        # Validate stock/availability again under the lock.
        for product in locked_products:
            required_qty = required_by_product_id.get(product.id, 0)
            if required_qty <= 0:
                continue

            if product.status != ProductStatus.ACTIVE or int(product.stock or 0) <= 0:
                messages.error(
                    request,
                    _("Some items in your cart are no longer available. Please review your cart."),
                )
                return redirect("cart:cart_page")

            if int(product.stock or 0) < required_qty:
                messages.error(
                    request,
                    _("Some items in your cart are no longer available. Please review your cart."),
                )
                return redirect("cart:cart_page")

        # Lock + validate coupon usage limit (if any) under the lock.
        locked_coupon: Coupon | None = None
        coupon_code = (getattr(cart, "coupon_code", "") or "").strip()
        if coupon_code:
            now = timezone.now()
            locked_coupon = Coupon.objects.select_for_update().filter(is_active=True, code__iexact=coupon_code).first()

            coupon_is_valid = True
            if (
                not locked_coupon
                or locked_coupon.valid_from
                and now < locked_coupon.valid_from
                or locked_coupon.valid_to
                and now > locked_coupon.valid_to
                or locked_coupon.usage_limit is not None
                and locked_coupon.used_count >= locked_coupon.usage_limit
                or locked_coupon.min_subtotal is not None
                and cart.subtotal < locked_coupon.min_subtotal
            ):
                coupon_is_valid = False

            if not coupon_is_valid:
                # Clear coupon and ask the user to review updated totals.
                cart.coupon_code = ""
                cart.discount_total = Decimal("0.00")
                cart.recalculate()
                messages.error(
                    request,
                    _("Your promo code is no longer valid. We've updated your order total."),
                )
                return redirect("cart:summary_page")

        # Apply updates only after all validations pass.
        for product in locked_products:
            required_qty = required_by_product_id.get(product.id, 0)
            if required_qty <= 0:
                continue

            revenue_delta = (revenue_by_product_id.get(product.id) or Decimal("0.00")).quantize(Decimal("0.01"))

            # Keep these counters consistent under concurrency.
            Product.objects.filter(pk=product.pk).update(
                stock=F("stock") - required_qty,
                sales_total=F("sales_total") + required_qty,
                revenue_total=ExpressionWrapper(
                    F("revenue_total") + Value(revenue_delta),
                    output_field=DecimalField(max_digits=15, decimal_places=2),
                ),
            )

        if locked_coupon is not None:
            Coupon.objects.filter(pk=locked_coupon.pk).update(used_count=F("used_count") + 1)

        order = Order.objects.create(
            customer=request.user if request.user.is_authenticated else None,
            tracking_token=tracking_token,
            email=details.get("email", ""),
            full_name=full_name,
            phone=phone,
            shipping_postal_code=(details.get("shipping_postal_code") or "").strip(),
            shipping_city=details.get("shipping_city", ""),
            shipping_address=address_line,
            delivery_method_name=(cart.delivery_method.name if cart.delivery_method else ""),
            payment_method_name=(cart.payment_method.name if cart.payment_method else ""),
            subtotal=cart.subtotal,
            discount_total=cart.discount_total,
            coupon_code=cart.coupon_code,
            delivery_cost=delivery_cost,
            total=cart.total,
            currency=currency,
        )

        OrderLine.objects.bulk_create(
            [
                OrderLine(
                    order=order,
                    product=line.product,
                    quantity=line.quantity,
                    unit_price=line.price,
                    line_total=line.subtotal,
                )
                for line in lines
            ]
        )

        # Clear cart after successful order placement
        cart.delete()

    request.session.pop("cart_id", None)
    clear_checkout_session(request)

    tracking_path = order.get_tracking_url()
    tracking_url = f"{base_url}{tracking_path}" if base_url else tracking_path

    payment_url = ""
    if should_redirect_to_payment:
        payment_path = reverse("orders:pay", kwargs={"token": order.tracking_token})
        payment_url = f"{base_url}{payment_path}" if base_url else payment_path

    send_order_confirmation_email(
        order=order,
        base_url=base_url,
        tracking_url=tracking_url,
        payment_url=payment_url,
    )

    # Defer the success toast until the user reaches order summary.
    # This prevents consuming the message on the intermediate payment page.
    request.session[ORDER_PLACED_MESSAGE_TOKEN_SESSION_KEY] = order.tracking_token

    is_htmx = request.headers.get("HX-Request") == "true"
    if should_redirect_to_payment and is_htmx:
        # For HTMX requests use HX-Redirect so the browser navigates to the payment
        # page directly without HTMX pre-fetching it first. Pre-fetching would consume
        # the Django session message before the browser ever renders the page, causing
        # the "Order placed" toast to silently disappear.
        payment_path = reverse("orders:pay", kwargs={"token": order.tracking_token})
        response = HttpResponse(status=200)
        response["HX-Redirect"] = payment_path
    else:
        response = (
            redirect("orders:pay", token=order.tracking_token)
            if should_redirect_to_payment
            else redirect("orders:summary", token=order.tracking_token)
        )
    # Clear stale cookie cart_id (session takes precedence but cookie can confuse other flows)
    response.delete_cookie("cart_id")
    return response


@require_GET
def order_summary(request: HttpRequest, token: str) -> HttpResponse:
    if not token:
        raise Http404

    order = get_object_or_404(
        Order.objects.prefetch_related("lines__product", "lines__product__images"), tracking_token=token
    )

    placed_token = request.session.pop(ORDER_PLACED_MESSAGE_TOKEN_SESSION_KEY, None)
    if placed_token == token:
        messages.success(request, _("Order placed."))

    if order.email_verified_at is None:
        try:
            Order.objects.filter(pk=order.pk, email_verified_at__isnull=True).update(email_verified_at=timezone.now())
            order.email_verified_at = timezone.now()
        except Exception:
            pass

    user_order_number = Order.objects.filter(email__iexact=order.email, created_at__lte=order.created_at).count()
    reorder_mode = request.GET.get("reorder") == "1"

    return render(
        request,
        "orders/order_summary.html",
        {
            "order": order,
            "lines": order.lines.all(),
            "now": timezone.now(),
            "user_order_number": user_order_number,
            "reorder_mode": reorder_mode,
        },
    )


@require_POST
def buy_again(request: HttpRequest, token: str) -> HttpResponse:
    """Re-add all products from a past order to the current cart."""
    if not token:
        raise Http404

    order = get_object_or_404(Order.objects.prefetch_related("lines__product"), tracking_token=token)

    lines = list(order.lines.select_related("product").all())
    if not lines:
        messages.error(request, _("This order has no items."))
        return redirect("orders:summary", token=token)

    # Resolve or create cart — mirrors the logic in add_to_cart.
    cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")
    cart = None
    if cart_id:
        cart = Cart.objects.filter(id=cart_id).first()

    if cart and cart.customer_id:
        if request.user.is_authenticated and cart.customer_id == request.user.id:
            pass
        elif request.user.is_authenticated:
            cart = Cart.objects.filter(customer=request.user).order_by("-id").first()
        else:
            cart = None

    if not cart and request.user.is_authenticated:
        cart = Cart.objects.filter(customer=request.user).order_by("-id").first()

    if not cart:
        cart = Cart.objects.create(customer=request.user if request.user.is_authenticated else None)

    added_count = 0
    skipped_count = 0

    with transaction.atomic():
        for line in lines:
            product = line.product
            if not product or product.status != ProductStatus.ACTIVE or int(product.stock or 0) <= 0:
                skipped_count += 1
                continue

            requested_quantity = int(line.quantity or 1)
            if requested_quantity <= 0:
                skipped_count += 1
                continue

            cart_line = CartLine.objects.select_for_update().filter(cart=cart, product=product).first()
            current_quantity = int(cart_line.quantity or 0) if cart_line else 0
            remaining_stock = max(int(product.stock or 0) - current_quantity, 0)
            quantity_to_add = min(requested_quantity, remaining_stock)

            if quantity_to_add <= 0:
                skipped_count += 1
                continue

            if cart_line is None:
                CartLine.objects.create(cart=cart, product=product, quantity=quantity_to_add, price=product.price)
            else:
                cart_line.quantity = current_quantity + quantity_to_add
                cart_line.price = product.price
                cart_line.save(update_fields=["quantity", "price"])

            if quantity_to_add < requested_quantity:
                skipped_count += 1

            added_count += 1

    if added_count > 0:
        refresh_cart_totals_from_db(cart)
        request.session["cart_id"] = cart.id

    if added_count == 0:
        messages.error(request, _("None of the products from this order are currently available."))
        return redirect("orders:summary", token=token)

    if skipped_count > 0:
        messages.warning(
            request,
            _("Some products from this order are unavailable and were skipped."),
        )
    else:
        messages.success(request, _("All products added to your cart."))

    response = redirect("cart:cart_page")
    response.set_cookie("cart_id", cart.id, max_age=60 * 60 * 24 * 10)
    return response


@require_GET
def track_order_legacy(request: HttpRequest, token: str) -> HttpResponse:
    return redirect("orders:summary", token=token)


@require_POST
def post_payment_mock(request: HttpRequest, token: str) -> HttpResponse:
    """
    Mock payment endpoint.
    Simulates a successful payment response by updating the order status and sending the email.
    """
    if not token:
        raise Http404

    order = get_object_or_404(
        Order.objects.prefetch_related("lines__product", "lines__product__images"), tracking_token=token
    )

    with transaction.atomic():
        order.status = OrderStatus.PAID
        order.save(update_fields=["status", "updated_at"])

    base_url = _get_site_base_url(request)
    tracking_path = order.get_tracking_url()
    tracking_url = f"{base_url}{tracking_path}" if base_url else tracking_path

    send_order_confirmation_email(
        order=order,
        base_url=base_url,
        tracking_url=tracking_url,
        payment_url="",  # We are already paid, no need for payment_url
    )

    messages.success(request, _("Payment successful. Thank you for your order!"))
    return redirect("orders:summary", token=order.tracking_token)
