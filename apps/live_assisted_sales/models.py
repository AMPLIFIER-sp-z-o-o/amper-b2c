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

    def clean(self):
        # The store API key (Bearer) and full event payloads (incl. shopper PII) travel to this URL,
        # so it must be https — an http:// endpoint would send the secret + PII in cleartext. Allow
        # plain http only for localhost during development.
        super().clean()
        from urllib.parse import urlparse

        url = (self.las_base_url or "").strip()
        if url:
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            is_local = host in ("localhost", "127.0.0.1", "::1")
            if parsed.scheme != "https" and not is_local:
                from django.core.exceptions import ValidationError

                raise ValidationError(
                    {"las_base_url": _("Use an https:// URL — the API key and customer data must not be sent over http.")}
                )

    @classmethod
    def get_solo(cls):
        # Default the switch ON so a first-time owner's ONLY required action is pasting the API key
        # (nothing is sent until a valid key makes is_configured true, so enabled-without-a-key is
        # an inert, safe state). The toggle stays available to pause LAS later without losing the key.
        obj, _created = cls.objects.get_or_create(pk=1, defaults={"enabled": True})
        return obj

    @property
    def effective_base_url(self):
        """Address of the AMPER LAS platform to talk to. Sourced from the deployment setting
        (LAS_BASE_URL) so the store owner never has to know or enter it — they only paste their API
        key. A per-instance value is honoured only as a legacy/advanced override when the setting is
        unset."""
        from django.conf import settings as django_settings

        configured = getattr(django_settings, "LAS_BASE_URL", "") or self.las_base_url or ""
        return configured.strip()

    @property
    def is_configured(self):
        return bool(self.enabled and self.effective_base_url and self.store_api_key)

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
