import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def cleanup_anonymous_wishlists(days=90):
    """Delete anonymous wishlists that haven't been updated in the given number of days."""
    from apps.favourites.models import WishList

    cutoff = timezone.now() - timedelta(days=days)
    expired = WishList.objects.filter(
        user__isnull=True,
        session_key__isnull=False,
        updated_at__lt=cutoff,
    )
    count = expired.count()
    if count:
        expired.delete()
        logger.info("Deleted %d anonymous wishlist(s) older than %d days.", count, days)
    return count
