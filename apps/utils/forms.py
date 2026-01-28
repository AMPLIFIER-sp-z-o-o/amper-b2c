"""
Wall-clock datetime widgets and fields for Django admin.

These utilities treat entered datetimes as "floating" (wall-clock) times
and store them in UTC without shifting. This enables per-user local-time
availability windows (e.g. show at 12:00 for each user's timezone).
"""

from datetime import UTC, datetime

from django import forms
from django.contrib.admin.widgets import AdminSplitDateTime
from django.utils import timezone


class WallClockSplitDateTimeWidget(AdminSplitDateTime):
    """SplitDateTimeWidget for wall-clock (floating) times."""


class WallClockDateTimeField(forms.SplitDateTimeField):
    """
    DateTimeField that stores wall-clock times without timezone shifting.

    - On display: shows the stored wall-clock time (no conversion)
    - On save: attaches UTC tzinfo without shifting (keeps wall-clock)
    """

    widget = WallClockSplitDateTimeWidget

    def prepare_value(self, value):
        """Show stored wall-clock time without conversion."""
        if isinstance(value, (list, tuple)):
            return super().prepare_value(value)
        if value and isinstance(value, datetime) and timezone.is_aware(value):
            value = value.replace(tzinfo=None)
        return super().prepare_value(value)

    def clean(self, value):
        """Attach UTC tzinfo without shifting the wall-clock time."""
        cleaned = super().clean(value)
        if cleaned:
            if timezone.is_aware(cleaned):
                cleaned = cleaned.replace(tzinfo=UTC)
            else:
                cleaned = timezone.make_aware(cleaned, UTC)
        return cleaned
