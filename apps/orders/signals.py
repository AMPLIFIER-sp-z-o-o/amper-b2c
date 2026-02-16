from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .models import Order


@receiver(user_logged_in)
def attach_guest_orders_on_login(sender, request, user, **kwargs):
    """Attach past guest orders to the user account after login.

    This enables a smooth "guest checkout → later create/sign in" flow where
    order history becomes visible under the account.
    """
    if not getattr(user, "email", None):
        return

    try:
        Order.objects.filter(
            customer__isnull=True,
            email__iexact=user.email,
            email_verified_at__isnull=False,
        ).update(customer=user)
    except Exception:
        # Never break login
        return
