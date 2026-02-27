from django.urls import path

from . import views

app_name = "favorites"

urlpatterns = [
    # Main page
    path("", views.favorites_page, name="favorites_page"),
    # CRUD wishlists
    path("list/<int:pk>/", views.wishlist_detail, name="wishlist_detail"),
    path("create/", views.create_wishlist, name="create_wishlist"),
    path("update/<int:pk>/", views.update_wishlist, name="update_wishlist"),
    path("delete/<int:pk>/", views.delete_wishlist, name="delete_wishlist"),
    # Item operations
    path("add/", views.add_to_wishlist, name="add_to_wishlist"),
    path("remove/", views.remove_from_wishlist, name="remove_from_wishlist"),
    path("move/", views.move_item, name="move_item"),
    path("toggle/", views.toggle_favorite, name="toggle_favorite"),
    # Bulk operations
    path("add-all-to-cart/", views.add_all_to_cart, name="add_all_to_cart"),
    path("copy-items/", views.copy_items, name="copy_items"),
    path("bulk-remove/", views.bulk_remove, name="bulk_remove"),
    # API endpoints
    path("api/wishlists/", views.get_wishlists, name="get_wishlists"),
    path("api/status/", views.check_product_status, name="check_product_status"),
    path("api/products/", views.get_all_products, name="get_all_products"),
    # Partials for HTMX
    path("partials/items/", views.wishlist_items_partial, name="wishlist_items_partial"),
    path("partials/sidebar/", views.wishlists_sidebar_partial, name="wishlists_sidebar_partial"),
]
