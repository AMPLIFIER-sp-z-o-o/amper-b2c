from .draft_preview_links import build_preview_links
from .draft_utils import get_active_drafts_for_session
from .models import DraftSession


def _get_admin_draft_links(request) -> list[dict[str, str]]:
    if not request or not request.path.startswith("/admin/"):
        return []
    user = getattr(request, "user", None)
    if not user or not user.is_staff:
        return []
    session_key = getattr(getattr(request, "session", None), "session_key", None)
    if not session_key:
        return []

    draft_session = DraftSession.objects.filter(session_key=session_key).first()
    if not draft_session:
        return []
    admin_change_url = request.get_full_path()
    drafts = get_active_drafts_for_session(draft_session).filter(admin_change_url=admin_change_url)
    if not drafts:
        return []
    return build_preview_links(drafts)


def admin_extra_userlinks(request):
    return {
        "draft_preview_links": _get_admin_draft_links(request),
    }


def draft_preview(request):
    return {
        "draft_preview_enabled": getattr(request, "draft_preview_enabled", False),
        "draft_preview_count": getattr(request, "draft_preview_count", 0),
    }
