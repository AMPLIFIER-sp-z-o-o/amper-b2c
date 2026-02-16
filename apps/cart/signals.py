from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from apps.cart.models import Cart, CartLine


@receiver(user_logged_in)
def merge_session_cart_on_login(sender, request, user, **kwargs):
    """Bind/merge the current anonymous session cart into the user's cart.

    Cart is primarily tracked by `cart_id` in session/cookie. When a user logs in,
    we want the cart to become associated with the account so it can be reused
    across sessions/devices.

    Strategy:
    - If the session cart is anonymous, but user has no cart -> bind it.
    - If the user has a cart and session cart is different -> merge lines and delete session cart.

    This is best-effort and must never break login.
    """

    if not request:
        return

    try:
        cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")
        if not cart_id:
            return

        session_cart = Cart.objects.prefetch_related("lines__product").filter(id=cart_id).first()
        if not session_cart:
            return

        # If it's already bound to this user, nothing to do.
        if session_cart.customer_id == user.id:
            request.session["cart_id"] = session_cart.id
            return

        # If session cart belongs to someone else, do not touch it.
        if session_cart.customer_id and session_cart.customer_id != user.id:
            return

        # Pick an existing user cart (latest id) if present.
        user_cart = Cart.objects.filter(customer=user).order_by("-id").first()

        if not user_cart:
            session_cart.customer = user
            session_cart.save(update_fields=["customer"])
            request.session["cart_id"] = session_cart.id
            return

        if user_cart.id == session_cart.id:
            return

        # Merge: move all session lines into user_cart, summing quantities.
        for line in session_cart.lines.all():
            product = line.product
            available = int(product.stock or 0)
            if available <= 0:
                continue

            existing = CartLine.objects.filter(cart=user_cart, product=product).first()
            if existing:
                desired = int(existing.quantity or 0) + int(line.quantity or 0)
                existing.quantity = min(desired, available)
                existing.price = product.price
                if existing.quantity <= 0:
                    existing.delete()
                else:
                    existing.save(update_fields=["quantity", "price"])
            else:
                quantity = min(int(line.quantity or 0), available)
                if quantity <= 0:
                    continue
                CartLine.objects.create(
                    cart=user_cart,
                    product=product,
                    quantity=quantity,
                    price=product.price,
                )

        user_cart.recalculate()

        session_cart.lines.all().delete()
        session_cart.delete()

        request.session["cart_id"] = user_cart.id
    except Exception:
        return
