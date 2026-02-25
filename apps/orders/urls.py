from django.urls import path

from .views import order_summary, payment_gateway_placeholder, place_order, post_payment_mock, track_order_legacy

app_name = "orders"

urlpatterns = [
    path("place/", place_order, name="place"),
    path("pay/<str:token>/", payment_gateway_placeholder, name="pay"),
    path("post-payment/<str:token>/", post_payment_mock, name="post_payment_mock"),
    path("summary/<str:token>/", order_summary, name="summary"),
    # Legacy route kept for old links from emails/bookmarks.
    path("track/<str:token>/", track_order_legacy, name="track"),
]
