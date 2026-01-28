from django.db import models
from simple_history.models import HistoricalRecords


class BaseModel(models.Model):
    """
    Base model that includes default created / updated timestamps.
    """

    history = HistoricalRecords(inherit=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SingletonModel(BaseModel):
    """Abstract model for singleton tables using a stable primary key."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.pk and self.__class__.objects.exists():
            existing = self.__class__.objects.first()
            self.pk = existing.pk
            if hasattr(self, "created_at") and not getattr(self, "created_at", None):
                self.created_at = existing.created_at
        super().save(*args, **kwargs)

    @classmethod
    def get_settings(cls):
        settings_obj, _created = cls.objects.get_or_create(pk=1)
        return settings_obj
