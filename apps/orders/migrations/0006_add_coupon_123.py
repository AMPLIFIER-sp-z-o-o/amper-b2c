from decimal import Decimal

from django.db import migrations


def create_coupon_123(apps, schema_editor):
    Coupon = apps.get_model("orders", "Coupon")
    # NOTE: Can't import CouponKind enum in migrations reliably across historical states.
    # Use raw values matching the model choices.
    Coupon.objects.get_or_create(
        code="123",
        defaults={
            "kind": "fixed",
            "value": Decimal("10.00"),
            "is_active": True,
            "used_count": 0,
            "min_subtotal": None,
            "valid_from": None,
            "valid_to": None,
            "usage_limit": None,
        },
    )


def delete_coupon_123(apps, schema_editor):
    Coupon = apps.get_model("orders", "Coupon")
    Coupon.objects.filter(code="123").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0005_remove_historicalorder_shipping_country_and_more"),
    ]

    operations = [
        migrations.RunPython(create_coupon_123, reverse_code=delete_coupon_123),
    ]
