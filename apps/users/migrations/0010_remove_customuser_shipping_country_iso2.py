from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0009_historicalcustomuser_shipping_country_iso2_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="customuser",
            name="shipping_country_iso2",
        ),
        migrations.RemoveField(
            model_name="historicalcustomuser",
            name="shipping_country_iso2",
        ),
    ]
