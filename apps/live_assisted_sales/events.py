import logging
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from django.utils import timezone

from apps.web.models import SiteSettings

from .client import enqueue_event
from .models import LiveAssistedSalesSettings

logger = logging.getLogger(__name__)
# High-frequency telemetry never needs a server-side cart snapshot, so we skip the per-event cart DB
# lookup for these (a page_ping every ~15s must not run a cart query each time).
CART_CONTEXT_EXCLUDED_EVENT_TYPES = {"click", "scroll_depth", "page_ping", "cursor_hover"}
SUPPORTED_EVENT_TYPES = {
    "session_start",
    "product_view",
    "category_view",
    "search",
    "cart_item_added",
    "cart_item_removed",
    "checkout_started",
    "order_completed",
    # Client-side behavioral telemetry (LAS-6 coverage): generic clicks, scroll depth, engaged-time
    # heartbeats and cursor hover. Emitted by the tracker and forwarded to LAS through the proxy.
    "click",
    "scroll_depth",
    "page_ping",
    "cursor_hover",
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


def client_ip_from_request(request):
    """Real shopper IP for the event. Events are forwarded server-to-server to LAS, so LAS only sees
    this app's server IP — we must capture the visitor's address here and pass it in the payload.
    Honours X-Forwarded-For (first hop) when behind a proxy, else REMOTE_ADDR."""
    if request is None:
        return ""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.META.get("REMOTE_ADDR", "") or ""


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


def _absolute_logo_url(request):
    """Absolute URL of the store logo, or "" if unset/unavailable. Mirrors the value the chat widget
    embed passes via data-las-logo, so the agent console shows the same brand avatar."""
    if request is None:
        return ""
    try:
        logo_url = SiteSettings.get_settings().logo_url
    except Exception:
        logger.exception("Live Assisted Sales logo lookup failed.")
        return ""
    return request.build_absolute_uri(logo_url) if logo_url else ""


def build_event_payload(request, event_type, **data):
    occurred_at = data.pop("occurred_at", None) or timezone.now()
    if hasattr(occurred_at, "isoformat"):
        occurred_at = occurred_at.isoformat()
    metadata = data.pop("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    metadata["user"] = user_metadata_from_request(request)
    client_ip = client_ip_from_request(request)
    if client_ip:
        metadata["client_ip"] = client_ip
    # Forward the originating request's User-Agent so LAS can detect AI-agent traffic (ChatGPT, Gemini,
    # Perplexity, Rufus, …) — the cookieless-agent signal client-side analytics can't see. Don't
    # overwrite a UA the client tracker may have already supplied.
    if request is not None and not metadata.get("user_agent"):
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        if user_agent:
            metadata["user_agent"] = user_agent[:512]
    # Forward the shopper's consent choice (set by the tracker's banner as a cookie) so LAS honors it
    # for server-side events too. LAS decides the meaning per its market regime (EU opt-in / US opt-out).
    if request is not None and "consent" not in metadata:
        consent_cookie = request.COOKIES.get("las_consent")
        if consent_cookie in ("true", "false"):
            metadata["consent"] = consent_cookie == "true"
    # Propagate the store's brand logo once per session so the LAS agent console can show it as the
    # support-team avatar, matching the customer-facing widget. Only on session_start to avoid
    # repeating it on every event.
    if event_type == "session_start":
        logo_url = _absolute_logo_url(request)
        if logo_url:
            metadata["widget"] = {**metadata.get("widget", {}), "logo_url": logo_url}
    cart = data.pop("cart", None)
    if not cart and event_type not in CART_CONTEXT_EXCLUDED_EVENT_TYPES:
        cart = cart_payload(None if request is None else _current_cart_from_request(request), request=request)
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
        "cart": cart or {},
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


def order_cart_payload(order, request=None):
    """A cart-shaped snapshot of a placed order so the LAS agent console renders order line items and
    totals with the same helpers it uses for live carts. ``line_total == unit_price * quantity`` is
    preserved so the funnel value invariant (value == sum(unit_price*qty)) holds downstream."""
    currency = (getattr(order, "currency", "") or storefront_currency()).upper()
    lines = list(order.lines.select_related("product").all()) if hasattr(order, "lines") else []
    total = str(getattr(order, "total", "0.00"))
    return {
        "items_count": sum(int(line.quantity or 0) for line in lines),
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
                "price": str(getattr(line, "unit_price", "")),
                "line_total": str(getattr(line, "line_total", "")),
                "currency": currency,
            }
            for line in lines[:50]
        ],
    }


def order_metadata(order):
    """Order-specific fields carried in ``metadata.order`` (the StorefrontEvent JSON columns have no
    dedicated order field). These are the supervised labels the intent engine (LAS-7) reads."""
    currency = (getattr(order, "currency", "") or storefront_currency()).upper()
    return {
        "order": {
            "order_id": str(getattr(order, "pk", "")),
            "tracking_token": getattr(order, "tracking_token", "") or "",
            "status": getattr(order, "status", "") or "",
            "subtotal": str(getattr(order, "subtotal", "")),
            "discount_total": str(getattr(order, "discount_total", "")),
            "delivery_cost": str(getattr(order, "delivery_cost", "")),
            "total": str(getattr(order, "total", "")),
            "currency": currency,
            "coupon_code": getattr(order, "coupon_code", "") or "",
        }
    }


def track_checkout_started(request, cart, *, visitor_id=None, session_id=None):
    """Funnel step: the shopper is placing an order. Carries the current cart snapshot."""
    return dispatch_event(
        request,
        "checkout_started",
        cart=cart_payload(cart, request=request),
        visitor_id=visitor_id,
        session_id=session_id,
        page={"title": "Checkout"},
    )


def track_order_completed(request, order, *, visitor_id=None, session_id=None):
    """Conversion event built straight from Order+OrderLine. THE label for LAS-7. ``visitor_id``/
    ``session_id`` should be the LAS ids captured at order creation so the conversion attributes to
    the right session even though delivery is off the request path."""
    return dispatch_event(
        request,
        "order_completed",
        cart=order_cart_payload(order, request=request),
        metadata=order_metadata(order),
        visitor_id=visitor_id,
        session_id=session_id,
        page={"title": f"Order {getattr(order, 'pk', '')}"},
    )
