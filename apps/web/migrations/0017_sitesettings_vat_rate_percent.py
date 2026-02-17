from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("web", "0016_alter_historicalsitesettings_currency_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="vat_rate_percent",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Store-wide VAT rate (percent). Example: 23 means 23%.",
                max_digits=6,
                verbose_name="VAT rate percent",
            ),
        ),
    ]
