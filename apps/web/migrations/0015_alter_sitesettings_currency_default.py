from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("web", "0014_change_logo_to_filefield"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sitesettings",
            name="currency",
            field=models.CharField(
                choices=[("PLN", "PLN (zł)"), ("EUR", "EUR (€)"), ("USD", "USD ($)")],
                default="USD",
                help_text="Currency symbol displayed on prices. No conversion is performed - this is display only.",
                max_length=3,
                verbose_name="Currency",
            ),
        ),
    ]
