import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("homepage", "0013_css_hook_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="historicalbanner",
            name="css_hook",
            field=models.UUIDField(blank=True, db_index=True, default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="historicalhomepagesection",
            name="css_hook",
            field=models.UUIDField(blank=True, db_index=True, default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="historicalhomepagesectionbanner",
            name="css_hook",
            field=models.UUIDField(blank=True, db_index=True, default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="historicalhomepagesectioncategorybox",
            name="css_hook",
            field=models.UUIDField(blank=True, db_index=True, default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="historicalhomepagesectioncategoryitem",
            name="css_hook",
            field=models.UUIDField(blank=True, db_index=True, default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="historicalstorefrontherosection",
            name="css_hook",
            field=models.UUIDField(blank=True, db_index=True, default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="historicalstorefrontcategorybox",
            name="css_hook",
            field=models.UUIDField(blank=True, db_index=True, default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="historicalstorefrontcategoryitem",
            name="css_hook",
            field=models.UUIDField(blank=True, db_index=True, default=uuid.uuid4, editable=False, null=True),
        ),
    ]
