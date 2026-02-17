import uuid

from django.db import migrations, models


def _backfill_css_hooks(apps, schema_editor):
    model_names = [
        "Banner",
        "HomepageSection",
        "HomepageSectionBanner",
        "HomepageSectionCategoryBox",
        "HomepageSectionCategoryItem",
        "StorefrontHeroSection",
        "StorefrontCategoryBox",
        "StorefrontCategoryItem",
    ]

    for model_name in model_names:
        Model = apps.get_model("homepage", model_name)
        queryset = Model.objects.filter(css_hook__isnull=True).only("pk")
        batch = []
        for obj in queryset.iterator(chunk_size=1000):
            obj.css_hook = uuid.uuid4()
            batch.append(obj)
            if len(batch) >= 1000:
                Model.objects.bulk_update(batch, ["css_hook"], batch_size=1000)
                batch.clear()
        if batch:
            Model.objects.bulk_update(batch, ["css_hook"], batch_size=1000)


class Migration(migrations.Migration):
    dependencies = [
        ("homepage", "0012_banner_image_alignment_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="banner",
            name="css_hook",
            field=models.UUIDField(db_index=True, editable=False, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="homepagesection",
            name="css_hook",
            field=models.UUIDField(db_index=True, editable=False, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="homepagesectionbanner",
            name="css_hook",
            field=models.UUIDField(db_index=True, editable=False, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="homepagesectioncategorybox",
            name="css_hook",
            field=models.UUIDField(db_index=True, editable=False, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="homepagesectioncategoryitem",
            name="css_hook",
            field=models.UUIDField(db_index=True, editable=False, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="storefrontherosection",
            name="css_hook",
            field=models.UUIDField(db_index=True, editable=False, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="storefrontcategorybox",
            name="css_hook",
            field=models.UUIDField(db_index=True, editable=False, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="storefrontcategoryitem",
            name="css_hook",
            field=models.UUIDField(db_index=True, editable=False, null=True, unique=True),
        ),
        migrations.RunPython(_backfill_css_hooks, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="banner",
            name="css_hook",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name="homepagesection",
            name="css_hook",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name="homepagesectionbanner",
            name="css_hook",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name="homepagesectioncategorybox",
            name="css_hook",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name="homepagesectioncategoryitem",
            name="css_hook",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name="storefrontherosection",
            name="css_hook",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name="storefrontcategorybox",
            name="css_hook",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name="storefrontcategoryitem",
            name="css_hook",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
