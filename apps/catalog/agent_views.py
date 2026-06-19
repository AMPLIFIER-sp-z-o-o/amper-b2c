"""LAS-7 B2 — agent-ready storefront: make the catalog discoverable and queryable by AI shopping
agents (ChatGPT, Gemini, Perplexity, Amazon Rufus, …) the way Shopify auto-shipped to every store in
2026. As shoppers increasingly route through AI agents, a storefront that is invisible to them loses
the journey; these endpoints turn that structural threat into distribution.

Three read-only surfaces, all public (no PII, just the published catalog):

* ``/llms.txt``            — a plain-text primer telling an agent what this store is and where the
                             machine-readable surfaces live (the emerging llms.txt convention).
* ``/.well-known/ucp.json`` — a UCP-style capability manifest (merchant info + what an agent can do).
* ``/api/agent/mcp/``       — a JSON-RPC 2.0 Model Context Protocol server exposing read-only tools
                             (search / get product / related products + availability).

Deliberately READ-ONLY and human-in-the-loop: we expose discovery, NOT agentic checkout (which
collapsed as a category in 2026) — purchase stays with the human-assisted flow. EU-sovereign: it is
an open, self-hosted protocol with no US-cloud dependency.
"""

import json

from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.catalog.models import VISIBLE_STATUSES, Product

# MCP protocol version we speak (date-based, per the spec).
MCP_PROTOCOL_VERSION = "2025-06-18"
MAX_RESULTS = 24


def _store_name():
    try:
        from apps.web.models import SiteSettings

        site_settings = SiteSettings.get_settings()
        if site_settings and getattr(site_settings, "store_name", ""):
            return site_settings.store_name
    except Exception:
        pass
    try:
        return settings.PROJECT_METADATA.get("NAME", "Sklep")
    except Exception:
        return "Sklep"


def _currency():
    try:
        from apps.web.models import SiteSettings

        site_settings = SiteSettings.get_settings()
        if site_settings and getattr(site_settings, "currency", ""):
            return str(site_settings.currency)
    except Exception:
        pass
    return ""


def _visible_products():
    return Product.objects.filter(status__in=VISIBLE_STATUSES)


def _search_query(query):
    q = Q()
    term = (query or "").strip()
    if not term:
        return q
    return (
        Q(name__icontains=term)
        | Q(description__icontains=term)
        | Q(category__name__icontains=term)
        | Q(category__slug__icontains=term)
    )


def _clamp_limit(value, default=12):
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(MAX_RESULTS, limit))


def _serialize_product(product, request, *, detail=False):
    data = {
        "id": product.id,
        "name": product.name,
        "slug": product.slug,
        "url": request.build_absolute_uri(product.get_absolute_url()),
        "price": float(product.price),
        "currency": _currency(),
        "in_stock": not product.is_unavailable,
        "availability": str(product.availability_label),
        "category": product.category.name if product.category_id else "",
    }
    if detail:
        # CKEditor HTML stripped to a plain, agent-friendly summary.
        from django.utils.html import strip_tags

        data["description"] = strip_tags(product.description or "").strip()[:2000]
        data["attributes"] = [
            {"name": attribute.get("attribute_name", ""), "value": attribute.get("full_value", "")}
            for attribute in (product.display_attributes or [])
        ]
    return data


def _search_products(request, query, limit):
    products = (
        _visible_products()
        .filter(_search_query(query))
        .select_related("category")
        .distinct()
        .order_by("-sales_total", "name")[: _clamp_limit(limit)]
    )
    return [_serialize_product(product, request) for product in products]


def _get_product(request, *, product_id=None, slug=None):
    products = _visible_products().select_related("category")
    product = None
    if product_id:
        product = products.filter(id=product_id).first()
    if product is None and slug:
        product = products.filter(slug=slug).first()
    return _serialize_product(product, request, detail=True) if product else None


def _related_products(request, *, product_id=None, slug=None, limit=6):
    """Related products for an item. v1 uses same-category popularity (the store's own sales) as an
    honest, self-contained signal; the LAS intelligence layer's co-purchase/sequence affinity is the
    cross-service enrichment that slots in here next."""
    base = _visible_products()
    product = None
    if product_id:
        product = base.filter(id=product_id).first()
    if product is None and slug:
        product = base.filter(slug=slug).first()
    if product is None or not product.category_id:
        return []
    related = (
        base.filter(category_id=product.category_id)
        .exclude(id=product.id)
        .select_related("category")
        .order_by("-sales_total", "name")[: _clamp_limit(limit, default=6)]
    )
    return [_serialize_product(item, request) for item in related]


# --- agent-discovery surfaces -----------------------------------------------------------------

def llms_txt(request):
    """The llms.txt primer an AI agent reads first."""
    base = request.build_absolute_uri("/").rstrip("/")
    name = _store_name()
    lines = [
        f"# {name}",
        "",
        f"> {name} to sklep internetowy. Ta strona udostępnia ustrukturyzowane dane dla asystentów AI.",
        "",
        "## Dla agentów AI",
        f"- Manifest możliwości (UCP): {base}/.well-known/ucp.json",
        f"- Serwer MCP (read-only, JSON-RPC 2.0): {base}/api/agent/mcp/",
        f"- Mapa strony: {base}/sitemap.xml",
        "",
        "## Co możesz zrobić",
        "- Wyszukiwać produkty, pobierać szczegóły i dostępność, oraz produkty powiązane.",
        "- Zakup i finalizacja zamówienia odbywają się z udziałem człowieka (obsługa klienta na żywo),",
        "  zgodnie z zasadami EU (human-in-the-loop). Nie udostępniamy automatycznego checkoutu agentowego.",
        "",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


def ucp_manifest(request):
    """A UCP-style capability manifest served at /.well-known/ucp.json."""
    base = request.build_absolute_uri("/").rstrip("/")
    manifest = {
        "ucp_version": "0.1",
        "merchant": {"name": _store_name(), "url": base + "/", "currency": _currency()},
        "capabilities": {
            "catalog": True,
            "search": True,
            "product_detail": True,
            "availability": True,
            "recommendations": True,
            # Honest about the human-in-the-loop posture: discovery yes, agentic checkout no.
            "agentic_checkout": False,
            "human_assisted_checkout": True,
        },
        "endpoints": {
            "mcp": base + "/api/agent/mcp/",
            "search": base + "/api/agent/catalog/search/",
            "sitemap": base + "/sitemap.xml",
            "llms_txt": base + "/llms.txt",
        },
        "protocols": {"mcp": MCP_PROTOCOL_VERSION},
    }
    return JsonResponse(manifest)


@require_http_methods(["GET"])
def agent_catalog_search(request):
    """Plain REST product search for agents that don't speak MCP."""
    query = request.GET.get("q", "")
    limit = request.GET.get("limit")
    return JsonResponse({"query": query, "results": _search_products(request, query, limit)})


# --- MCP server -------------------------------------------------------------------------------

def _mcp_tools():
    return [
        {
            "name": "search_products",
            "description": "Wyszukaj produkty w sklepie po nazwie, opisie lub kategorii.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Szukana fraza."},
                    "limit": {"type": "integer", "description": "Maks. liczba wyników (1-24)."},
                },
                "required": ["query"],
            },
        },
        {
            "name": "get_product",
            "description": "Pobierz szczegóły i dostępność produktu po id lub slug.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "slug": {"type": "string"},
                },
            },
        },
        {
            "name": "related_products",
            "description": "Produkty powiązane (klienci często oglądają je razem) dla danego produktu.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "slug": {"type": "string"},
                    "limit": {"type": "integer"},
                },
            },
        },
    ]


def _mcp_call_tool(request, name, arguments):
    arguments = arguments or {}
    if name == "search_products":
        return {"results": _search_products(request, arguments.get("query", ""), arguments.get("limit"))}
    if name == "get_product":
        product = _get_product(request, product_id=arguments.get("id"), slug=arguments.get("slug"))
        if product is None:
            return None
        return {"product": product}
    if name == "related_products":
        return {
            "results": _related_products(
                request,
                product_id=arguments.get("id"),
                slug=arguments.get("slug"),
                limit=arguments.get("limit", 6),
            )
        }
    raise KeyError(name)


def _jsonrpc_result(request_id, result):
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _jsonrpc_error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


@csrf_exempt
@require_http_methods(["GET", "POST"])
def agent_mcp(request):
    """Read-only Model Context Protocol (JSON-RPC 2.0) server for this store's catalog.

    Implements ``initialize``, ``tools/list`` and ``tools/call``. A GET returns a small descriptor so
    the endpoint is human-inspectable. No writes, no PII — just the published catalog."""
    if request.method == "GET":
        return JsonResponse(
            {
                "name": "amper-storefront-mcp",
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "transport": "json-rpc-2.0-over-http",
                "tools": [tool["name"] for tool in _mcp_tools()],
                "readOnly": True,
            }
        )

    try:
        payload = json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        return JsonResponse(_jsonrpc_error(None, -32700, "Parse error"), status=400)

    request_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") or {}

    if method == "initialize":
        return JsonResponse(
            _jsonrpc_result(
                request_id,
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "amper-storefront-mcp", "version": "1.0.0"},
                    "instructions": (
                        "Read-only catalog access for an AI shopping agent. Purchase is human-assisted; "
                        "this server only helps discover products and availability."
                    ),
                },
            )
        )
    if method in ("notifications/initialized", "ping"):
        return JsonResponse(_jsonrpc_result(request_id, {}))
    if method == "tools/list":
        return JsonResponse(_jsonrpc_result(request_id, {"tools": _mcp_tools()}))
    if method == "tools/call":
        tool_name = params.get("name")
        try:
            output = _mcp_call_tool(request, tool_name, params.get("arguments"))
        except KeyError:
            return JsonResponse(_jsonrpc_error(request_id, -32602, f"Unknown tool: {tool_name}"), status=400)
        if output is None:
            return JsonResponse(
                _jsonrpc_result(
                    request_id,
                    {"content": [{"type": "text", "text": "Nie znaleziono."}], "isError": True},
                )
            )
        # MCP tool results carry a content array; we include both human text and structured JSON.
        return JsonResponse(
            _jsonrpc_result(
                request_id,
                {
                    "content": [{"type": "text", "text": json.dumps(output, ensure_ascii=False)}],
                    "structuredContent": output,
                },
            )
        )
    return JsonResponse(_jsonrpc_error(request_id, -32601, f"Method not found: {method}"), status=400)
