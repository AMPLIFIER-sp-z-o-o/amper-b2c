from django.urls import path

from .views import payment_gateway_placeholder, place_order, track_order

app_name = "orders"

urlpatterns = [
    path("place/", place_order, name="place"),
    path("pay/<str:token>/", payment_gateway_placeholder, name="pay"),
    path("track/<str:token>/", track_order, name="track"),
]
