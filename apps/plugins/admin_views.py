import re
from pathlib import Path

import markdown
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest
from django.template.response import TemplateResponse

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@staff_member_required
def plugin_developer_guide_view(request: HttpRequest):
    """Standalone admin view — renders HOW_TO_ADD_PLUGIN.md as HTML."""
    guide_path = _PROJECT_ROOT / "docs" / "plugins" / "HOW_TO_ADD_PLUGIN.md"
    if guide_path.exists():
        md_content = guide_path.read_text(encoding="utf-8")
        html_content = markdown.markdown(
            md_content,
            extensions=["tables", "fenced_code", "codehilite", "toc"],
            extension_configs={"codehilite": {"css_class": "highlight", "guess_lang": False}},
        )
        # Strip the first <h1> from the rendered HTML (duplicate of the page title)
        html_content = re.sub(r"^<h1[^>]*>.*?</h1>\s*", "", html_content, count=1, flags=re.DOTALL)
    else:
        html_content = "Developer guide file not found."

    from django.contrib import admin as _admin
    from apps.plugins.models import Plugin

    context = {
        **_admin.site.each_context(request),
        "opts": Plugin._meta,
        "title": "Plugin Developer Guide",
        "guide_html": html_content,
    }
    return TemplateResponse(request, "admin/plugins/plugin/developer_guide.html", context)


