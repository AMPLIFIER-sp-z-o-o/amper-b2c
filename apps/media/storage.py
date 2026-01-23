"""
Dynamic storage backend for media files.
Selects storage backend based on MediaStorageSettings configuration.
"""

import logging
import mimetypes

from django.conf import settings

# Register additional MIME types that Python doesn't recognize by default
# This ensures S3 presigned URLs get the correct ResponseContentType
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
from django.core.files.storage import FileSystemStorage
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

# Cache for storage backend instances and S3 client
_storage_cache = {}
_s3_client_cache = {}


def clear_storage_cache():
    """Clear the storage backend cache. Called when settings change."""
    global _storage_cache, _s3_client_cache
    _storage_cache.clear()
    _s3_client_cache.clear()
    logger.debug("Storage cache cleared")


def _get_cached_s3_client():
    """
    Get a cached S3 client. Creating boto3 sessions is expensive (~100-200ms),
    so we cache the client for reuse.
    """
    cache_key = "s3_client"
    if cache_key in _s3_client_cache:
        return _s3_client_cache[cache_key]

    from apps.media.models import MediaStorageSettings

    import boto3
    from botocore.config import Config

    media_settings = MediaStorageSettings.get_settings()
    if media_settings.provider_type != "s3":
        return None

    session = boto3.Session(
        aws_access_key_id=media_settings.aws_access_key_id,
        aws_secret_access_key=media_settings.aws_secret_access_key,
        region_name=media_settings.aws_region,
    )

    config = Config(
        signature_version="s3v4",
        s3={"addressing_style": "virtual"},
    )

    client = session.client(
        "s3",
        endpoint_url=f"https://s3.{media_settings.aws_region}.amazonaws.com",
        config=config,
    )

    _s3_client_cache[cache_key] = {
        "client": client,
        "bucket": media_settings.aws_bucket_name,
        "settings": media_settings,
    }

    return _s3_client_cache[cache_key]


def get_active_storage():
    """
    Get the appropriate storage backend based on MediaStorageSettings.

    Returns:
        Storage backend instance (S3Boto3Storage or FileSystemStorage)
    """
    from apps.media.models import MediaStorageSettings

    # Check cache first
    cache_key = "active_storage"
    if cache_key in _storage_cache:
        return _storage_cache[cache_key]

    try:
        media_settings = MediaStorageSettings.get_settings()

        if media_settings.provider_type == "local":
            storage = FileSystemStorage(
                location=str(settings.MEDIA_ROOT),
                base_url=settings.MEDIA_URL,
            )
        elif media_settings.provider_type == "s3":
            storage = media_settings.get_storage_backend()
            if storage is None:
                # S3 selected but not fully configured yet (e.g. initial setup)
                # Fallback to local storage silently
                storage = FileSystemStorage(
                    location=str(settings.MEDIA_ROOT),
                    base_url=settings.MEDIA_URL,
                )
            # If we got a backend, it's already configured
        else:
            storage = FileSystemStorage(
                location=str(settings.MEDIA_ROOT),
                base_url=settings.MEDIA_URL,
            )

        _storage_cache[cache_key] = storage
        return storage

    except Exception as e:
        logger.error(f"Error getting active storage: {e}")
        return FileSystemStorage(
            location=str(settings.MEDIA_ROOT),
            base_url=settings.MEDIA_URL,
        )


class DynamicMediaStorage(FileSystemStorage):
    """
    A storage class that dynamically selects the appropriate backend
    based on the MediaStorageSettings configuration.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _get_storage(self):
        """Get the active storage backend."""
        return get_active_storage()

    def _open(self, name, mode="rb"):
        return self._get_storage()._open(name, mode)

    def _save(self, name, content):
        return self._get_storage()._save(name, content)

    def delete(self, name):
        return self._get_storage().delete(name)

    def exists(self, name):
        return self._get_storage().exists(name)

    def listdir(self, path):
        return self._get_storage().listdir(path)

    def size(self, name):
        return self._get_storage().size(name)

    def url(self, name, inline=True):
        """
        Get URL for the file.
        For S3, generates a presigned URL with response-content-disposition.
        Uses cached S3 client for performance.
        """
        try:
            s3_cache = _get_cached_s3_client()
            if s3_cache:
                # Use cached S3 client for fast presigned URL generation
                params = {
                    "Bucket": s3_cache["bucket"],
                    "Key": name,
                }
                if inline:
                    params["ResponseContentDisposition"] = "inline"
                    content_type, _ = mimetypes.guess_type(name)
                    if content_type:
                        params["ResponseContentType"] = content_type

                presigned_url = s3_cache["client"].generate_presigned_url(
                    "get_object",
                    Params=params,
                    ExpiresIn=3600,
                )

                return s3_cache["settings"].get_cdn_url(presigned_url)

            # For local storage, use default URL generation
            storage = self._get_storage()
            return storage.url(name)

        except Exception:
            storage = self._get_storage()
            return storage.url(name)

    def get_accessed_time(self, name):
        return self._get_storage().get_accessed_time(name)

    def get_created_time(self, name):
        return self._get_storage().get_created_time(name)

    def get_modified_time(self, name):
        return self._get_storage().get_modified_time(name)


def setup_storage_signals():
    """
    Set up signal handlers to clear storage cache when settings change.
    Called from AppConfig.ready()
    """
    from apps.media.models import MediaStorageSettings

    @receiver(post_save, sender=MediaStorageSettings)
    def on_settings_save(sender, instance, **kwargs):
        clear_storage_cache()

    @receiver(post_delete, sender=MediaStorageSettings)
    def on_settings_delete(sender, instance, **kwargs):
        clear_storage_cache()
