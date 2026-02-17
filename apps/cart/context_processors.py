from decimal import Decimal

from .models import Cart
from .services import _get_cart_from_request, refresh_cart_totals_from_db


def cart_context(request):
    cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")

    if not cart_id:
        return {
            "nav_cart": None,
            "nav_cart_lines": [],
            "nav_cart_total": 0,
            "nav_cart_count": 0,
        }

    # Important: this must use the same access control as the cart views.
    # Otherwise, a user-bound cart could be rendered in the navbar for an
    # anonymous user (or a different authenticated user) before a view clears
    # the cookie in the response.
    cart = _get_cart_from_request(request, cart_id)
    if not cart and request.user.is_authenticated:
        # Self-heal: stale cart_id might point to a different user's cart.
        cart = Cart.objects.prefetch_related("lines__product").filter(customer=request.user).order_by("-id").first()
        if cart:
            request.session["cart_id"] = cart.id

    if not cart:
        # Best-effort: clear session pointer (cookie can only be cleared in a response).
        request.session.pop("cart_id", None)
        return {
            "nav_cart": None,
            "nav_cart_lines": [],
            "nav_cart_total": 0,
            "nav_cart_count": 0,
        }

    # Keep navbar totals consistent with current DB state.
    # Guard against doing this multiple times within the same request.
    if not getattr(request, "_cart_totals_refreshed", False):
        try:
            refresh_cart_totals_from_db(cart)
        except Exception:
            pass
        setattr(request, "_cart_totals_refreshed", True)

    nav_cart_lines = list(cart.lines.select_related("product").all())
    nav_cart_count = sum(int(line.quantity or 0) for line in nav_cart_lines)

    return {
        "nav_cart": cart,
        "nav_cart_lines": nav_cart_lines,
        "nav_cart_total": cart.total if nav_cart_lines else Decimal("0.00"),
        # Total quantity of all products in cart (not number of distinct lines)
        "nav_cart_count": nav_cart_count,
    }
