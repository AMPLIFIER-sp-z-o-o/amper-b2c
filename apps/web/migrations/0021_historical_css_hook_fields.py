import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("web", "0020_css_hook_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="historicaltopbar",
            name="css_hook",
            field=models.UUIDField(blank=True, db_index=True, default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="historicaldynamicpage",
            name="css_hook",
            field=models.UUIDField(blank=True, db_index=True, default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="historicalfooter",
            name="css_hook",
            field=models.UUIDField(blank=True, db_index=True, default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="historicalfootersection",
            name="css_hook",
            field=models.UUIDField(blank=True, db_index=True, default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="historicalfootersectionlink",
            name="css_hook",
            field=models.UUIDField(blank=True, db_index=True, default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="historicalfootersocialmedia",
            name="css_hook",
            field=models.UUIDField(blank=True, db_index=True, default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="historicalbottombar",
            name="css_hook",
            field=models.UUIDField(blank=True, db_index=True, default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="historicalbottombarlink",
            name="css_hook",
            field=models.UUIDField(blank=True, db_index=True, default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="historicalnavbar",
            name="css_hook",
            field=models.UUIDField(blank=True, db_index=True, default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="historicalnavbaritem",
            name="css_hook",
            field=models.UUIDField(blank=True, db_index=True, default=uuid.uuid4, editable=False, null=True),
        ),
    ]
