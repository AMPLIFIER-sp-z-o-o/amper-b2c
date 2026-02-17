from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0008_remove_order_payment_cost"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="historicalorder",
            name="payment_cost",
        ),
    ]
