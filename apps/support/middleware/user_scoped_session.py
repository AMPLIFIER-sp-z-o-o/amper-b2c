"""
Middleware that scopes session-based data to the impersonated user during hijack.

When an admin impersonates a user via django-hijack, request.user is swapped to
the hijacked user but session-based references (e.g. cart_id) still reflect the
admin's data.  This middleware detects active hijack and loads the impersonated
user's cart into the session so that every view that reads session["cart_id"]
automatically sees the correct user's cart.
"""

from apps.cart.models import Cart


class UserScopedSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        hijack_active = bool(getattr(request, "session", {}).get("hijack_history", []))

        if user and user.is_authenticated and hijack_active:
            self._scope_cart_to_user(request, user)

        return self.get_response(request)

    @staticmethod
    def _scope_cart_to_user(request, user):
        """
        If the session has no cart_id (or the cart belongs to another user),
        look up the impersonated user's most recent cart and set it in the
        session so all downstream code sees the right cart.
        """
        session_cart_id = request.session.get("cart_id")

        if session_cart_id:
            # Verify the session cart actually belongs to the impersonated user
            try:
                cart = Cart.objects.get(id=session_cart_id)
                if cart.customer_id == user.pk:
                    return  # already correct
            except Cart.DoesNotExist:
                pass

        # Look up the impersonated user's most recent cart
        user_cart = Cart.objects.filter(customer=user).order_by("-id").first()

        if user_cart:
            request.session["cart_id"] = user_cart.id
        else:
            # User has no cart – clear any stale reference
            request.session.pop("cart_id", None)
