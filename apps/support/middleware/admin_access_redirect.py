from django.shortcuts import redirect


class AdminAccessRedirectMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path or ""
        user = getattr(request, "user", None)

        if path.startswith("/admin/") and user and user.is_authenticated and not user.is_superuser:
            return redirect("web:home")

        return self.get_response(request)
