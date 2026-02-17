from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0010_remove_order_company"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="historicalorder",
            name="company",
        ),
    ]
