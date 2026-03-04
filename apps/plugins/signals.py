from __future__ import annotations

import threading

from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver

from apps.plugins.engine.registry import registry
from apps.plugins.engine.runtime import run_plugin_lifecycle_callback
from apps.plugins.models import Plugin, PluginStatus

_thread_local = threading.local()


def _get_previous_status_map() -> dict[int, str | None]:
    if not hasattr(_thread_local, "previous_status_by_plugin_pk"):
        _thread_local.previous_status_by_plugin_pk = {}
    return _thread_local.previous_status_by_plugin_pk


@receiver(pre_save, sender=Plugin)
def capture_previous_plugin_status(sender, instance: Plugin, **kwargs) -> None:
    if not instance.pk:
        return
    previous_status = Plugin.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
    _get_previous_status_map()[instance.pk] = previous_status


@receiver(post_save, sender=Plugin)
def dispatch_plugin_lifecycle_on_save(sender, instance: Plugin, created: bool, **kwargs) -> None:
    previous_status = _get_previous_status_map().pop(instance.pk, None)
    # Invalidate cache so next dispatch reads the updated status from DB.
    registry.invalidate_plugin_cache(instance.slug)

    run_plugin_lifecycle_callback(
        instance,
        "on_plugin_status_changed",
        previous_status=previous_status,
        current_status=instance.status,
        created=created,
    )

    if created:
        run_plugin_lifecycle_callback(instance, "on_plugin_created")

    if previous_status != instance.status:
        if instance.status == PluginStatus.ACTIVATED:
            run_plugin_lifecycle_callback(
                instance,
                "on_plugin_activated",
                previous_status=previous_status,
                current_status=instance.status,
            )
        elif previous_status == PluginStatus.ACTIVATED:
            run_plugin_lifecycle_callback(
                instance,
                "on_plugin_deactivated",
                previous_status=previous_status,
                current_status=instance.status,
            )


@receiver(pre_delete, sender=Plugin)
def dispatch_plugin_lifecycle_on_delete(sender, instance: Plugin, **kwargs) -> None:
    registry.invalidate_plugin_cache(instance.slug)
    run_plugin_lifecycle_callback(
        instance,
        "on_plugin_before_delete",
        previous_status=instance.status,
        current_status=PluginStatus.DEACTIVATED,
    )
