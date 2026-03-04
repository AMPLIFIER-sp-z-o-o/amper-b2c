from __future__ import annotations

from django.conf import settings
from django.utils.encoding import force_str

from apps.plugins.engine.state import reset_request_budget, set_request_budget_ms


class PluginHTMLInjectionMiddleware:
    """
    Injects plugin UI hook content into HTML responses without requiring
    any template tags in storefront templates.

    Dispatches three filter hooks on every full HTML storefront response:
      - storefront.base.head       → injected just before </head>
      - storefront.base.body.start → injected just after <body ...>
      - storefront.base.body.end   → injected just before </body>

    Each hook callback receives (value, request) and must return an HTML string.
    Only dispatched when at least one plugin has registered a callback for the hook,
    so there is zero overhead when no UI plugins are active.
    HTMX partial requests are skipped — they do not contain full <html> structure.
    """

    SKIP_PREFIXES = ("/admin", "/api", "/media", "/static", "/plugins/webhooks")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if not self._should_process(request, response):
            return response

        from apps.plugins.engine.registry import registry

        has_head = registry.has_filter("storefront.base.head")
        has_body_start = registry.has_filter("storefront.base.body.start")
        has_body_end = registry.has_filter("storefront.base.body.end")

        if not (has_head or has_body_start or has_body_end):
            return response

        content = force_str(response.content, encoding=response.charset or "utf-8")

        if has_head:
            head_html = registry.apply_filters("storefront.base.head", "", request=request)
            if head_html:
                content = content.replace("</head>", head_html + "\n</head>", 1)

        if has_body_start:
            body_start_html = registry.apply_filters("storefront.base.body.start", "", request=request)
            if body_start_html:
                idx = content.find(">", content.find("<body"))
                if idx != -1:
                    content = content[: idx + 1] + "\n" + body_start_html + content[idx + 1 :]

        if has_body_end:
            body_end_html = registry.apply_filters("storefront.base.body.end", "", request=request)
            if body_end_html:
                content = content.replace("</body>", body_end_html + "\n</body>", 1)

        response.content = content.encode(response.charset or "utf-8")
        if "Content-Length" in response:
            response["Content-Length"] = len(response.content)

        return response

    def _should_process(self, request, response) -> bool:
        if response.status_code != 200:
            return False
        if "text/html" not in response.get("Content-Type", ""):
            return False
        path = request.path
        for prefix in self.SKIP_PREFIXES:
            if path.startswith(prefix):
                return False
        # Skip HTMX partial requests — no full <html> structure
        if request.headers.get("HX-Request"):
            return False
        return True


class PluginRequestBudgetMiddleware:
    """Initializes per-request plugin execution budget.

    Budget is consumed by sync hooks in addition to per-hook timeout limits.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        budget_ms = int(getattr(settings, "PLUGIN_REQUEST_BUDGET_MS", 1200))
        token = set_request_budget_ms(budget_ms)
        try:
            return self.get_response(request)
        finally:
            reset_request_budget(token)
