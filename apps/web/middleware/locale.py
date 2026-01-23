import zoneinfo

from django.conf import settings
from django.utils import timezone, translation

# Cookie name for storing browser timezone (must match views.py)
TIMEZONE_COOKIE_NAME = "amplifier_timezone"


class UserLocaleMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        """Activate logged-in users' preferred language based on their profile setting."""
        user = getattr(request, "user", None)
        if user and user.is_authenticated and user.language and user.language != translation.get_language():
            translation.activate(user.language)

        response = self.get_response(request)

        cookie_lang_code = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
        if not cookie_lang_code or cookie_lang_code != translation.get_language():
            response.set_cookie(settings.LANGUAGE_COOKIE_NAME, translation.get_language())
        return response


class UserTimezoneMiddleware:
    """
    Middleware to set the timezone based on the user's configuration or browser detection.

    Priority:
    1. Authenticated user's profile timezone setting
    2. Browser-detected timezone from cookie (for all users)
    3. Server default timezone (TIME_ZONE in settings)

    Loosely modeled on: https://docs.djangoproject.com/en/stable/topics/i18n/timezones/#selecting-the-current-time-zone
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tz_name = None

        user = getattr(request, "user", None)
        if user and user.is_authenticated and user.timezone:
            # Priority 1: User's profile setting
            tz_name = user.timezone
        else:
            # Priority 2: Browser-detected timezone from cookie
            tz_name = request.COOKIES.get(TIMEZONE_COOKIE_NAME)

        if tz_name:
            try:
                timezone.activate(zoneinfo.ZoneInfo(tz_name))
            except (KeyError, Exception):
                # Invalid timezone, use server default
                timezone.deactivate()
        else:
            timezone.deactivate()

        return self.get_response(request)
