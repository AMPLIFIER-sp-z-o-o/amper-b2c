from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("cart", "0011_remove_cart_tax_rate_percent_remove_cart_tax_total_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="paymentmethod",
            name="additional_fees",
        ),
    ]
