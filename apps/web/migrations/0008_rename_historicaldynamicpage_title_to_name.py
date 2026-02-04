from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("web", "0007_rename_dynamicpage_title_to_name"),
    ]

    operations = [
        migrations.RenameField(
            model_name="historicaldynamicpage",
            old_name="title",
            new_name="name",
        ),
    ]
