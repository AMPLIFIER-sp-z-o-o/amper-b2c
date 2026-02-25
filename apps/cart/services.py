from __future__ import annotations

from decimal import Decimal

from django.http import HttpRequest
from django.utils import timezone

from apps.catalog.models import ProductStatus

from .models import Cart


def clear_cart_id(request: HttpRequest, response=None):
    request.session.pop("cart_id", None)
    if response is not None:
        response.delete_cookie("cart_id")
    return response


def get_cart_from_request(request: HttpRequest, cart_id: str | None) -> Cart | None:
    if not cart_id:
        return None

    cart = Cart.objects.filter(id=cart_id).first()
    if not cart:
        return None

    # If the cart is bound to a user, it must only be accessible by that user.
    if cart.customer_id:
        if not request.user.is_authenticated:
            return None
        if cart.customer_id != request.user.id:
            return None

    return cart


def annotate_lines_with_stock_issues(lines) -> list[dict]:
    """Annotate cart lines with stock/availability issues for checkout UX.

    Important: this function is read-only and MUST NOT mutate the cart.

    Adds dynamic attributes to each line:
    - line.checkout_stock_issue (bool)
    - line.checkout_stock_available (int)

    Returns a list of issue dicts for optional UI summaries.
    """

    issues: list[dict] = []

    for line in lines:
        product = line.product
        available = int(product.stock or 0)
        is_purchasable = product.status == ProductStatus.ACTIVE and available > 0

        line.checkout_stock_issue = False
        line.checkout_stock_available = available

        if not is_purchasable:
            line.checkout_stock_issue = True
            line.checkout_stock_available = 0
            issues.append(
                {
                    "type": "unavailable",
                    "product_name": product.name,
                    "old_quantity": line.quantity,
                    "available": 0,
                }
            )
            continue

        if line.quantity > available:
            line.checkout_stock_issue = True
            line.checkout_stock_available = available
            issues.append(
                {
                    "type": "exceeds_stock",
                    "product_name": product.name,
                    "old_quantity": line.quantity,
                    "available": available,
                }
            )

    return issues


def ensure_cart_methods_active(cart: Cart) -> dict:
    """Ensure selected delivery/payment methods are still active.

    Returns a dict describing what was changed.
    """

    changed = {
        "delivery_method_cleared": False,
        "payment_method_cleared": False,
    }

    if getattr(cart, "delivery_method_id", None):
        # Avoid stale FK references to disabled methods.
        if not cart.delivery_method or not getattr(cart.delivery_method, "is_active", False):
            cart.delivery_method = None
            changed["delivery_method_cleared"] = True

    if getattr(cart, "payment_method_id", None):
        if not cart.payment_method or not getattr(cart.payment_method, "is_active", False):
            cart.payment_method = None
            changed["payment_method_cleared"] = True

    if changed["delivery_method_cleared"] or changed["payment_method_cleared"]:
        cart.save(update_fields=["delivery_method", "payment_method"])
        cart.recalculate()

    return changed


def refresh_cart_totals_from_db(cart: Cart, *, now=None) -> dict:
    """Refresh cart pricing and discounts from the current DB state.

    - Updates each CartLine.price from Product.price (cannot trust stale line price)
    - Revalidates coupon and recomputes discount_total from current subtotal
    - Recalculates cart totals (subtotal/total)

    Returns a dict describing changes.
    """

    if now is None:
        now = timezone.now()

    result = {
        "prices_updated": False,
        "coupon_cleared": False,
        "discount_recomputed": False,
    }

    lines = list(cart.lines.select_related("product").all())
    for line in lines:
        product = line.product
        new_price = (Decimal(product.price or 0)).quantize(Decimal("0.01"))
        if line.price != new_price:
            line.price = new_price
            line.save(update_fields=["price"])
            result["prices_updated"] = True

    # Always recalculate to drop persisted fees for empty carts, etc.
    cart.recalculate()

    code = (getattr(cart, "coupon_code", "") or "").strip()
    if not code:
        return result

    # Import lazily to keep module dependency direction simple.
    from apps.orders.models import Coupon, CouponKind

    coupon = Coupon.objects.filter(is_active=True, code__iexact=code).order_by("-updated_at").first()
    is_valid = True
    if not coupon or coupon.valid_from and now < coupon.valid_from or coupon.valid_to and now > coupon.valid_to or coupon.usage_limit is not None and coupon.used_count >= coupon.usage_limit or coupon.min_subtotal is not None and cart.subtotal < coupon.min_subtotal:
        is_valid = False

    if not is_valid:
        cart.coupon_code = ""
        cart.discount_total = Decimal("0.00")
        cart.recalculate()
        result["coupon_cleared"] = True
        return result

    discount_total = Decimal("0.00")
    if coupon.kind == CouponKind.PERCENT:
        try:
            discount_total = (cart.subtotal * Decimal(coupon.value) / Decimal("100.00")).quantize(Decimal("0.01"))
        except Exception:
            discount_total = Decimal("0.00")
    elif coupon.kind == CouponKind.FIXED:
        try:
            discount_total = Decimal(coupon.value).quantize(Decimal("0.01"))
        except Exception:
            discount_total = Decimal("0.00")

    if discount_total < 0:
        discount_total = Decimal("0.00")
    if discount_total > cart.subtotal:
        discount_total = cart.subtotal

    # Normalize to canonical code.
    cart.coupon_code = coupon.code
    cart.discount_total = discount_total
    cart.recalculate()
    result["discount_recomputed"] = True

    return result


# Backwards-compatible aliases (used across the codebase)
_clear_cart_id = clear_cart_id
_get_cart_from_request = get_cart_from_request
_annotate_lines_with_stock_issues = annotate_lines_with_stock_issues

ensure_cart_methods_active = ensure_cart_methods_active
refresh_cart_totals_from_db = refresh_cart_totals_from_db
