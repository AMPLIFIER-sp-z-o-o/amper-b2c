from django.apps import AppConfig


class FavouritesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.favourites"
    verbose_name = "Favourites"

    def ready(self):
        """Import signals to register them."""
        import apps.favourites.signals  # noqa: F401
