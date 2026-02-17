import uuid

from django.db import migrations, models


def _backfill_css_hooks(apps, schema_editor):
    model_names = [
        "TopBar",
        "DynamicPage",
        "Footer",
        "FooterSection",
        "FooterSectionLink",
        "FooterSocialMedia",
        "BottomBar",
        "BottomBarLink",
        "Navbar",
        "NavbarItem",
    ]

    for model_name in model_names:
        Model = apps.get_model("web", model_name)
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
        ("web", "0019_remove_historicalsitesettings_vat_rate_percent_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="topbar",
            name="css_hook",
            field=models.UUIDField(db_index=True, editable=False, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="dynamicpage",
            name="css_hook",
            field=models.UUIDField(db_index=True, editable=False, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="footer",
            name="css_hook",
            field=models.UUIDField(db_index=True, editable=False, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="footersection",
            name="css_hook",
            field=models.UUIDField(db_index=True, editable=False, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="footersectionlink",
            name="css_hook",
            field=models.UUIDField(db_index=True, editable=False, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="footersocialmedia",
            name="css_hook",
            field=models.UUIDField(db_index=True, editable=False, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="bottombar",
            name="css_hook",
            field=models.UUIDField(db_index=True, editable=False, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="bottombarlink",
            name="css_hook",
            field=models.UUIDField(db_index=True, editable=False, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="navbar",
            name="css_hook",
            field=models.UUIDField(db_index=True, editable=False, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="navbaritem",
            name="css_hook",
            field=models.UUIDField(db_index=True, editable=False, null=True, unique=True),
        ),
        migrations.RunPython(_backfill_css_hooks, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="topbar",
            name="css_hook",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name="dynamicpage",
            name="css_hook",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name="footer",
            name="css_hook",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name="footersection",
            name="css_hook",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name="footersectionlink",
            name="css_hook",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name="footersocialmedia",
            name="css_hook",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name="bottombar",
            name="css_hook",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name="bottombarlink",
            name="css_hook",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name="navbar",
            name="css_hook",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name="navbaritem",
            name="css_hook",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
