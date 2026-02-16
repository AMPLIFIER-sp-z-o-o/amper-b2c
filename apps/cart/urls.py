from django.urls import path

from .views import (
    add_to_cart,
    cart_page,
    checkout_page,
    checkout_save_details,
    remove_from_cart,
    summary_page,
)

app_name = "cart"

urlpatterns = [
    path("", cart_page, name="cart_page"),
    path("checkout/", checkout_page, name="checkout_page"),
    path("checkout/save-details/", checkout_save_details, name="checkout_save_details"),
    path("summary/", summary_page, name="summary_page"),
    path("add/", add_to_cart, name="add_to_cart"),
    path("remove/", remove_from_cart, name="remove_from_cart"),
]

