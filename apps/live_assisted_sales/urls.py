from django.urls import path

from . import views

app_name = "live_assisted_sales"

urlpatterns = [
    path("events/", views.browser_events, name="events"),
    path("product-search/", views.product_search, name="product-search"),
]
