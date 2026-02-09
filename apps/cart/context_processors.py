from .models import Cart

def cart_context(request):
    cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")

    if not cart_id:
        return {
            "nav_cart": None,
            "nav_cart_lines": [],
            "nav_cart_total": 0,
            "nav_cart_count": 0,
        }

    try:
        cart = Cart.objects.prefetch_related(
            "lines__product"
        ).get(id=cart_id)
    except Cart.DoesNotExist:
        return {
            "nav_cart": None,
            "nav_cart_lines": [],
            "nav_cart_total": 0,
            "nav_cart_count": 0,
        }

    return {
        "nav_cart": cart,
        "nav_cart_lines": cart.lines.all(),
        "nav_cart_total": cart.total,
        "nav_cart_count": cart.lines.count(),
    }
