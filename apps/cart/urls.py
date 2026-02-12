from django.urls import path
from .views import cart_page, summary_page, checkout_page, add_to_cart, remove_from_cart

app_name = "cart"

urlpatterns = [
    path("", cart_page, name="cart_page"),
    path("checkout/", checkout_page, name="checkout_page"),
    path("summary/", summary_page, name="summary_page"),
    path("add/", add_to_cart, name="add_to_cart"),
    path("remove/", remove_from_cart, name="remove_from_cart"),
]

