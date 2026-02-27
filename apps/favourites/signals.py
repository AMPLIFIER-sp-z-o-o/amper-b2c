"""
Signals for the favorites app.

Handles merging anonymous wishlists to user account on login.
"""

from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from apps.favourites.models import WishList


@receiver(user_logged_in)
def merge_anonymous_wishlists_on_login(sender, request, user, **kwargs):
    """
    Merge anonymous wishlists to user account on login.

    When a user logs in, any wishlists associated with their session
    are merged into their account's wishlists. Items from anonymous
    wishlists are moved to the user's default wishlist.
    """
    if not request:
        return

    session_key = request.COOKIES.get(settings.SESSION_COOKIE_NAME) or request.session.session_key
    if not session_key:
        return

    try:
        WishList.merge_anonymous_wishlists(user, session_key)
    except Exception:
        # Don't break login if merge fails
        pass
