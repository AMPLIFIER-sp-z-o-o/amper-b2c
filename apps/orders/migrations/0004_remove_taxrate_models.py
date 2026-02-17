from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0003_alter_coupon_kind_alter_coupon_min_subtotal_and_more"),
    ]

    operations = [
        migrations.DeleteModel(
            name="TaxRate",
        ),
        migrations.DeleteModel(
            name="HistoricalTaxRate",
        ),
    ]
