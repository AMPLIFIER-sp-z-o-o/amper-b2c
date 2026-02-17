from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0012_remove_shippingaddress_company"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="historicalshippingaddress",
            name="company",
        ),
    ]
