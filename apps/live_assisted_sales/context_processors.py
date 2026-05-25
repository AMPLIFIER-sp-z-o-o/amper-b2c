import logging

from apps.cart.services import _get_cart_from_request

from .events import cart_payload
from .models import LiveAssistedSalesSettings

logger = logging.getLogger(__name__)


def _initial_cart_payload(request):
    try:
        cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")
        cart = _get_cart_from_request(request, cart_id) if cart_id else None
        if not cart and request.user.is_authenticated:
            from apps.cart.models import Cart

            cart = Cart.objects.prefetch_related("lines__product").filter(customer=request.user).order_by("-id").first()
        return cart_payload(cart, request=request)
    except Exception:
        logger.exception("Live Assisted Sales initial cart payload failed.")
        return {}


def live_assisted_sales(request):
    settings_obj = LiveAssistedSalesSettings.get_solo()
    enabled = settings_obj.is_configured
    return {
        "live_assisted_sales": {
            "enabled": enabled,
            "events_url": "/live-assisted-sales/events/",
            "initial_cart": _initial_cart_payload(request) if enabled else {},
        }
    }
