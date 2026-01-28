from django.contrib.messages.storage.fallback import FallbackStorage


class AdminScopedFallbackStorage(FallbackStorage):
    """
    Tag messages created in /admin/ so they don't leak into public templates.
    """

    def add(self, level, message, extra_tags=""):
        extra_tags = (extra_tags or "").strip()
        if self.request.path.startswith("/admin/"):
            extra_tags = f"{extra_tags} admin".strip()
        return super().add(level, message, extra_tags)
