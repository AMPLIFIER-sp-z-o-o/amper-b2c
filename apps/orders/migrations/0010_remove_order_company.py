from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0009_remove_historicalorder_payment_cost"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="order",
            name="company",
        ),
    ]
