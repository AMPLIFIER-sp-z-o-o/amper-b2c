from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0007_remove_historicalorder_tax_rate_percent_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="order",
            name="payment_cost",
        ),
    ]
