from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("web", "0005_convert_dynamic_page_links"),
    ]

    operations = [
        migrations.AlterField(
            model_name="dynamicpage",
            name="title",
            field=models.CharField(
                max_length=200,
                verbose_name="Name",
                help_text="Internal name for identification",
            ),
        ),
    ]
