from django.db import migrations


def ensure_single_country(apps, schema_editor):
    ShippingCountry = apps.get_model("cart", "ShippingCountry")

    # Default store country (can be overridden in runtime settings, but migrations must be deterministic).
    iso2 = "PL"
    name = "Poland"

    ShippingCountry.objects.update(is_active=False)

    obj, _ = ShippingCountry.objects.get_or_create(
        iso2=iso2,
        defaults={
            "name": name,
            "is_active": True,
        },
    )
    updates = {}
    if not (obj.name or "").strip():
        updates["name"] = name
    updates["is_active"] = True
    if updates:
        ShippingCountry.objects.filter(pk=obj.pk).update(**updates)


class Migration(migrations.Migration):

    dependencies = [
        ("cart", "0008_alter_historicalshippingcountry_iso2_and_more"),
    ]

    operations = [
        migrations.RunPython(ensure_single_country, reverse_code=migrations.RunPython.noop),
    ]
