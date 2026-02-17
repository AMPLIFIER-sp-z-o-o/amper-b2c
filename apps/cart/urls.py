from django.urls import path

from .views import (
    add_to_cart,
    apply_coupon,
    cart_page,
    clear_cart,
    checkout_page,
    checkout_save_details,
    remove_from_cart,
    remove_coupon,
    save_as_list,
    set_cart_address,
    summary_page,
)

app_name = "cart"

urlpatterns = [
    path("", cart_page, name="cart_page"),
    path("set-cart-address/", set_cart_address, name="set_cart_address"),
    path("clear/", clear_cart, name="clear_cart"),
    path("save-as-list/", save_as_list, name="save_as_list"),
    path("apply-coupon/", apply_coupon, name="apply_coupon"),
    path("remove-coupon/", remove_coupon, name="remove_coupon"),
    path("checkout/", checkout_page, name="checkout_page"),
    path("checkout/save-details/", checkout_save_details, name="checkout_save_details"),
    path("summary/", summary_page, name="summary_page"),
    path("add/", add_to_cart, name="add_to_cart"),
    path("remove/", remove_from_cart, name="remove_from_cart"),
]

