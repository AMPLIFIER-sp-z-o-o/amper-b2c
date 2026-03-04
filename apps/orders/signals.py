from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.plugins.engine.registry import registry
from apps.plugins.hook_names import ORDER_SHIPPED, ORDER_STATUS_CHANGED

from .models import Order, OrderStatus


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


@receiver(pre_save, sender=Order)
def capture_previous_order_status(sender, instance: Order, **kwargs):
    if not instance.pk:
        instance._previous_status = None
        return

    previous_status = (
        Order.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
    )
    instance._previous_status = previous_status


@receiver(post_save, sender=Order)
def dispatch_order_status_hooks(sender, instance: Order, created: bool, **kwargs):
    if created:
        return

    previous_status = getattr(instance, "_previous_status", None)
    current_status = instance.status
    if not previous_status or previous_status == current_status:
        return

    registry.dispatch_action(
        ORDER_STATUS_CHANGED,
        order=instance,
        previous_status=previous_status,
        status=current_status,
    )

    shipped_statuses = {OrderStatus.CONFIRMED}
    if hasattr(OrderStatus, "SHIPPED"):
        shipped_statuses.add(OrderStatus.SHIPPED)

    if current_status in shipped_statuses:
        registry.dispatch_action(
            ORDER_SHIPPED,
            order=instance,
            previous_status=previous_status,
            status=current_status,
        )
