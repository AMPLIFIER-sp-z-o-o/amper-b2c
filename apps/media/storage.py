"""
Dynamic storage backend for media files.
Selects storage backend based on MediaStorageSettings configuration.
"""

import logging

from django.conf import settings

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

    import boto3
    from botocore.config import Config

    from apps.media.models import MediaStorageSettings

    media_settings = MediaStorageSettings.get_settings()
    if media_settings.provider_type != "s3":
        return None

    if not (
        media_settings.aws_access_key_id
        and media_settings.aws_secret_access_key
        and media_settings.aws_bucket_name
    ):
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


def _build_s3_key(name, settings):
    """Build the full S3 key including aws_location prefix when configured."""
    if not name:
        return name
    location = (settings.aws_location or "").strip("/")
    if not location:
        return name
    if name.startswith(f"{location}/"):
        return name
    return f"{location}/{name}"


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
        For S3, returns a direct public URL (non-expiring).
        """
        try:
            s3_cache = _get_cached_s3_client()
            if s3_cache:
                settings = s3_cache["settings"]
                key = _build_s3_key(name, settings)
                if settings.cdn_enabled and settings.cdn_domain:
                    return settings.get_cdn_url(key)
                return f"https://{settings.aws_bucket_name}.s3.{settings.aws_region}.amazonaws.com/{key}"

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
