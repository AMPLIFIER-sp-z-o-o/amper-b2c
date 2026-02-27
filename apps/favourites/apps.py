from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class FavoritesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.favourites"
    verbose_name = _("Shopping lists")

    def ready(self):
        """Import signals to register them."""
        import apps.favourites.signals  # noqa: F401
