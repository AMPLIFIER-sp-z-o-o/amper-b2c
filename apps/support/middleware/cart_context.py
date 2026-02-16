from apps.cart.models import Cart


class CartContextMiddleware:
    """Attach current cart to request for downstream use."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")
        request.cart = Cart.objects.filter(id=cart_id).first() if cart_id else None
        return self.get_response(request)
