from apps.support.draft_utils import cleanup_expired_drafts


class AdminDraftCleanupMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/admin/") or request.path.startswith("/support/"):
            cleanup_expired_drafts()
        return self.get_response(request)
