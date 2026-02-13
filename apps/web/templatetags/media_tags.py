from django import template
from django.conf import settings

from apps.media.storage import DynamicMediaStorage

register = template.Library()


@register.simple_tag
def media_file_url(path):
    """Return URL for a media path using active storage backend (S3/local)."""
    if not path:
        return ""

    relative_path = str(path).lstrip("/")
    if relative_path.startswith("media/"):
        relative_path = relative_path[len("media/") :]

    try:
        return DynamicMediaStorage().url(relative_path)
    except Exception:
        return f"{settings.MEDIA_URL}{relative_path}"
