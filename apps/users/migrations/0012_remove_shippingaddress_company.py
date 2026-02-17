from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0011_remove_historicalshippingaddress_phone_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="shippingaddress",
            name="company",
        ),
    ]
