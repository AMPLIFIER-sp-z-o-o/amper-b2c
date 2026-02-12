from django import template
from django.utils.timesince import timesince
from django.utils.translation import gettext as _

register = template.Library()


@register.filter
def smart_timesince(value):
    """Like Django's timesince but returns 'just now' instead of '0 minutes'."""
    if value is None:
        return ""
    result = timesince(value)
    if result.startswith("0\xa0") or result.startswith("0 "):
        return _("just now")
    return f"{result} {_('ago')}"
