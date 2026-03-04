# Generated manually – removes PluginRuntimeSettings (moved to settings.py constants)

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("plugins", "0003_remove_pluginpackageartifact"),
    ]

    operations = [
        migrations.DeleteModel(
            name="HistoricalPluginRuntimeSettings",
        ),
        migrations.DeleteModel(
            name="PluginRuntimeSettings",
        ),
    ]
