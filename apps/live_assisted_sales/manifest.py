PLUGIN_MANIFEST = {
    "name": "Live Assisted Sales",
    "version": "1.0.0",
    "description": "WP-like adapter that forwards storefront events to Live Assisted Sales.",
    "settings_model": "live_assisted_sales.LiveAssistedSalesSettings",
    "browser_endpoint": "/live-assisted-sales/events/",
    "event_types": [
        "product_view",
        "category_view",
        "search",
        "cart_item_added",
        "cart_item_removed",
    ],
}
