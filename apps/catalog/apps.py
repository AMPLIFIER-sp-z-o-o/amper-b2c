from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.AutoField"
    name = "apps.catalog"
    label = "catalog"
    verbose_name = "Catalog"
