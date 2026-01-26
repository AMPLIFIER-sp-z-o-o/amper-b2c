"""Utility helpers for wall-clock (floating) datetime handling."""

from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

from django.utils import timezone


def to_wall_clock(value: datetime | None) -> datetime | None:
    """
    Return a naive datetime representing the wall-clock value.

    If value is timezone-aware, tzinfo is stripped without conversion.
    """
    if not value:
        return None
    if timezone.is_aware(value):
        return value.replace(tzinfo=None)
    return value


def wall_clock_now() -> datetime:
    """Return the current local time as a naive wall-clock datetime."""
    local_now = timezone.localtime(timezone.now())
    return local_now.replace(tzinfo=None)


def wall_clock_utc_now() -> datetime:
    """
    Return the current local wall-clock time, but tagged as UTC-aware.

    This allows comparing wall-clock times in the database (stored as UTC
    with no shifting) using Django ORM filters.
    """
    now_wall = wall_clock_now()
    return timezone.make_aware(now_wall, dt_timezone.utc)


def is_within_wall_clock_range(
    available_from: datetime | None,
    available_to: datetime | None,
    now: datetime | None = None,
) -> bool:
    """Check availability using wall-clock time in the active timezone."""
    now_wall = to_wall_clock(now) if now else wall_clock_now()
    start = to_wall_clock(available_from)
    end = to_wall_clock(available_to)

    if start and now_wall < start:
        return False
    if end and now_wall > end:
        return False
    return True
