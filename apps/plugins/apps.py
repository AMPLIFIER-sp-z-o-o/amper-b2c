from django.apps import AppConfig
from django.core.signals import request_started
from django.db.models.signals import post_migrate
from django.utils.translation import gettext_lazy as _

_plugins_bootstrapped = False


def _bootstrap_plugins(**_kwargs):
    global _plugins_bootstrapped
    if _plugins_bootstrapped:
        return
    from apps.plugins.engine.loader import sync_and_load_plugins

    _plugins_bootstrapped = bool(sync_and_load_plugins())


class PluginsConfig(AppConfig):
    default_auto_field = "django.db.models.AutoField"
    name = "apps.plugins"
    label = "plugins"
    verbose_name = _("Plugins")

    def ready(self):
        from apps.plugins import signals  # noqa: F401

        post_migrate.connect(_bootstrap_plugins, sender=self)
        request_started.connect(_bootstrap_plugins, dispatch_uid="plugins-bootstrap-on-request")

