import hashlib
import hmac
import logging
import time

from django.utils import translation

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


# Prior-consent banner copy. The banner only ever shows to EU/EEA/UK visitors, but its language must
# follow the STORE's display language (not the visitor's region) — an English store shown to an EU
# shopper must not render a Polish banner. English is the source; add a language key per store locale.
_CONSENT_TEXTS = {
    "en": {
        "aria_label": "Cookie and data-processing consent",
        "title": "We value your privacy",
        "body": (
            "This store uses cookies and data about your activity to work properly, "
            "help you in real time, and recommend products more accurately."
        ),
        # Banner actions. "Accept all" is the visual primary; "Only necessary" is the SAME-layer,
        # one-click decline (kept as easy as accept — reject must never be buried); "Preferences"
        # opens the per-purpose modal.
        "accept_all": "Accept all",
        "only_necessary": "Only necessary",
        "preferences": "Preferences",
        # Preferences modal.
        "prefs_title": "Privacy preferences",
        "prefs_intro": "Choose what you're comfortable with. You can change this at any time.",
        "close": "Close",
        "necessary_title": "Strictly necessary",
        "necessary_state": "Always on",
        "necessary_desc": (
            "Required for the store to work and stay secure. Doesn't build a profile or identify you."
        ),
        "analytics_title": "Analytics & personalization",
        "analytics_desc": (
            "Lets the store understand your visit so it can help you in real time and recommend "
            "products more accurately."
        ),
        "save": "Save choices",
        "cancel": "Cancel",
        # Footer reopen link — lets a shopper change/withdraw consent later (GDPR right to withdraw).
        "privacy_link": "Privacy settings",
    },
    "pl": {
        "aria_label": "Zgoda na pliki cookies i przetwarzanie danych",
        "title": "Zależy nam na Twojej prywatności",
        "body": (
            "Ten sklep używa plików cookies oraz danych o Twoich działaniach, aby działać "
            "poprawnie, pomagać Ci na żywo i trafniej dobierać produkty."
        ),
        "accept_all": "Zaakceptuj wszystko",
        "only_necessary": "Tylko niezbędne",
        "preferences": "Preferencje",
        "prefs_title": "Preferencje prywatności",
        "prefs_intro": "Wybierz, na co się zgadzasz. Możesz to zmienić w dowolnym momencie.",
        "close": "Zamknij",
        "necessary_title": "Niezbędne",
        "necessary_state": "Zawsze aktywne",
        "necessary_desc": (
            "Konieczne, aby sklep działał i był bezpieczny. Nie budują profilu ani Cię nie identyfikują."
        ),
        "analytics_title": "Analiza i personalizacja",
        "analytics_desc": (
            "Pozwalają zrozumieć Twoją wizytę, aby sklep mógł pomagać Ci na żywo i trafniej "
            "dobierać produkty."
        ),
        "save": "Zapisz wybór",
        "cancel": "Anuluj",
        "privacy_link": "Ustawienia prywatności",
    },
}


def _consent_texts():
    """Consent-banner copy in the store's active display language, falling back to English.

    Keyed on Django's active language (set per request by UserLocaleMiddleware), so the banner
    speaks the same language as the rest of the page instead of a hard-coded locale."""
    lang = (translation.get_language() or "en").split("-")[0].lower()
    return _CONSENT_TEXTS.get(lang, _CONSENT_TEXTS["en"])


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
    las_base_url = settings_obj.effective_base_url.rstrip("/")
    return {
        "live_assisted_sales": {
            "enabled": enabled,
            "events_url": "/live-assisted-sales/events/",
            "initial_cart": _initial_cart_payload(request) if enabled else {},
            "customer": _widget_customer_payload(request, settings_obj.store_api_key or "") if enabled else {},
            "site_public_key": settings_obj.site_public_key,
            "consent_region": _consent_region(request) if enabled else "",
            "consent_texts": _consent_texts() if enabled else {},
            "widget_enabled": settings_obj.is_widget_configured,
            "widget_script_url": f"{las_base_url}/widget/v1/chat.js" if las_base_url else "",
            "widget_accent": settings_obj.widget_accent,
            "widget_logo_url": _widget_logo_url(request) if enabled else "",
        }
    }
