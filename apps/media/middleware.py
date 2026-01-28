"""
Current user middleware for tracking the logged-in user across the request lifecycle.

This middleware stores the current user in thread-local storage, making it accessible
from signal handlers and other code that doesn't have direct access to the request.
"""

import threading
from typing import Any

from django.http import HttpRequest, HttpResponse

# Thread-local storage for current user
_thread_locals = threading.local()


def get_current_user() -> Any:
    """
    Get the current user from thread-local storage.
    Returns None if no user is set or user is not authenticated.
    """
    user = getattr(_thread_locals, "user", None)
    if user and hasattr(user, "is_authenticated") and user.is_authenticated:
        return user
    return None


class CurrentUserMiddleware:
    """
    Middleware that stores the current authenticated user in thread-local storage.

    This makes the current user accessible from signal handlers via get_current_user().
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Store user in thread-local storage
        _thread_locals.user = getattr(request, "user", None)

        try:
            response = self.get_response(request)
        finally:
            # Clean up after request
            _thread_locals.user = None

        return response
