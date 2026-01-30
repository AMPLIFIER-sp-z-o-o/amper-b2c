from django.urls import path
from django.views.generic import TemplateView

from . import views

app_name = "web"
urlpatterns = [
    path("", views.home, name="home"),
    path("products/", views.product_list, name="product_list"),
    path("category/<int:category_id>/<slug:category_slug>/", views.product_list, name="product_list_category"),
    path("search/", views.product_search, name="product_search"),
    path("preview/<str:token>/", views.preview_draft, name="preview_draft"),
    path("terms/", TemplateView.as_view(template_name="terms.html"), name="terms"),
    path("robots.txt", TemplateView.as_view(template_name="robots.txt", content_type="text/plain"), name="robots.txt"),
    # these views are just for testing error pages
    # actual error handling is handled by Django: https://docs.djangoproject.com/en/stable/ref/views/#error-views
    path("400/", TemplateView.as_view(template_name="400.html"), name="400"),
    path("403/", TemplateView.as_view(template_name="403.html"), name="403"),
    path("404/", TemplateView.as_view(template_name="404.html"), name="404"),
    path("429/", TemplateView.as_view(template_name="429.html"), name="429"),
    path("500/", TemplateView.as_view(template_name="500.html"), name="500"),
    path("simulate_error/", views.simulate_error),
    path("health/", views.HealthCheck.as_view(), name="health_check"),
    path(
        "ui/flowbite/",
        TemplateView.as_view(
            template_name="web/ui_demos/flowbite/flowbite_demo.html", extra_context={"active_tab": "flowbite-demo"}
        ),
        name="flowbite",
    ),
    path(
        "ui/shadcn/",
        TemplateView.as_view(
            template_name="web/ui_demos/shadcn_demo.html", extra_context={"active_tab": "shadcn-demo"}
        ),
        name="shadcn",
    ),
]
