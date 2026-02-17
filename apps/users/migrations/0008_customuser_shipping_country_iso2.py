from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0007_remove_avatar_field"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="shipping_country_iso2",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Two-letter ISO 3166-1 alpha-2 code (e.g. PL, DE).",
                max_length=2,
                verbose_name="Shipping country",
            ),
        ),
        migrations.AddField(
            model_name="historicalcustomuser",
            name="shipping_country_iso2",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Two-letter ISO 3166-1 alpha-2 code (e.g. PL, DE).",
                max_length=2,
                verbose_name="Shipping country",
            ),
        ),
    ]
