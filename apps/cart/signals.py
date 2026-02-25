from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from apps.cart.checkout import (
    CHECKOUT_MODE_ORDER_SESSION,
    CHECKOUT_MODE_USER_DEFAULT,
    get_checkout_mode,
    get_checkout_state,
    set_checkout_active_details,
    set_checkout_order_details,
    touch_checkout_session,
)
from apps.cart.models import Cart, CartLine
from apps.users.models import ShippingAddress


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


@receiver(user_logged_in)
def migrate_checkout_on_login(sender, request, user, **kwargs):
    """Preserve guest checkout details on login and optionally save as default.

    Rules:
    - Never overwrite user's existing addresses automatically.
    - If user has no addresses and checkout details are complete & not expired -> save as default.
    - Keep the "address entered in this order" snapshot in session.
    - Rotate session key (cycle_key) to mitigate session fixation.
    """

    if not request or not user:
        return

    try:
        state = get_checkout_state(request, touch=False)
        if state.expired:
            return

        order_details = state.order_details or {}
        active_details = state.active_details or {}

        # If only active details exist (older sessions), treat them as order_details too.
        if active_details and not order_details:
            set_checkout_order_details(request, active_details)
            order_details = dict(active_details)

        # Always touch meta so timeout policy starts tracking post-login navigation.
        current_mode = get_checkout_mode(state.meta)
        touch_checkout_session(request, set_mode=current_mode)

        if not order_details:
            # No checkout details to migrate.
            try:
                request.session.cycle_key()
            except Exception:
                pass
            return

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
        if any(not (order_details.get(k) or "").strip() for k in required):
            # Incomplete -> keep in session for user to fix, but don't save to account.
            try:
                request.session.cycle_key()
            except Exception:
                pass
            return

        def _norm(value: str) -> str:
            return " ".join(str(value or "").strip().split()).lower()

        has_any = ShippingAddress.objects.filter(user=user).exists()

        street = _norm(order_details.get("shipping_street"))
        postal = _norm(order_details.get("shipping_postal_code"))
        city = _norm(order_details.get("shipping_city"))
        building = _norm(order_details.get("shipping_building_number"))
        apt = _norm(order_details.get("shipping_apartment_number"))

        full_name = " ".join([order_details.get("first_name") or "", order_details.get("last_name") or ""]).strip()
        defaults = {
            "full_name": full_name,
            "phone_country_code": (order_details.get("phone_country_code") or "+48").strip() or "+48",
            "phone_number": (order_details.get("phone_number") or "").strip(),
            "shipping_city": (order_details.get("shipping_city") or "").strip(),
            "shipping_postal_code": (order_details.get("shipping_postal_code") or "").strip(),
            "shipping_street": (order_details.get("shipping_street") or "").strip(),
            "shipping_building_number": (order_details.get("shipping_building_number") or "").strip(),
            "shipping_apartment_number": (order_details.get("shipping_apartment_number") or "").strip(),
        }

        match = (
            ShippingAddress.objects.filter(
                user=user,
                shipping_street__iexact=street,
                shipping_postal_code__iexact=postal,
                shipping_city__iexact=city,
                shipping_building_number__iexact=building,
                shipping_apartment_number__iexact=apt,
            )
            .order_by("-updated_at", "-id")
            .first()
        )

        if not has_any:
            if match:
                for k, v in defaults.items():
                    setattr(match, k, v)
                match.is_default = True
                match.save()
                ShippingAddress.objects.filter(user=user).exclude(pk=match.pk).update(is_default=False)
            else:
                ShippingAddress.objects.filter(user=user).update(is_default=False)
                ShippingAddress.objects.create(user=user, is_default=True, **defaults)

            # Prefer using the (now) default address mode.
            set_checkout_active_details(request, order_details, mode=CHECKOUT_MODE_USER_DEFAULT)
            touch_checkout_session(request, set_mode=CHECKOUT_MODE_USER_DEFAULT)
        else:
            # User already has addresses: never overwrite existing ones or change the default.
            # If the checkout address is new, add it as a non-default saved address.
            if not match:
                ShippingAddress.objects.create(user=user, is_default=False, **defaults)

            # For clarity, keep using the address entered in this order after login.
            set_checkout_active_details(request, order_details, mode=CHECKOUT_MODE_ORDER_SESSION)
            touch_checkout_session(request, set_mode=CHECKOUT_MODE_ORDER_SESSION)

        try:
            request.session.cycle_key()
        except Exception:
            pass
    except Exception:
        return
