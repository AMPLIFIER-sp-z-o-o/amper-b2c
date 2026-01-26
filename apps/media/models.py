"""
Media Storage Models
Simple singleton model for configuring S3 storage and CDN settings.
Also includes MediaFile for tracking all media files in the system.
"""

import os
import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.media.encryption import EncryptedCharField
from apps.media.storage import DynamicMediaStorage
from apps.utils.models import BaseModel

# =============================================================================
# Media File Models
# =============================================================================


def media_file_path(instance, filename):
    """Generate unique filename for uploaded media files."""
    ext = filename.split(".")[-1].lower()
    unique_name = f"{uuid.uuid4()}.{ext}"
    return f"media_library/{instance.file_type}/{unique_name}"


class MediaFile(BaseModel):
    """
    Media file with metadata for the media library.
    Tracks all uploaded files in the system.
    """

    FILE_TYPE_CHOICES = [
        ("image", _("Image")),
        ("document", _("Document")),
        ("video", _("Video")),
        ("audio", _("Audio")),
        ("other", _("Other")),
    ]

    file = models.FileField(_("file"), upload_to=media_file_path, storage=DynamicMediaStorage())
    filename = models.CharField(_("filename"), max_length=255)
    title = models.CharField(_("title"), max_length=200, blank=True)
    alt_text = models.CharField(
        _("alt text"),
        max_length=200,
        blank=True,
        help_text=_("Alternative text for accessibility (required for images)"),
    )
    description = models.TextField(_("description"), blank=True)

    file_type = models.CharField(
        _("file type"),
        max_length=20,
        choices=FILE_TYPE_CHOICES,
        default="other",
        db_index=True,
    )
    mime_type = models.CharField(_("MIME type"), max_length=100, blank=True)
    file_size = models.PositiveIntegerField(_("file size"), default=0, help_text=_("Size in bytes"))



    # Image-specific fields
    width = models.PositiveIntegerField(_("width"), null=True, blank=True)
    height = models.PositiveIntegerField(_("height"), null=True, blank=True)

    # Source tracking - which model/field this file came from
    source_model = models.CharField(
        _("source model"),
        max_length=100,
        blank=True,
        db_index=True,
        help_text=_("The model this file was uploaded from (e.g., 'homepage.Banner')"),
    )
    source_field = models.CharField(
        _("source field"),
        max_length=100,
        blank=True,
        help_text=_("The field name this file was uploaded to (e.g., 'image')"),
    )
    source_object_id = models.PositiveIntegerField(
        _("source object ID"),
        null=True,
        blank=True,
        db_index=True,
        help_text=_("The primary key of the source object"),
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_media_files",
        verbose_name=_("uploaded by"),
    )

    class Meta:
        verbose_name = _("media file")
        verbose_name_plural = _("media files")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["file_type", "-created_at"]),
        ]

    def __str__(self):
        return self.title or self.filename

    def save(self, *args, **kwargs):
        # Set original filename if not provided
        if not self.filename and self.file:
            self.filename = os.path.basename(self.file.name)

        # Set title from filename if not provided
        if not self.title:
            name_without_ext = os.path.splitext(self.filename)[0]
            self.title = name_without_ext.replace("-", " ").replace("_", " ").title()

        # Detect file type from extension for new files
        if self.file and not self.pk:
            ext = self.file.name.split(".")[-1].lower()
            self.file_type = self._detect_file_type(ext)
            self.mime_type = self._detect_mime_type(ext)

        super().save(*args, **kwargs)

    def _detect_file_type(self, ext):
        """Detect file type based on extension."""
        image_exts = {"jpg", "jpeg", "png", "gif", "webp", "svg", "bmp", "ico"}
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

    def _detect_mime_type(self, ext):
        """Detect MIME type based on extension."""
        mime_types = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "webp": "image/webp",
            "svg": "image/svg+xml",
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

    @property
    def file_size_display(self):
        """Return human-readable file size."""
        size = self.file_size
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    @property
    def dimensions(self):
        """Return image dimensions as 'WxH' string or None."""
        if self.width and self.height:
            return f"{self.width}x{self.height}"
        return None

    @property
    def is_image(self):
        return self.file_type == "image"

    @property
    def url(self):
        """Return file URL - uses CDN if configured, otherwise S3 or local."""
        return self.get_full_url()

    def get_full_url(self, expires_in=3600):
        """
        Generate full URL for the file based on storage settings.
        For S3, generates a presigned URL that expires in expires_in seconds.
        Uses cached S3 client for performance.
        """
        if not self.file:
            return None

        from apps.media.storage import _get_cached_s3_client

        # Try cached S3 client first for performance
        s3_cache = _get_cached_s3_client()
        if s3_cache:
            file_path = str(self.file)
            try:
                presigned_url = s3_cache["client"].generate_presigned_url(
                    "get_object",
                    Params={
                        "Bucket": s3_cache["bucket"],
                        "Key": file_path,
                        "ResponseContentDisposition": "inline",
                    },
                    ExpiresIn=expires_in,
                )
                return s3_cache["settings"].get_cdn_url(presigned_url)
            except Exception:
                # Fallback to direct S3 URL if presigning fails
                settings = s3_cache["settings"]
                return f"https://{settings.aws_bucket_name}.s3.{settings.aws_region}.amazonaws.com/{file_path}"

        # Local storage - use Django's default URL
        return self.file.url if self.file else None

    def get_download_url(self, expires_in=3600):
        """
        Generate a download URL for the file.
        For S3, generates a presigned URL with Content-Disposition=attachment.
        Uses cached S3 client for performance.
        """
        if not self.file:
            return None

        from apps.media.storage import _get_cached_s3_client

        s3_cache = _get_cached_s3_client()
        if s3_cache:
            file_path = str(self.file)
            filename = (self.filename or "").replace("\"", "")
            if not filename:
                filename = file_path.split("/")[-1]

            try:
                presigned_url = s3_cache["client"].generate_presigned_url(
                    "get_object",
                    Params={
                        "Bucket": s3_cache["bucket"],
                        "Key": file_path,
                        "ResponseContentDisposition": f'attachment; filename="{filename}"',
                        "ResponseContentType": self.mime_type or "application/octet-stream",
                    },
                    ExpiresIn=expires_in,
                )
                return presigned_url
            except Exception:
                return self.file.url

        return self.file.url

    @property
    def extension(self):
        """Return file extension."""
        if self.filename:
            return self.filename.split(".")[-1].upper()
        return ""


# =============================================================================
# Storage Settings Model
# =============================================================================


class MediaStorageSettings(BaseModel):
    """
    Singleton model for media storage configuration.
    Supports local filesystem or Amazon S3 storage with optional CDN.
    """

    PROVIDER_TYPE_CHOICES = [
        ("local", _("Local Server Storage")),
        ("s3", _("Amazon S3")),
    ]

    AWS_REGION_CHOICES = [
        ("us-east-1", "US East (N. Virginia)"),
        ("us-east-2", "US East (Ohio)"),
        ("us-west-1", "US West (N. California)"),
        ("us-west-2", "US West (Oregon)"),
        ("eu-west-1", "EU (Ireland)"),
        ("eu-west-2", "EU (London)"),
        ("eu-west-3", "EU (Paris)"),
        ("eu-central-1", "EU (Frankfurt)"),
        ("eu-north-1", "EU (Stockholm)"),
        ("ap-northeast-1", "Asia Pacific (Tokyo)"),
        ("ap-northeast-2", "Asia Pacific (Seoul)"),
        ("ap-southeast-1", "Asia Pacific (Singapore)"),
        ("ap-southeast-2", "Asia Pacific (Sydney)"),
        ("ap-south-1", "Asia Pacific (Mumbai)"),
        ("sa-east-1", "South America (São Paulo)"),
        ("ca-central-1", "Canada (Central)"),
    ]

    # Basic Settings
    provider_type = models.CharField(
        _("storage type"),
        max_length=20,
        choices=PROVIDER_TYPE_CHOICES,
        default="local",
    )

    # S3 Configuration
    aws_access_key_id = models.CharField(
        _("AWS Access Key ID"),
        max_length=200,
        blank=True,
    )
    aws_secret_access_key = EncryptedCharField(
        _("AWS Secret Access Key"),
        max_length=500,
        blank=True,
    )
    aws_bucket_name = models.CharField(
        _("bucket name"),
        max_length=63,
        blank=True,
    )
    aws_region = models.CharField(
        _("AWS region"),
        max_length=30,
        choices=AWS_REGION_CHOICES,
        default="eu-central-1",
    )
    aws_location = models.CharField(
        _("storage path"),
        max_length=200,
        default="media",
        blank=True,
    )

    # CDN Configuration
    cdn_enabled = models.BooleanField(
        _("enable CDN"),
        default=False,
    )
    cdn_domain = models.CharField(
        _("CDN domain"),
        max_length=255,
        blank=True,
    )

    class Meta:
        verbose_name = _("Media Storage Settings")
        verbose_name_plural = _("Media Storage Settings")

    def __str__(self):
        return f"Media Storage: {self.get_provider_type_display()}"

    def save(self, *args, **kwargs):
        # Singleton pattern - ensure only one instance
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_settings(cls):
        """Get or create the singleton settings instance."""
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

    def get_storage_backend(self):
        """Return the appropriate storage backend."""
        if self.provider_type == "local":
            return None

        if self.provider_type == "s3":
            # Don't initialize S3 if essentials are missing
            if not self.aws_access_key_id or not self.aws_secret_access_key or not self.aws_bucket_name:
                return None

            from storages.backends.s3boto3 import S3Boto3Storage

            # Always use signed URLs for private S3 buckets
            # CDN only works with public-read buckets which is not our case
            # AWS_QUERYSTRING_AUTH=True by default
            storage_options = {
                "access_key": self.aws_access_key_id,
                "secret_key": self.aws_secret_access_key,
                "bucket_name": self.aws_bucket_name,
                "region_name": self.aws_region,
                "location": self.aws_location,
                "file_overwrite": False,
                "querystring_auth": True,  # Always use signed URLs
                "signature_version": "s3v4",
                "object_parameters": {
                    "ContentDisposition": "inline",
                },
                # Don't set custom_domain - let S3 generate presigned URLs directly
            }

            return S3Boto3Storage(**storage_options)

        return None

    def test_connection(self):
        """Test the S3 connection."""
        if self.provider_type != "s3":
            return True, _("Local storage is always available.")

        import boto3
        from botocore.exceptions import ClientError, NoCredentialsError

        if not self.aws_secret_access_key:
            return False, _("AWS Secret Access Key is required.")

        try:
            session = boto3.Session(
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
                region_name=self.aws_region,
            )
            s3 = session.client("s3")
            s3.head_bucket(Bucket=self.aws_bucket_name)
            return True, _("Connection successful! Bucket is accessible.")

        except NoCredentialsError:
            return False, _("Invalid AWS credentials.")
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "403":
                return False, _("Access denied. Check your credentials and bucket permissions.")
            elif error_code == "404":
                return False, _("Bucket not found. Check the bucket name.")
            return False, f"{_('AWS Error')}: {error_code}"
        except Exception as e:
            return False, f"{_('Connection failed')}: {str(e)}"

    def get_cdn_url(self, path):
        """Transform a media path to CDN URL if CDN is enabled."""
        if not self.cdn_enabled or not self.cdn_domain:
            return path

        if "://" in path:
            from urllib.parse import urlparse

            parsed_url = urlparse(path)
            path = parsed_url.path

        if path.startswith("/"):
            path = path[1:]

        return f"https://{self.cdn_domain}/{path}"
