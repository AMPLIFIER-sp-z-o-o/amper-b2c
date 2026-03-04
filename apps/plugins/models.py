from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.utils.models import BaseModel


class PluginStatus(models.TextChoices):
    ACTIVATED = "activated", _("Activated")
    DEACTIVATED = "deactivated", _("Deactivated")


class PluginExecutionMode(models.TextChoices):
    LIVE = "live", _("Live")
    SUPERADMIN_ONLY = "superadmin_only", _("Super Admin only")
    IP_ALLOWLIST = "ip_allowlist", _("IP allowlist")



class Plugin(BaseModel):
    slug = models.SlugField(max_length=120, unique=True, verbose_name=_("Slug"))
    name = models.CharField(max_length=255, verbose_name=_("Name"))
    version = models.CharField(max_length=80, verbose_name=_("Version"))
    status = models.CharField(
        max_length=30,
        choices=PluginStatus.choices,
        default=PluginStatus.DEACTIVATED,
        verbose_name=_("Status"),
    )
    package_path = models.CharField(max_length=500, blank=True, default="", verbose_name=_("Package path"))
    entrypoint = models.CharField(max_length=255, default="entrypoint.py", verbose_name=_("Entrypoint"))
    checksum_sha256 = models.CharField(max_length=64, blank=True, default="", verbose_name=_("Checksum SHA256"))
    manifest = models.JSONField(default=dict, blank=True, verbose_name=_("Manifest"))
    config_schema = models.JSONField(default=dict, blank=True, verbose_name=_("Config schema"))
    config = models.JSONField(default=dict, blank=True, verbose_name=_("Config"))
    scopes = models.JSONField(default=list, blank=True, verbose_name=_("Scopes"))
    dependencies = models.JSONField(default=list, blank=True, verbose_name=_("Dependencies"))
    core_version_min = models.CharField(max_length=40, blank=True, default="", verbose_name=_("Core min version"))
    core_version_max = models.CharField(max_length=40, blank=True, default="", verbose_name=_("Core max version"))
    last_error = models.TextField(blank=True, default="", verbose_name=_("Last error"))
    execution_mode = models.CharField(
        max_length=40,
        choices=PluginExecutionMode.choices,
        default=PluginExecutionMode.LIVE,
        verbose_name=_("Execution mode"),
    )
    safe_mode_ip_allowlist = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Safe mode IP allowlist"),
        help_text=_("Comma-separated IPv4/IPv6 addresses allowed when execution mode is IP allowlist."),
    )

    class Meta:
        verbose_name = _("Plugin")
        verbose_name_plural = _("Plugins")
        ordering = ["slug"]

    def __str__(self) -> str:
        return self.name

    @property
    def is_active(self) -> bool:
        return self.status == PluginStatus.ACTIVATED


class PluginMigrationState(BaseModel):
    plugin = models.ForeignKey(
        Plugin,
        related_name="migration_states",
        on_delete=models.CASCADE,
        verbose_name=_("Plugin"),
    )
    version = models.CharField(max_length=80, verbose_name=_("Version"))
    migration_name = models.CharField(max_length=255, verbose_name=_("Migration name"))
    direction = models.CharField(max_length=16, default="up", verbose_name=_("Direction"))
    applied = models.BooleanField(default=False, verbose_name=_("Applied"))

    class Meta:
        verbose_name = _("Plugin migration state")
        verbose_name_plural = _("Plugin migration states")
        unique_together = ("plugin", "version", "migration_name", "direction")


class PluginKVData(BaseModel):
    plugin = models.ForeignKey(
        Plugin,
        related_name="kv_items",
        on_delete=models.CASCADE,
        verbose_name=_("Plugin"),
    )
    namespace = models.CharField(max_length=120, default="default", verbose_name=_("Namespace"))
    key = models.CharField(max_length=255, verbose_name=_("Key"))
    value = models.JSONField(default=dict, blank=True, verbose_name=_("Value"))

    class Meta:
        verbose_name = _("Plugin data item")
        verbose_name_plural = _("Plugin data items")
        unique_together = ("plugin", "namespace", "key")
        indexes = [models.Index(fields=["plugin", "namespace", "key"])]


class PluginWebhookEventStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    PROCESSED = "processed", _("Processed")
    FAILED = "failed", _("Failed")
    DUPLICATE = "duplicate", _("Duplicate")


class PluginWebhookEvent(BaseModel):
    plugin = models.ForeignKey(
        Plugin,
        related_name="webhook_events",
        on_delete=models.CASCADE,
        verbose_name=_("Plugin"),
    )
    provider_event_id = models.CharField(max_length=255, blank=True, default="", verbose_name=_("Provider event ID"))
    payload_hash = models.CharField(max_length=64, verbose_name=_("Payload hash"))
    hook_name = models.CharField(max_length=120, verbose_name=_("Hook"))
    status = models.CharField(
        max_length=20,
        choices=PluginWebhookEventStatus.choices,
        default=PluginWebhookEventStatus.PENDING,
        verbose_name=_("Status"),
    )
    payload = models.JSONField(default=dict, blank=True, verbose_name=_("Payload"))
    processed_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Processed at"))
    error_message = models.TextField(blank=True, default="", verbose_name=_("Error message"))

    class Meta:
        verbose_name = _("Plugin webhook event")
        verbose_name_plural = _("Plugin webhook events")
        indexes = [
            models.Index(fields=["plugin", "hook_name", "status"]),
            models.Index(fields=["plugin", "provider_event_id"]),
            models.Index(fields=["plugin", "payload_hash"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["plugin", "provider_event_id"],
                name="uniq_plugin_provider_event",
                condition=~models.Q(provider_event_id=""),
            ),
            models.UniqueConstraint(fields=["plugin", "payload_hash"], name="uniq_plugin_payload_hash"),
        ]


class PluginLogLevel(models.TextChoices):
    INFO = "info", _("Info")
    WARNING = "warning", _("Warning")
    ERROR = "error", _("Error")


class PluginLog(BaseModel):
    plugin = models.ForeignKey(
        Plugin,
        related_name="logs",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_("Plugin"),
    )
    level = models.CharField(max_length=16, choices=PluginLogLevel.choices, default=PluginLogLevel.INFO)
    event_type = models.CharField(max_length=120, verbose_name=_("Event type"))
    message = models.TextField(verbose_name=_("Message"))
    payload = models.JSONField(default=dict, blank=True, verbose_name=_("Payload"))
    correlation_id = models.CharField(max_length=80, blank=True, default="", verbose_name=_("Correlation ID"))
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="plugin_logs",
        verbose_name=_("User"),
    )

    def __str__(self):
        return f"{self.event_type} ({self.level})"

    class Meta:
        verbose_name = _("Plugin log")
        verbose_name_plural = _("Plugin logs")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["plugin", "event_type", "created_at"])]
