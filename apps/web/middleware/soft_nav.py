"""
Middleware that strips full-page HTML down to just the #page-content div
for HTMX soft-nav requests (HX-Soft-Nav: true).

On soft-nav the server renders the full page but HTMX only uses #page-content
via hx-select. By extracting that fragment here we cut response size ~50%
without changing any view code.
"""

import re

_DIV_OPEN_RE = re.compile(r"<div\b", re.IGNORECASE)
_DIV_CLOSE_RE = re.compile(r"</div>", re.IGNORECASE)
_PAGE_CONTENT_START_RE = re.compile(r'<div\b[^>]*\bid="page-content"[^>]*>', re.IGNORECASE)


def _extract_page_content(html: str) -> str | None:
    """Return the <div id="page-content">…</div> substring, or None on failure."""
    start_match = _PAGE_CONTENT_START_RE.search(html)
    if not start_match:
        return None

    pos = start_match.end()
    depth = 1

    while pos < len(html) and depth > 0:
        open_match = _DIV_OPEN_RE.search(html, pos)
        close_match = _DIV_CLOSE_RE.search(html, pos)

        if close_match is None:
            break

        if open_match is None or close_match.start() < open_match.start():
            depth -= 1
            pos = close_match.end()
        else:
            depth += 1
            pos = open_match.end()

    if depth == 0:
        return html[start_match.start() : pos]
    return None


class SoftNavResponseMiddleware:
    """
    For requests that carry the ``HX-Soft-Nav: true`` header, replace the full
    HTML response with only the ``#page-content`` fragment.  This halves the
    wire payload without requiring any view-level changes.

    Falls back to the original response silently if extraction fails.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if (
            request.headers.get("HX-Soft-Nav") == "true"
            and response.status_code == 200
            and "text/html" in response.get("Content-Type", "")
            and not getattr(response, "streaming", False)
        ):
            try:
                html = response.content.decode(response.charset or "utf-8")
                fragment = _extract_page_content(html)
                if fragment:
                    encoded = fragment.encode(response.charset or "utf-8")
                    response.content = encoded
                    response["Content-Length"] = len(encoded)
            except Exception:
                # Never break the page — fall back to full response
                pass

        return response
