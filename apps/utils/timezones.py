from django.utils.translation import gettext


def get_common_timezones():
    # This is an example list of common timezones. You may want to modify it for your own app.
    return [
        "Africa/Cairo",
        "Africa/Johannesburg",
        "Africa/Nairobi",
        "America/Anchorage",
        "America/Argentina/Buenos_Aires",
        "America/Chicago",
        "America/Denver",
        "America/Los_Angeles",
        "America/Mexico_City",
        "America/New_York",
        "America/Sao_Paulo",
        "America/Toronto",
        "Asia/Dubai",
        "Asia/Jerusalem",
        "Asia/Kolkata",
        "Asia/Seoul",
        "Asia/Shanghai",
        "Asia/Singapore",
        "Asia/Tokyo",
        "Australia/Perth",
        "Australia/Sydney",
        "Europe/Athens",
        "Europe/Berlin",
        "Europe/London",
        "Europe/Moscow",
        "Europe/Paris",
        "Europe/Warsaw",
        "Pacific/Auckland",
        "Pacific/Fiji",
        "Pacific/Honolulu",
        "Pacific/Tongatapu",
        "UTC",
    ]


def is_valid_timezone(tz_name: str) -> bool:
    """Check if the given timezone name is valid."""
    import zoneinfo

    try:
        zoneinfo.ZoneInfo(tz_name)
        return True
    except (KeyError, zoneinfo.ZoneInfoNotFoundError):
        return False


def get_timezones_display():
    all_tzs = get_common_timezones()
    return zip([""] + all_tzs, [gettext("Not Set")] + all_tzs, strict=False)
