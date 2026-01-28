import mimetypes

from django.contrib.admin.views.decorators import staff_member_required
from django.http import FileResponse, Http404
from django.views.decorators.cache import cache_control

from .storage import DynamicMediaStorage

# Register additional MIME types that Python doesn't recognize by default
# These are used by the proxy view for serving files with correct content-type
ADDITIONAL_IMAGE_MIMETYPES = {
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".jxl": "image/jxl",
    ".apng": "image/apng",
}
for ext, mime_type in ADDITIONAL_IMAGE_MIMETYPES.items():
    mimetypes.add_type(mime_type, ext)

# Paths that can be served publicly without authentication
PUBLIC_PATHS = [
    "storefront/",
    "seeds/",
]


def _is_public_path(path):
    """Check if the path should be publicly accessible."""
    return any(path.startswith(prefix) for prefix in PUBLIC_PATHS)


def _serve_file(request, path):
    """
    Internal function to serve files from storage.
    Used by both authenticated and public views.
    """
    storage = DynamicMediaStorage()

    try:
        if not storage.exists(path):
            raise Http404("File not found")
    except Exception:
        raise Http404("File not found")

    # Determine content type - mimetypes now knows about webp, avif, etc.
    content_type, _ = mimetypes.guess_type(path)
    if not content_type:
        content_type = "application/octet-stream"

    # Serve file directly with inline disposition
    # This works for both local and S3 storage
    try:
        file = storage.open(path, "rb")
        response = FileResponse(file, content_type=content_type)
        filename = path.split("/")[-1]
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response
    except Exception:
        raise Http404("File not found")


@cache_control(max_age=86400, public=True)
def view_public_file(request, path):
    """
    Public proxy view for serving files from whitelisted paths.
    No authentication required. Files are cached for 24 hours.
    """
    if not _is_public_path(path):
        raise Http404("File not found")
    return _serve_file(request, path)


@staff_member_required
@cache_control(max_age=3600, public=True)
def view_file(request, path):
    """
    Proxy view to serve files from storage with inline Content-Disposition.
    This ensures files open in browser instead of downloading.
    For S3, we stream the file through Django to have full control over headers.
    Requires staff authentication.
    """
    return _serve_file(request, path)
