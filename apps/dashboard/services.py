import datetime

from django.conf import settings
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.users.models import CustomUser


def get_user_signups(start: datetime.date | None = None, end: datetime.date | None = None, include_unconfirmed=None):
    extra_filter_kwargs = {}
    if include_unconfirmed is None:
        include_unconfirmed = settings.ACCOUNT_EMAIL_VERIFICATION != "mandatory"
    if not include_unconfirmed:
        extra_filter_kwargs = {
            "emailaddress__verified": True,
        }
    end = end or timezone.now()
    start = start or end - datetime.timedelta(days=90)
    data = (
        CustomUser.objects.filter(date_joined__gte=start, date_joined__lte=end, **extra_filter_kwargs)
        .annotate(date=TruncDate("date_joined"))
        .values("date")
        .annotate(count=Count("id"))
        .order_by("date")
    )
    return [{"date": item["date"], "count": item["count"]} for item in data]
