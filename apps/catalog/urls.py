from django.urls import path
from .views import product_detail

app_name = "catalog"

urlpatterns = [
    path("<slug:slug>/<int:id>/", product_detail, name="product_detail"),
]