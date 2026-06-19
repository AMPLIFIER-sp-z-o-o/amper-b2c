import hashlib
import hmac
import logging
import time

from apps.cart.services import _get_cart_from_request

from .events import _absolute_logo_url, cart_payload, client_ip_from_request
from .models import LiveAssistedSalesSettings

logger = logging.getLogger(__name__)

# Country codes where prior consent is required before behavioural profiling (EU/EEA + UK + CH).
CONSENT_REQUIRED_COUNTRIES = frozenset({
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT",
    "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE",  # EU-27
    "IS", "LI", "NO",  # EEA
    "GB", "CH",        # UK + Switzerland (GDPR-like regimes)
})

# ISO country headers injected by common CDNs / load balancers (most reliable in production).
_GEO_HEADER_KEYS = (
    "HTTP_CF_IPCOUNTRY",                # Cloudflare
    "HTTP_CLOUDFRONT_VIEWER_COUNTRY",   # AWS CloudFront
    "HTTP_X_VERCEL_IP_COUNTRY",         # Vercel
    "HTTP_X_APPENGINE_COUNTRY",         # Google App Engine
    "HTTP_X_GEO_COUNTRY",               # generic / Fastly
    "HTTP_X_COUNTRY_CODE",              # generic proxy
)


def _country_code_from_request(request):
    """Best-effort ISO-3166 alpha-2 country for the request, decided server-side.

    Prefers a country header set by the CDN/load balancer (reliable in production); falls back to
    a local GeoIP2 database if one is configured. Returns "" when the country cannot be determined."""
    for key in _GEO_HEADER_KEYS:
        code = (request.META.get(key) or "").strip().upper()
        if len(code) == 2 and code.isalpha() and code not in ("XX", "T1"):  # XX/T1 = unknown/Tor
            return code
    try:
        from django.contrib.gis.geoip2 import GeoIP2

        ip = client_ip_from_request(request)
        if ip:
            code = (GeoIP2().country_code(ip) or "").strip().upper()
            if len(code) == 2 and code.isalpha():
                return code
    except Exception:
        # GeoIP2 not installed/configured, or private/unknown IP — fall through to "unknown".
        pass
    return ""


def _consent_region(request):
    """Consent regime for this visitor, decided server-side from their IP/country:
    ``"eu"`` (prior consent required), ``"noneu"`` (opt-out allowed), or ``""`` (unknown —
    the client-side tracker then falls back to a timezone heuristic)."""
    code = _country_code_from_request(request)
    if not code:
        return ""
    return "eu" if code in CONSENT_REQUIRED_COUNTRIES else "noneu"


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


# How long a signed identity stays valid. Server-rendered pages refresh the signature on
# every navigation, so this only needs to outlive a long-idle open tab, not be eternal.
CUSTOMER_SIGNATURE_TTL_SECONDS = 2 * 60 * 60


def _sign_customer_identity(external_id, email, store_api_key):
    """HMAC proof for window.LAS_CUSTOMER, verified by las-backend with the same store key.

    Canonical message (must match las-backend's identity_signature_message):
    ``external_id|lowercased email|unix exp``. The key itself never reaches the browser —
    only the signature does, so devtools can't mint identities for other accounts.
    """
    exp = int(time.time()) + CUSTOMER_SIGNATURE_TTL_SECONDS
    message = f"{external_id}|{email.strip().lower()}|{exp}"
    signature = hmac.new(store_api_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    return exp, signature


def _widget_customer_payload(request, store_api_key=""):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}

    email = str(getattr(user, "email", "") or "")
    username = str(getattr(user, "get_username", lambda: "")() or "")
    full_name = str(getattr(user, "get_full_name", lambda: "")() or "").strip()
    first_name = str(getattr(user, "first_name", "") or "").strip()
    display_name = full_name or first_name or email or username
    payload = {
        "id": str(getattr(user, "pk", "") or ""),
        "external_id": str(getattr(user, "pk", "") or ""),
        "email": email,
        "name": display_name,
        "display": display_name,
    }
    if store_api_key:
        exp, signature = _sign_customer_identity(payload["external_id"], email, store_api_key)
        payload["exp"] = exp
        payload["sig"] = signature
    return payload


def _widget_logo_url(request):
    """Absolute URL of the store logo, so the chat widget (served from the LAS origin) can
    render it as the agent avatar. Relative media paths must be made absolute here."""
    return _absolute_logo_url(request)


def live_assisted_sales(request):
    settings_obj = LiveAssistedSalesSettings.get_solo()
    enabled = settings_obj.is_configured
    las_base_url = (settings_obj.las_base_url or "").rstrip("/")
    return {
        "live_assisted_sales": {
            "enabled": enabled,
            "events_url": "/live-assisted-sales/events/",
            "initial_cart": _initial_cart_payload(request) if enabled else {},
            "customer": _widget_customer_payload(request, settings_obj.store_api_key or "") if enabled else {},
            "site_public_key": settings_obj.site_public_key,
            "consent_region": _consent_region(request) if enabled else "",
            "widget_enabled": settings_obj.is_widget_configured,
            "widget_script_url": f"{las_base_url}/widget/v1/chat.js" if las_base_url else "",
            "widget_accent": settings_obj.widget_accent,
            "widget_logo_url": _widget_logo_url(request) if enabled else "",
        }
    }
