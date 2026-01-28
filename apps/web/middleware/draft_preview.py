from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from django.shortcuts import redirect

from apps.support.draft_utils import build_draft_map, get_active_drafts_for_session, get_draft_session_by_token


class DraftPreviewMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.draft_preview_enabled = False
        request.draft_preview_count = 0
        request.draft_changes = []
        request.draft_changes_map = {}

        if request.path.startswith("/admin/"):
            return self.get_response(request)

        # Only apply drafts when preview_token is explicitly in the URL
        preview_token = request.GET.get("preview_token")
        if preview_token:
            draft_session = get_draft_session_by_token(preview_token)
            if draft_session:
                drafts = get_active_drafts_for_session(draft_session)
                if drafts:
                    request.draft_changes = list(drafts)
                    request.draft_changes_map = build_draft_map(drafts)
                    request.draft_preview_count = len(request.draft_changes)
                    request.draft_preview_enabled = True
                else:
                    # Session exists but has no active drafts (expired)
                    return self._redirect_to_clean_url(request)
            else:
                # Token is invalid or session was already deleted
                return self._redirect_to_clean_url(request)

        return self.get_response(request)

    def _redirect_to_clean_url(self, request):
        """Redirect to the current URL without the preview_token parameter."""
        parsed = urlparse(request.get_full_path())
        query_params = dict(parse_qsl(parsed.query))
        query_params.pop("preview_token", None)

        new_query = urlencode(query_params)
        new_url = urlunparse(parsed._replace(query=new_query))
        return redirect(new_url)
