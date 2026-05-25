from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class LiveAssistedSalesSettings(models.Model):
    enabled = models.BooleanField(_("Enabled"), default=False)
    las_base_url = models.URLField(_("LAS base URL"), max_length=500, blank=True)
    store_api_key = models.CharField(_("Store API key"), max_length=128, blank=True)
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

    def record_test_result(self, status, message):
        self.last_test_status = status
        self.last_test_message = message
        self.last_test_at = timezone.now()
        self.save(update_fields=["last_test_status", "last_test_message", "last_test_at", "updated_at"])
