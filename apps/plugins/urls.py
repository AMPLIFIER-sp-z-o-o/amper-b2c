from django.urls import path

from apps.plugins.views import plugin_webhook, provider_flow_return, provider_flow_start

app_name = "plugins"

urlpatterns = [
    path("flow/<slug:plugin_slug>/start/<str:token>/", provider_flow_start, name="provider_flow_start"),
    path("flow/<slug:plugin_slug>/return/<str:token>/", provider_flow_return, name="provider_flow_return"),
    # Backward-compatible legacy routes.
    path("pay/<slug:plugin_slug>/<str:token>/", provider_flow_start, name="payment_provider_start"),
    path("pay/<slug:plugin_slug>/return/<str:token>/", provider_flow_return, name="payment_provider_return"),
    path("webhooks/<slug:plugin_slug>/", plugin_webhook, name="plugin_webhook"),
]
