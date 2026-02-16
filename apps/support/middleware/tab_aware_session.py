import re
from importlib import import_module

from django.conf import settings
from django.contrib.sessions.backends.base import UpdateError
from django.contrib.sessions.exceptions import SessionInterrupted
from django.utils.cache import patch_vary_headers
from django.utils.deprecation import MiddlewareMixin


TAB_PARAM = "__tab"
TAB_HEADER = "HTTP_X_TAB_ID"
TAB_COOKIE_HINT = "amper_tab_id"
TAB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class TabAwareSessionMiddleware(MiddlewareMixin):
    """
    Overlay middleware for tab-scoped sessions on top of Django SessionMiddleware.

    Default traffic (without `__tab`) keeps using the standard `sessionid` cookie.
    When `__tab` is present, this middleware swaps `request.session` to a
    dedicated tab session cookie and restores the default session object before
    Django SessionMiddleware writes the response.
    """

    def __init__(self, get_response):
        super().__init__(get_response)
        engine = import_module(settings.SESSION_ENGINE)
        self.SessionStore = engine.SessionStore

    @staticmethod
    def _normalize_tab_id(value: str | None) -> str | None:
        if not value:
            return None
        value = value.strip()
        if not value or not TAB_ID_RE.match(value):
            return None
        return value

    def _get_tab_id(self, request) -> str | None:
        query_tab = self._normalize_tab_id(request.GET.get(TAB_PARAM))
        if query_tab:
            return query_tab

        header_tab = self._normalize_tab_id(request.META.get(TAB_HEADER))
        if header_tab:
            return header_tab

        return None

    @staticmethod
    def _cookie_name_for_tab(tab_id: str | None) -> str:
        if not tab_id:
            return settings.SESSION_COOKIE_NAME
        return f"{settings.SESSION_COOKIE_NAME}__{tab_id}"

    def process_request(self, request):
        request._default_session = getattr(request, "session", None)

        tab_id = self._get_tab_id(request)
        cookie_name = self._cookie_name_for_tab(tab_id)

        request._tab_id = tab_id
        request.tab_id = tab_id
        request._session_cookie_name = cookie_name
        request._session_is_tab_scoped = bool(tab_id)
        request._session_force_save = False

        if not tab_id:
            return

        tab_session_key = request.COOKIES.get(cookie_name)

        if tab_id and not tab_session_key:
            default_key = request.COOKIES.get(settings.SESSION_COOKIE_NAME)
            if default_key:
                default_store = self.SessionStore(default_key)
                try:
                    default_data = default_store.load()
                except Exception:
                    default_data = {}

                request.session = self.SessionStore()
                request.session.update(default_data)
                request._session_force_save = True
                return

        request.session = self.SessionStore(tab_session_key)

    def process_response(self, request, response):
        if not getattr(request, "_session_is_tab_scoped", False):
            return response

        try:
            accessed = request.session.accessed
            modified = request.session.modified or bool(getattr(request, "_session_force_save", False))
            empty = request.session.is_empty()
        except AttributeError:
            default_session = getattr(request, "_default_session", None)
            if default_session is not None:
                request.session = default_session
            return response

        cookie_name = getattr(request, "_session_cookie_name", settings.SESSION_COOKIE_NAME)

        if cookie_name in request.COOKIES and empty:
            response.delete_cookie(
                cookie_name,
                path=settings.SESSION_COOKIE_PATH,
                domain=settings.SESSION_COOKIE_DOMAIN,
                samesite=settings.SESSION_COOKIE_SAMESITE,
            )
            patch_vary_headers(response, ("Cookie",))
        else:
            if accessed:
                patch_vary_headers(response, ("Cookie",))

            if (modified or settings.SESSION_SAVE_EVERY_REQUEST) and not empty:
                if response.status_code < 500:
                    try:
                        request.session.save()
                    except UpdateError:
                        raise SessionInterrupted(
                            "The request's session was deleted before the request completed. "
                            "The user may have logged out in a concurrent request, for example."
                        )

                    response.set_cookie(
                        cookie_name,
                        request.session.session_key,
                        max_age=settings.SESSION_COOKIE_AGE,
                        expires=None,
                        domain=settings.SESSION_COOKIE_DOMAIN,
                        path=settings.SESSION_COOKIE_PATH,
                        secure=settings.SESSION_COOKIE_SECURE or None,
                        httponly=settings.SESSION_COOKIE_HTTPONLY or None,
                        samesite=settings.SESSION_COOKIE_SAMESITE,
                    )

        default_session = getattr(request, "_default_session", None)
        if default_session is not None:
            request.session = default_session

        return response
