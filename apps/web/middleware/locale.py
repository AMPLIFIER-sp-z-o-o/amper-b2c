import zoneinfo

from django.conf import settings
from django.utils import timezone, translation


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
    Middleware to set the timezone based on the user's configuration.

    Loosely modeled on: https://docs.djangoproject.com/en/stable/topics/i18n/timezones/#selecting-the-current-time-zone
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            if user.timezone:
                timezone.activate(zoneinfo.ZoneInfo(user.timezone))
            else:
                timezone.deactivate()
        return self.get_response(request)
