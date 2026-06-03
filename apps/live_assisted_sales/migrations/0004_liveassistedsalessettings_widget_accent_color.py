import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("live_assisted_sales", "0003_liveassistedsalessettings_site_public_key"),
    ]

    operations = [
        migrations.AddField(
            model_name="liveassistedsalessettings",
            name="widget_accent_color",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Hex colour used to theme the chat widget (launcher, header, buttons). "
                    "Leave blank to use the store brand colour."
                ),
                max_length=7,
                validators=[
                    django.core.validators.RegexValidator(
                        message="Enter a valid hex colour, e.g. #2563eb.",
                        regex="^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$",
                    )
                ],
                verbose_name="Widget accent colour",
            ),
        ),
    ]
