from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("web", "0006_alter_dynamicpage_title"),
    ]

    operations = [
        migrations.RenameField(
            model_name="dynamicpage",
            old_name="title",
            new_name="name",
        ),
    ]
