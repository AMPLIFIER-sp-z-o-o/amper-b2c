"""
Shared admin mixins for wall-clock availability handling.

Wall-Clock Time Concept:
------------------------
When an admin sets "available_from = 12:00", it means the content should
become visible at 12:00 LOCAL TIME for EACH user, regardless of their timezone.

This is different from Django's default behavior where 12:00 UTC means the same
moment in time everywhere (which would be 13:00 in Warsaw, 07:00 in New York).

Usage:
------
1. For models with available_from/available_to fields, use WallClockAvailabilityAdminMixin:

    class BannerAdmin(WallClockAvailabilityAdminMixin, ModelAdmin):
        list_display = ["name", "is_enabled", "available_from", "available_to", "status_badge"]

2. Or use BaseModelAdmin which auto-detects these fields:

    class BannerAdmin(BaseModelAdmin):
        list_display = ["name", "is_enabled", "available_from", "available_to", "status_badge"]

3. In models, use wall-clock helpers for availability checking:

    from apps.utils.datetime_utils import is_within_wall_clock_range, wall_clock_utc_now

    def is_available(self) -> bool:
        if not self.is_enabled:
            return False
        return is_within_wall_clock_range(self.available_from, self.available_to)
"""

from django.contrib import admin, messages
from django.db import models
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from simple_history.admin import SimpleHistoryAdmin
from unfold.admin import ModelAdmin

from apps.utils.datetime_utils import to_wall_clock
from apps.utils.forms import WallClockDateTimeField


class SingletonAdminMixin:
    """
    Mixin for singleton models to:
    1. Fix success messages by removing the redundant object name.
    2. Simplify breadcrumbs by hiding the instance level if it's a singleton.
    """

    def message_user(
        self, request, message, level=messages.SUCCESS, extra_tags="", fail_silently=False
    ):
        """
        Intervene in message creation to remove quoted object names for singletons.
        Changes 'The Navigation bar "Navigation bar" was changed' to 'Navigation bar was changed'.
        """
        # Convert to string to check content
        msg_str = str(message)
        
        # Matches common patterns in English and Polish
        patterns = [
            "was changed successfully",
            "został pomyślnie zmieniony",
            "was added successfully",
            "został pomyślnie dodany",
        ]
        
        if any(p in msg_str for p in patterns):
            message = _("%(name)s was changed successfully.") % {
                "name": self.model._meta.verbose_name
            }
        return super().message_user(request, message, level, extra_tags, fail_silently)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        # Unfold uses 'title' for the page heading and 'obj' for the breadcrumb part.
        # By setting obj to None or empty in context, we might influence Unfold.
        # However, extra_context usually merges.
        
        # This fixes the main title heading in Unfold
        extra_context["title"] = self.model._meta.verbose_name
        return super().change_view(request, object_id, form_url, extra_context=extra_context)


# Field names that should use wall-clock handling
WALL_CLOCK_FIELD_NAMES = frozenset({"available_from", "available_to"})


class WallClockAvailabilityAdminMixin:
    """
    Mixin that applies wall-clock handling for availability fields.

    Automatically:
    - Uses WallClockDateTimeField for available_from/available_to in forms
    - Replaces these fields in list_display with display methods showing naive time
    """

    availability_field_names = WALL_CLOCK_FIELD_NAMES

    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name in self.availability_field_names and isinstance(db_field, models.DateTimeField):
            kwargs.setdefault("form_class", WallClockDateTimeField)
        return super().formfield_for_dbfield(db_field, **kwargs)

    def get_list_display(self, request):
        display = list(super().get_list_display(request))
        mapping = {
            "available_from": "available_from_display",
            "available_to": "available_to_display",
        }
        return [mapping.get(item, item) for item in display]

    @admin.display(description=_("Available from"))
    def available_from_display(self, obj):
        return to_wall_clock(getattr(obj, "available_from", None))

    @admin.display(description=_("Available to"))
    def available_to_display(self, obj):
        return to_wall_clock(getattr(obj, "available_to", None))


def _model_has_wall_clock_fields(model) -> bool:
    """Check if a model has any wall-clock fields."""
    if not model:
        return False
    field_names = {f.name for f in model._meta.fields}
    return bool(WALL_CLOCK_FIELD_NAMES & field_names)


class HistoryModelAdmin(SimpleHistoryAdmin, ModelAdmin):
    """Unfold ModelAdmin with django-simple-history support."""


class BaseModelAdmin(HistoryModelAdmin):
    """
    Base ModelAdmin that auto-detects and handles wall-clock fields.

    If the model has 'available_from' or 'available_to' fields,
    wall-clock handling is automatically applied.

    Example:
        class BannerAdmin(BaseModelAdmin):
            list_display = ["name", "is_enabled", "available_from", "status_badge"]
    """

    def formfield_for_dbfield(self, db_field, **kwargs):
        # Apply wall-clock form field for availability fields
        if db_field.name in WALL_CLOCK_FIELD_NAMES and isinstance(db_field, models.DateTimeField):
            kwargs.setdefault("form_class", WallClockDateTimeField)
        return super().formfield_for_dbfield(db_field, **kwargs)

    def get_list_display(self, request):
        display = list(super().get_list_display(request))

        # Only remap if model has these fields
        if not _model_has_wall_clock_fields(self.model):
            return display

        mapping = {
            "available_from": "available_from_display",
            "available_to": "available_to_display",
        }
        return [mapping.get(item, item) for item in display]

    @admin.display(description=_("Available from"))
    def available_from_display(self, obj):
        return to_wall_clock(getattr(obj, "available_from", None))

    @admin.display(description=_("Available to"))
    def available_to_display(self, obj):
        return to_wall_clock(getattr(obj, "available_to", None))
