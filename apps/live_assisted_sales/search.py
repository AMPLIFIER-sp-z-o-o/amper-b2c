"""Product search this storefront answers for LAS (2026-08-13).

An agent helping a shopper in the LAS console types a few letters and must see products from THIS
shop's real catalogue - not only the ones some shopper happened to view earlier. LAS therefore asks
the shop, and the shop answers with what it would show that shopper itself.

The request is signed, never keyed: LAS sends a timestamp plus an HMAC of "<timestamp>.<body>"
computed with the store API key both sides already share, so the secret never travels and a captured
request cannot be replayed later.
"""

import hashlib
import hmac
import json
import time

from django.conf import settings

from apps.catalog.models import VISIBLE_STATUSES, Product

from .events import product_payload

SIGNATURE_HEADER = "HTTP_X_AMPER_SIGNATURE"
TIMESTAMP_HEADER = "HTTP_X_AMPER_TIMESTAMP"
# Tolerates ordinary clock drift between LAS and this host while keeping a replay window small.
SIGNATURE_MAX_AGE_SECONDS = 300
MAX_RESULTS = 24


def expected_signature(secret, timestamp, body):
    payload = f"{timestamp}.".encode() + (body or b"")
    digest = hmac.new(str(secret or "").encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def signature_is_valid(request, secret):
    """True when this request really came from LAS and is fresh.

    Compared with ``compare_digest`` so a wrong signature cannot be discovered byte by byte through
    response timing, and refused outright without a configured secret - an unconfigured integration
    must never accidentally expose the catalogue.
    """
    if not secret:
        return False
    timestamp = request.META.get(TIMESTAMP_HEADER, "")
    signature = request.META.get(SIGNATURE_HEADER, "")
    if not timestamp or not signature:
        return False
    try:
        age = abs(time.time() - int(timestamp))
    except (TypeError, ValueError):
        return False
    if age > SIGNATURE_MAX_AGE_SECONDS:
        return False
    return hmac.compare_digest(signature, expected_signature(secret, timestamp, request.body))


def parse_search_request(body):
    """The query and result cap LAS asked for; malformed input searches for nothing."""
    try:
        data = json.loads((body or b"").decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    query = " ".join(str(data.get("query") or "").split())[:120]
    try:
        limit = int(data.get("limit") or MAX_RESULTS)
    except (TypeError, ValueError):
        limit = MAX_RESULTS
    return {"query": query, "limit": max(1, min(limit, MAX_RESULTS))}


def search_products(query, limit=MAX_RESULTS, request=None):
    """Products matching ``query`` that a shopper of this storefront may actually see.

    Scoped to ``VISIBLE_STATUSES`` - the same rule the storefront listing uses - so an agent can
    never send a hidden product into a chat. Prices are identical for every shopper here (no B2B
    contract pricing at this tier), so the buyer's identity does not change the answer.
    """
    if not query:
        return []
    products = (
        Product.objects.filter(status__in=VISIBLE_STATUSES)
        .filter(name__icontains=query)
        .select_related("category")
        .order_by("name")[:limit]
    )
    results = []
    for product in products:
        payload = product_payload(product, request=request)
        results.append(
            {
                "id": payload.get("id", ""),
                "name": payload.get("name", ""),
                "sku": payload.get("sku", ""),
                "url": payload.get("url", ""),
                "image": payload.get("image", ""),
                # The formatted price is what the shopper card shows; the raw number is meaningless
                # to a reader without the currency.
                "price": payload.get("price_display", ""),
                "availability": "out_of_stock" if product.is_unavailable else "in_stock",
            }
        )
    return results


def search_endpoint_url(request=None):
    """Absolute URL of this storefront's search endpoint, announced to LAS on connection.

    LAS stays platform-neutral by storing whatever URL an integration reports, so the shop - not
    LAS - decides where it answers. The address comes from the same place order e-mails take theirs
    (the owner-set site URL), falling back to the deployment's front-end address and finally to the
    current request, so a shop that never filled the field still announces something reachable.
    """
    from apps.web.models import SiteSettings

    base = ""
    try:
        base = str(SiteSettings.get_settings().site_url or "").strip()
    except Exception:
        base = ""
    if not base:
        base = str(getattr(settings, "FRONTEND_ADDRESS", "") or "").strip()
    if not base and request is not None and hasattr(request, "build_absolute_uri"):
        base = request.build_absolute_uri("/")
    base = base.rstrip("/")
    if not base.startswith(("http://", "https://")):
        return ""
    return f"{base}/live-assisted-sales/product-search/"
