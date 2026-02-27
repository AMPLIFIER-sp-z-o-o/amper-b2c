from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .models import Order


@receiver(user_logged_in)
def attach_guest_orders_on_login(sender, request, user, **kwargs):
    """Attach past guest orders to the user account after login.

    This enables a smooth "guest checkout → later create/sign in" flow where
    order history becomes visible under the account.
    """
    email = (getattr(user, "email", "") or "").strip()
    if not email:
        return

    try:
        Order.objects.filter(
            customer__isnull=True,
            email__iexact=email,
        ).update(customer=user)
    except Exception:
        # Never break login
        return
