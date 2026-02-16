from django.db import migrations


def add_extra_image(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    ProductImage = apps.get_model("catalog", "ProductImage")

    try:
        product = Product.objects.get(id=11)
    except Product.DoesNotExist:
        return

    image_path = "product-images/seed/product-12.jpg"

    if ProductImage.objects.filter(product=product, image=image_path).exists():
        return

    ProductImage.objects.create(
        product=product,
        image=image_path,
        alt_text="",
        sort_order=0,
    )


def remove_extra_image(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    ProductImage = apps.get_model("catalog", "ProductImage")

    try:
        product = Product.objects.get(id=11)
    except Product.DoesNotExist:
        return

    image_path = "product-images/seed/product-12.jpg"
    ProductImage.objects.filter(product=product, image=image_path).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0010_add_disabled_status"),
    ]

    operations = [
        migrations.RunPython(add_extra_image, remove_extra_image),
    ]
