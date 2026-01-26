"""
Media file synchronization signals.

Automatically creates/updates MediaFile entries when files are uploaded
to any model using DynamicMediaStorage.
"""

import logging
import os
from typing import Any

from django.db import models, transaction
from django.db.models.fields.files import FieldFile
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from apps.media.storage import DynamicMediaStorage

logger = logging.getLogger(__name__)


def _get_file_fields_with_dynamic_storage(model: type[models.Model]) -> list[models.FileField]:
    """Get all FileField/ImageField instances using DynamicMediaStorage."""
    file_fields = []
    for field in model._meta.get_fields():
        if isinstance(field, models.FileField):
            # Check if the field uses DynamicMediaStorage
            if isinstance(field.storage, DynamicMediaStorage):
                file_fields.append(field)
    return file_fields


def _get_image_dimensions(file_field: FieldFile) -> tuple[int | None, int | None]:
    """Try to get image dimensions from file."""
    try:
        from PIL import Image

        file_field.seek(0)
        with Image.open(file_field) as img:
            return img.width, img.height
    except Exception:
        return None, None


def _sync_media_file(
    file_field: FieldFile,
    field_name: str,
    instance: models.Model,
    user: Any | None = None,
) -> None:
    """Create or update a MediaFile entry for the given file."""
    if not file_field or not file_field.name:
        return

    # Avoid circular import
    from apps.media.models import MediaFile

    file_path = file_field.name
    filename = os.path.basename(file_path)

    # Check if MediaFile already exists for this path
    existing = MediaFile.objects.filter(file=file_path).first()
    if existing:
        # Already tracked
        return

    # Detect file type and mime type
    ext = filename.split(".")[-1].lower() if "." in filename else ""

    file_type = _detect_file_type(ext)
    mime_type = _detect_mime_type(ext)

    # Try to get file size - multiple methods for S3 compatibility
    file_size = 0
    try:
        # Method 1: Try file_field.size (works for in-memory files)
        file_size = file_field.size
    except Exception:
        pass

    if not file_size:
        try:
            # Method 2: Try storage.size() - works for django-storages S3
            file_size = file_field.storage.size(file_path)
        except Exception:
            pass

    if not file_size:
        try:
            # Method 3: For S3, try using boto3 head_object directly
            from apps.media.models import MediaStorageSettings

            settings = MediaStorageSettings.get_settings()
            if settings.provider_type == "s3":
                import boto3

                session = boto3.Session(
                    aws_access_key_id=settings.aws_access_key_id,
                    aws_secret_access_key=settings.aws_secret_access_key,
                    region_name=settings.aws_region,
                )
                s3_client = session.client("s3")
                response = s3_client.head_object(
                    Bucket=settings.aws_bucket_name,
                    Key=file_path,
                )
                file_size = response.get("ContentLength", 0)
        except Exception:
            pass

    # Get image dimensions if it's an image
    width, height = None, None
    if file_type == "image":
        try:
            width, height = _get_image_dimensions(file_field)
        except Exception:
            pass

    # Generate title from filename
    name_without_ext = os.path.splitext(filename)[0]
    title = name_without_ext.replace("-", " ").replace("_", " ").title()

    # Determine source model
    model_class = instance.__class__
    source_model = f"{model_class._meta.app_label}.{model_class._meta.model_name}"

    # Create MediaFile entry
    media_file = MediaFile(
        file=file_path,
        filename=filename,
        title=title,
        file_type=file_type,
        mime_type=mime_type,
        file_size=file_size,
        width=width,
        height=height,
        source_model=source_model,
        source_field=field_name,
        source_object_id=instance.pk,
        uploaded_by=user,
    )

    try:
        media_file.save()
        logger.debug(f"Created MediaFile for {file_path} from {source_model}.{field_name}")
    except Exception as e:
        logger.warning(f"Failed to create MediaFile for {file_path}: {e}")


def _detect_file_type(ext: str) -> str:
    """Detect file type based on extension."""
    image_exts = {"jpg", "jpeg", "png", "gif", "webp", "svg", "bmp", "ico", "avif", "heic", "heif"}
    document_exts = {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "csv", "rtf"}
    video_exts = {"mp4", "webm", "avi", "mov", "mkv", "wmv", "flv"}
    audio_exts = {"mp3", "wav", "ogg", "aac", "flac", "m4a"}

    if ext in image_exts:
        return "image"
    elif ext in document_exts:
        return "document"
    elif ext in video_exts:
        return "video"
    elif ext in audio_exts:
        return "audio"
    return "other"


def _detect_mime_type(ext: str) -> str:
    """Detect MIME type based on extension."""
    mime_types = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "webp": "image/webp",
        "svg": "image/svg+xml",
        "avif": "image/avif",
        "heic": "image/heic",
        "heif": "image/heif",
        "pdf": "application/pdf",
        "doc": "application/msword",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xls": "application/vnd.ms-excel",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "mp4": "video/mp4",
        "webm": "video/webm",
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
    }
    return mime_types.get(ext, "application/octet-stream")


def _get_current_user() -> Any | None:
    """Get the current user from middleware's thread-local storage."""
    try:
        from apps.media.middleware import get_current_user

        return get_current_user()
    except Exception:
        return None


# Store old file values to detect changes
_pre_save_file_cache: dict[tuple[type, int, str], str | None] = {}


def handle_pre_save(sender: type[models.Model], instance: models.Model, **kwargs: Any) -> None:
    """Cache the old file values before save to detect changes."""
    if not instance.pk:
        return

    file_fields = _get_file_fields_with_dynamic_storage(sender)
    if not file_fields:
        return

    try:
        old_instance = sender.objects.get(pk=instance.pk)
        for field in file_fields:
            old_file = getattr(old_instance, field.name, None)
            old_path = old_file.name if old_file else None
            cache_key = (sender, instance.pk, field.name)
            _pre_save_file_cache[cache_key] = old_path
    except sender.DoesNotExist:
        pass


def handle_post_save(sender: type[models.Model], instance: models.Model, created: bool, **kwargs: Any) -> None:
    """Sync MediaFile entries for any new or changed files."""
    file_fields = _get_file_fields_with_dynamic_storage(sender)
    if not file_fields:
        return

    user = _get_current_user()

    for field in file_fields:
        current_file = getattr(instance, field.name, None)
        current_path = current_file.name if current_file else None

        if created:
            # New instance - sync if file exists
            if current_path:
                transaction.on_commit(lambda f=current_file, fn=field.name: _sync_media_file(f, fn, instance, user))
        else:
            # Existing instance - check if file changed
            cache_key = (sender, instance.pk, field.name)
            old_path = _pre_save_file_cache.pop(cache_key, None)

            if current_path and current_path != old_path:
                # File was changed - sync new file
                transaction.on_commit(lambda f=current_file, fn=field.name: _sync_media_file(f, fn, instance, user))


def handle_post_delete(sender: type[models.Model], instance: models.Model, **kwargs: Any) -> None:
    """Remove MediaFile entries when source model is deleted."""
    file_fields = _get_file_fields_with_dynamic_storage(sender)
    if not file_fields:
        return

    # Avoid circular import
    from apps.media.models import MediaFile

    for field in file_fields:
        file_field = getattr(instance, field.name, None)
        if file_field and file_field.name:
            # Delete the MediaFile entry for this file path
            try:
                MediaFile.objects.filter(file=file_field.name).delete()
                logger.debug(f"Deleted MediaFile for {file_field.name}")
            except Exception as e:
                logger.warning(f"Failed to delete MediaFile for {file_field.name}: {e}")


def setup_media_sync_signals() -> None:
    """
    Set up signals for all models that use DynamicMediaStorage.
    Called from MediaConfig.ready().
    
    Automatically discovers all models in the project that have FileField/ImageField
    using DynamicMediaStorage - no hardcoding required.
    """
    from django.apps import apps

    # Automatically discover all models with DynamicMediaStorage fields
    for model in apps.get_models():
        # Skip abstract or swapped models
        if model._meta.abstract or model._meta.swapped:
            continue
            
        try:
            file_fields = _get_file_fields_with_dynamic_storage(model)

            if file_fields:
                app_label = model._meta.app_label
                model_name = model._meta.model_name
                
                # Connect signals
                pre_save.connect(
                    handle_pre_save,
                    sender=model,
                    dispatch_uid=f"media_sync_pre_save_{app_label}_{model_name}",
                )
                post_save.connect(
                    handle_post_save,
                    sender=model,
                    dispatch_uid=f"media_sync_post_save_{app_label}_{model_name}",
                )
                post_delete.connect(
                    handle_post_delete,
                    sender=model,
                    dispatch_uid=f"media_sync_post_delete_{app_label}_{model_name}",
                )
                logger.debug(f"Connected media sync signals for {app_label}.{model_name}")
        except Exception as e:
            logger.warning(f"Failed to connect signals for {model}: {e}")

