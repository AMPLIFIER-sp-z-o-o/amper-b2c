from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

DEFAULT_WIDGET_ACCENT = "#2563eb"

hex_color_validator = RegexValidator(
    regex=r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$",
    message=_("Enter a valid hex colour, e.g. #2563eb."),
)


class LiveAssistedSalesSettings(models.Model):
    enabled = models.BooleanField(_("Enabled"), default=False)
    las_base_url = models.URLField(_("LAS base URL"), max_length=500, blank=True)
    store_api_key = models.CharField(_("Store API key"), max_length=128, blank=True)
    site_public_key = models.CharField(_("Site public key"), max_length=80, blank=True)
    widget_accent_color = models.CharField(
        _("Widget accent colour"),
        max_length=7,
        blank=True,
        validators=[hex_color_validator],
        help_text=_(
            "Hex colour used to theme the chat widget (launcher, header, buttons). "
            "Leave blank to use the store brand colour."
        ),
    )
    last_test_status = models.CharField(_("Last test status"), max_length=32, blank=True)
    last_test_message = models.TextField(_("Last test message"), blank=True)
    last_test_at = models.DateTimeField(_("Last test at"), blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Live Assisted Sales settings")
        verbose_name_plural = _("Live Assisted Sales settings")

    def __str__(self):
        return str(_("Live Assisted Sales settings"))

    @classmethod
    def get_solo(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def is_configured(self):
        return bool(self.enabled and self.las_base_url and self.store_api_key)

    @property
    def is_widget_configured(self):
        return bool(self.is_configured and self.site_public_key)

    @property
    def widget_accent(self):
        return self.widget_accent_color or DEFAULT_WIDGET_ACCENT

    def record_test_result(self, status, message):
        self.last_test_status = status
        self.last_test_message = message
        self.last_test_at = timezone.now()
        self.save(
            update_fields=[
                "site_public_key",
                "last_test_status",
                "last_test_message",
                "last_test_at",
                "updated_at",
            ]
        )


class OutboxEvent(models.Model):
    """Durable transactional outbox for money/truth events (cart + conversion) forwarded to LAS.

    Replaces fire-and-forget for the events whose loss would corrupt analytics or ML labels: the row
    is committed first, then delivered off the request thread, and a periodic relay retries anything
    not confirmed (survives a worker crash or LAS downtime). Downstream is idempotent via the
    (store, event_id) unique constraint, so retries are safe. High-frequency telemetry deliberately
    does NOT use the outbox (see client.DURABLE_EVENT_TYPES) to avoid a DB write per heartbeat.
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        SENT = "sent", _("Sent")
        FAILED = "failed", _("Failed")  # exhausted retries (dead-letter)

    payload = models.JSONField()
    event_type = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"], name="las_outbox_status_idx"),
        ]

    def __str__(self):
        return f"OutboxEvent #{self.pk} {self.event_type} [{self.status}]"
