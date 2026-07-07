import logging
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from django.utils import timezone

from apps.web.models import SiteSettings

from .client import enqueue_event
from .models import LiveAssistedSalesSettings

logger = logging.getLogger(__name__)
# High-frequency telemetry never needs a server-side cart snapshot, so we skip the per-event cart DB
# lookup for these (a page_ping every ~15s must not run a cart query each time). select_item is a
# client-side product-tile click, which likewise carries no cart context.
CART_CONTEXT_EXCLUDED_EVENT_TYPES = {"scroll_depth", "page_ping", "select_item"}
# The storefront event taxonomy, standardised on the GA4 recommended-ecommerce names. The funnel events
# (view_item_list … purchase) are the shopping journey LAS surfaces to the agent; the trailing block is
# the retained behavioural signals that only feed live-activity and intent scoring. Generic clicks and
# cursor-hover were intentionally dropped as non-standard noise (hover is a heatmap category, not an
# analytics event). Keep in sync with las-backend StorefrontEvent.EventType.
SUPPORTED_EVENT_TYPES = {
    "view_item_list",
    "select_item",
    "view_item",
    "add_to_wishlist",
    "add_to_cart",
    "remove_from_cart",
    "view_cart",
    "begin_checkout",
    "add_shipping_info",
    "add_payment_info",
    "purchase",
    # Behavioural signals (not GA4 funnel): session lifecycle + engagement, forwarded to LAS.
    "session_start",
    "search",
    "scroll_depth",
    "page_ping",
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


def user_metadata_from_request(request, *, include_pii=True):
    """Identity block for the event. ``include_pii=False`` (consent withheld) keeps the pseudonymous
    account id + authenticated status for operational linkage but DROPS the raw email/display name, so
    no directly-identifying PII leaves the storefront before the shopper consents."""
    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        if not include_pii:
            return {
                "status": "authenticated",
                "authenticated": True,
                "id": str(getattr(user, "pk", "")),
            }
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


def _pii_forwarding_allowed(request, metadata):
    """Whether raw PII (email, IP) may be forwarded to LAS for this event. EU/EEA/UK: only once the
    shopper has explicitly consented (opt-in). Elsewhere: allowed unless they explicitly opted out."""
    if request is None:
        return False
    if metadata.get("consent") is False:
        return False
    try:
        from .context_processors import _consent_region

        if _consent_region(request) == "eu":
            return metadata.get("consent") is True
    except Exception:
        logger.exception("Live Assisted Sales consent-region lookup failed; withholding PII.")
        return False
    return True


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
    # Resolve the shopper's consent choice FIRST (set by the tracker's banner as a cookie) so it can
    # gate PII below. LAS also applies its own per-store regime once it receives the flag.
    if request is not None and "consent" not in metadata:
        consent_cookie = request.COOKIES.get("las_consent")
        if consent_cookie in ("true", "false"):
            metadata["consent"] = consent_cookie == "true"
    # GDPR: withhold raw email + IP for EU visitors who haven't consented (and anyone who opted out),
    # so directly-identifying PII never leaves the storefront before there is a legal basis to profile.
    pii_allowed = _pii_forwarding_allowed(request, metadata)
    metadata["user"] = user_metadata_from_request(request, include_pii=pii_allowed)
    if pii_allowed:
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


def _product_image_url(product, request=None):
    """Absolute URL of a product's primary image (lowest sort_order), or "" when it has none.

    LAS uses this to render a real product card when an agent sends a suggestion to a shopper.
    """
    images = getattr(product, "images", None)
    if images is None:
        return ""
    try:
        first = images.all().order_by("sort_order", "id").first()
    except Exception:
        first = None
    image = getattr(first, "image", None) if first else None
    if not image:
        return ""
    try:
        return _absolute_payload_url(request, image.url)
    except Exception:
        return ""


def product_payload(product, request=None):
    if not product:
        return {}
    url = product.get_absolute_url() if hasattr(product, "get_absolute_url") else ""
    currency = storefront_currency()
    price = getattr(product, "price", None)
    return {
        "id": str(getattr(product, "id", "")),
        "name": getattr(product, "name", "") or "",
        "sku": getattr(product, "sku", "") or getattr(product, "code", "") or "",
        "url": _absolute_payload_url(request, url),
        # Image + price let LAS render a clickable product card (not just text) in the chat.
        "image": _product_image_url(product, request=request),
        "price": str(price) if price not in (None, "") else "",
        "price_display": format_storefront_amount(price, currency) if price not in (None, "") else "",
        "currency": currency,
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


def track_view_item(request, product):
    return dispatch_event(
        request,
        "view_item",
        product=product_payload(product, request=request),
        page={"title": getattr(product, "name", "")},
    )


def track_view_item_list(request, category=None, *, list_name=""):
    """GA4 view_item_list — a product list was shown (category page, all-products listing or search
    results). Carries the category payload when browsing a category, otherwise just a list name."""
    title = getattr(category, "name", "") if category else (list_name or "Products")
    return dispatch_event(
        request,
        "view_item_list",
        category=category_payload(category, request=request) if category else {},
        page={"title": title},
    )


def track_search(request, query, results_count=None):
    if not query:
        return False
    search = {"query": query}
    # LAS classifies zero-result searches ("Braki w ofercie") strictly by results_count,
    # so callers should always pass it; None means the caller genuinely doesn't know.
    if results_count is not None:
        search["results_count"] = results_count
    return dispatch_event(request, "search", search=search, page={"title": f"Search: {query}"})


def track_add_to_cart(request, cart, product):
    return dispatch_event(
        request,
        "add_to_cart",
        product=product_payload(product, request=request),
        cart=cart_payload(cart, request=request),
    )


def track_remove_from_cart(request, cart, product):
    return dispatch_event(
        request,
        "remove_from_cart",
        product=product_payload(product, request=request),
        cart=cart_payload(cart, request=request),
    )


def track_add_to_wishlist(request, product):
    """GA4 add_to_wishlist — a product was saved to a wishlist / favourites."""
    return dispatch_event(
        request,
        "add_to_wishlist",
        product=product_payload(product, request=request),
        page={"title": getattr(product, "name", "")},
    )


def track_view_cart(request, cart):
    """GA4 view_cart — the shopper opened the cart page with items in it."""
    return dispatch_event(
        request,
        "view_cart",
        cart=cart_payload(cart, request=request),
        page={"title": "Cart"},
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


def track_begin_checkout(request, cart, *, visitor_id=None, session_id=None):
    """GA4 begin_checkout — the shopper entered the checkout process. Carries the current cart snapshot.
    Fired when the checkout page opens (not at final submit), matching GA4 funnel semantics."""
    return dispatch_event(
        request,
        "begin_checkout",
        cart=cart_payload(cart, request=request),
        visitor_id=visitor_id,
        session_id=session_id,
        page={"title": "Checkout"},
    )


def _delivery_metadata(cart):
    method = getattr(cart, "delivery_method", None)
    if not method:
        return {}
    return {"shipping": {"tier": getattr(method, "name", "") or "", "cost": str(getattr(cart, "delivery_cost", "") or "")}}


def _payment_metadata(cart):
    method = getattr(cart, "payment_method", None)
    if not method:
        return {}
    return {"payment": {"type": getattr(method, "name", "") or ""}}


def track_add_shipping_info(request, cart, *, visitor_id=None, session_id=None):
    """GA4 add_shipping_info — the shopper confirmed a delivery method. Carries the checkout basket."""
    return dispatch_event(
        request,
        "add_shipping_info",
        cart=cart_payload(cart, request=request),
        metadata=_delivery_metadata(cart),
        visitor_id=visitor_id,
        session_id=session_id,
        page={"title": "Checkout"},
    )


def track_add_payment_info(request, cart, *, visitor_id=None, session_id=None):
    """GA4 add_payment_info — the shopper confirmed a payment method. Carries the checkout basket."""
    return dispatch_event(
        request,
        "add_payment_info",
        cart=cart_payload(cart, request=request),
        metadata=_payment_metadata(cart),
        visitor_id=visitor_id,
        session_id=session_id,
        page={"title": "Checkout"},
    )


def track_purchase(request, order, *, visitor_id=None, session_id=None):
    """GA4 purchase — conversion built straight from Order+OrderLine. THE label for LAS-7. ``visitor_id``/
    ``session_id`` should be the LAS ids captured at order creation so the conversion attributes to
    the right session even though delivery is off the request path."""
    return dispatch_event(
        request,
        "purchase",
        cart=order_cart_payload(order, request=request),
        metadata=order_metadata(order),
        visitor_id=visitor_id,
        session_id=session_id,
        page={"title": f"Order {getattr(order, 'pk', '')}"},
    )
