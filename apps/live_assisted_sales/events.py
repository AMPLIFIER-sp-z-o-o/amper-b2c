import logging
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from django.utils import timezone

from apps.web.models import SiteSettings

from .client import enqueue_event
from .models import LiveAssistedSalesSettings

logger = logging.getLogger(__name__)
SUPPORTED_EVENT_TYPES = {
    "product_view",
    "category_view",
    "search",
    "cart_item_added",
    "cart_item_removed",
    "session_end",
}


def visitor_id_from_request(request):
    return (
        request.COOKIES.get("las_visitor_id")
        or getattr(request.session, "session_key", None)
        or f"visitor-{uuid4()}"
    )


def session_id_from_request(request):
    return (
        request.COOKIES.get("las_session_id")
        or getattr(request.session, "session_key", None)
        or f"session-{uuid4()}"
    )


def user_metadata_from_request(request):
    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        email = str(getattr(user, "email", "") or "")
        username = getattr(user, "get_username", lambda: "")()
        if not email and "@" in str(username):
            email = str(username)
        display = (
            email
            or getattr(user, "get_full_name", lambda: "")()
            or username
            or str(getattr(user, "pk", ""))
        )
        return {
            "status": "authenticated",
            "authenticated": True,
            "id": str(getattr(user, "pk", "")),
            "email": email,
            "display": display,
        }
    return {"status": "anonymous", "authenticated": False}


def build_event_payload(request, event_type, **data):
    occurred_at = data.pop("occurred_at", None) or timezone.now()
    if hasattr(occurred_at, "isoformat"):
        occurred_at = occurred_at.isoformat()
    metadata = data.pop("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    metadata["user"] = user_metadata_from_request(request)
    return {
        "event_id": str(data.pop("event_id", uuid4())),
        "event_type": event_type,
        "visitor_id": data.pop("visitor_id", None) or visitor_id_from_request(request),
        "session_id": data.pop("session_id", None) or session_id_from_request(request),
        "occurred_at": occurred_at,
        "url": data.pop("url", request.build_absolute_uri()),
        "page": data.pop("page", {}),
        "product": data.pop("product", {}),
        "category": data.pop("category", {}),
        "search": data.pop("search", {}),
        "cart": data.pop("cart", None)
        or cart_payload(None if request is None else _current_cart_from_request(request), request=request),
        "cursor": data.pop("cursor", {}),
        "metadata": metadata,
    }


def dispatch_event(request, event_type, **data):
    if event_type not in SUPPORTED_EVENT_TYPES:
        return False
    settings_obj = LiveAssistedSalesSettings.get_solo()
    payload = build_event_payload(request, event_type, **data)
    try:
        return enqueue_event(settings_obj, payload)
    except Exception:
        logger.exception("Live Assisted Sales event enqueue failed.")
        return False


def _absolute_payload_url(request, url):
    if not url:
        return ""
    url = str(url)
    if url.startswith(("http://", "https://")):
        return url
    if request and hasattr(request, "build_absolute_uri"):
        return request.build_absolute_uri(url)
    return url


def product_payload(product, request=None):
    if not product:
        return {}
    url = product.get_absolute_url() if hasattr(product, "get_absolute_url") else ""
    return {
        "id": str(getattr(product, "id", "")),
        "name": getattr(product, "name", "") or "",
        "sku": getattr(product, "sku", "") or getattr(product, "code", "") or "",
        "url": _absolute_payload_url(request, url),
    }


def category_payload(category, request=None):
    if not category:
        return {}
    url = category.get_absolute_url() if hasattr(category, "get_absolute_url") else ""
    return {
        "id": str(getattr(category, "id", "")),
        "name": getattr(category, "name", "") or "",
        "slug": getattr(category, "slug", "") or "",
        "url": _absolute_payload_url(request, url),
    }


def storefront_currency():
    settings_obj = SiteSettings.get_settings()
    return (getattr(settings_obj, "currency", "") or SiteSettings.Currency.USD).upper()


def format_storefront_amount(amount, currency=None):
    currency = (currency or storefront_currency()).upper()
    try:
        amount_value = Decimal(str(amount)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return f"{amount} {currency}".strip()
    if currency == SiteSettings.Currency.PLN:
        return f"{amount_value:,.2f}".replace(",", " ").replace(".", ",") + " zł"
    if currency == SiteSettings.Currency.EUR:
        return f"{amount_value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"
    if currency == SiteSettings.Currency.USD:
        return f"${amount_value:,.2f}"
    return f"{amount_value:,.2f} {currency}"


def cart_payload(cart, request=None):
    currency = storefront_currency()
    if not cart:
        return {
            "items_count": 0,
            "total": "0.00",
            "total_display": format_storefront_amount("0.00", currency),
            "currency": currency,
            "items": [],
        }
    lines = list(cart.lines.select_related("product").all()) if hasattr(cart, "lines") else []
    total = str(getattr(cart, "total", "0.00"))
    return {
        "items_count": sum(line.quantity for line in lines),
        "total": total,
        "total_display": format_storefront_amount(total, currency),
        "currency": currency,
        "items": [
            {
                "product_id": str(line.product_id),
                "name": getattr(line.product, "name", ""),
                "sku": getattr(line.product, "sku", "") or getattr(line.product, "code", "") or "",
                "url": _absolute_payload_url(
                    request,
                    line.product.get_absolute_url() if hasattr(line.product, "get_absolute_url") else "",
                ),
                "quantity": line.quantity,
                "price": str(getattr(line, "price", "")),
                "line_total": str(getattr(line, "subtotal", "")),
                "currency": currency,
            }
            for line in lines[:50]
        ],
    }


def _current_cart_from_request(request):
    if not request:
        return None
    try:
        from apps.cart.models import Cart
        from apps.cart.services import _get_cart_from_request

        cart_id = _cart_id_from_request(request)
        cart = _get_cart_from_request(request, cart_id) if cart_id else None
        user = getattr(request, "user", None)
        if not cart and user and user.is_authenticated:
            cart = (
                Cart.objects.prefetch_related("lines__product").filter(customer=user).order_by("-id").first()
            )
        return cart
    except Exception:
        logger.exception("Live Assisted Sales cart payload lookup failed.")
        return None


def _cart_id_from_request(request):
    cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")
    if cart_id in (None, ""):
        return None
    return cart_id if isinstance(cart_id, int | str) else None


def track_product_view(request, product):
    return dispatch_event(
        request,
        "product_view",
        product=product_payload(product, request=request),
        page={"title": getattr(product, "name", "")},
    )


def track_category_view(request, category):
    return dispatch_event(
        request,
        "category_view",
        category=category_payload(category, request=request),
        page={"title": getattr(category, "name", "")},
    )


def track_search(request, query):
    if not query:
        return False
    return dispatch_event(request, "search", search={"query": query}, page={"title": f"Search: {query}"})


def track_cart_item_added(request, cart, product):
    return dispatch_event(
        request,
        "cart_item_added",
        product=product_payload(product, request=request),
        cart=cart_payload(cart, request=request),
    )


def track_cart_item_removed(request, cart, product):
    return dispatch_event(
        request,
        "cart_item_removed",
        product=product_payload(product, request=request),
        cart=cart_payload(cart, request=request),
    )
