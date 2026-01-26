from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.utils.models import BaseModel


class DraftSession(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="draft_sessions",
    )
    session_key = models.CharField(max_length=64, unique=True)
    share_token = models.CharField(max_length=64, unique=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"DraftSession({self.user_id}, {self.session_key})"


class DraftChange(BaseModel):
    session = models.ForeignKey(
        DraftSession,
        on_delete=models.CASCADE,
        related_name="draft_changes",
    )
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    object_id = models.CharField(max_length=64, null=True, blank=True)
    draft_token = models.CharField(max_length=128)
    object_repr = models.CharField(max_length=255, blank=True, default="")
    admin_change_url = models.CharField(max_length=500, blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["session", "draft_token"], name="unique_draft_per_session_token"),
        ]
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        model_label = "unknown"
        if self.content_type:
            model_label = f"{self.content_type.app_label}.{self.content_type.model}"
        return f"DraftChange({model_label}, {self.object_id or 'new'})"
