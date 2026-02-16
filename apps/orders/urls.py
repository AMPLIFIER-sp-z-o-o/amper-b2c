from django.urls import path

from .views import place_order, track_order

app_name = "orders"

urlpatterns = [
    path("place/", place_order, name="place"),
    path("track/<str:token>/", track_order, name="track"),
]
