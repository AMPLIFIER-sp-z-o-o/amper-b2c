from django.apps import AppConfig


class MediaConfig(AppConfig):
    default_auto_field = "django.db.models.AutoField"
    name = "apps.media"
    verbose_name = "Media Storage"

    def ready(self):
        # Set up storage cache invalidation signals
        from apps.media.storage import setup_storage_signals

        setup_storage_signals()

        # Set up media file sync signals
        from apps.media.signals import setup_media_sync_signals

        setup_media_sync_signals()
