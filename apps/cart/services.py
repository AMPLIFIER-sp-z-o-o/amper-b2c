from __future__ import annotations

from django.http import HttpRequest

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


# Backwards-compatible aliases (used across the codebase)
_clear_cart_id = clear_cart_id
_get_cart_from_request = get_cart_from_request
_annotate_lines_with_stock_issues = annotate_lines_with_stock_issues
