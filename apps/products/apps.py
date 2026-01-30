from django.apps import AppConfig


class ProductsConfig(AppConfig):
    default_auto_field = "django.db.models.AutoField"
    name = "apps.products"
    label = "products"
    verbose_name = "Products"
