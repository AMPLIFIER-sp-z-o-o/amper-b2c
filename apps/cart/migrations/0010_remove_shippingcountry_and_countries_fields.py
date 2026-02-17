from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0004_remove_taxrate_models"),
        ("cart", "0009_single_country_store_defaults"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="deliverymethod",
            name="countries",
        ),
        migrations.RemoveField(
            model_name="paymentmethod",
            name="countries",
        ),
        migrations.DeleteModel(
            name="ShippingCountry",
        ),
    ]
