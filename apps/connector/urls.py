from django.urls import path

from .views import import_stock_locations_view, import_stocks_view


app_name = "connector"

urlpatterns = [
    path("stock-locations/import/", import_stock_locations_view, name="connector_import_stock_locations"),
    path("stocks/import/", import_stocks_view, name="connector_import_stocks"),
]