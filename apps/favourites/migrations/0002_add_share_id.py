"""
Add share_id field to WishList model.

This migration:
1. Adds the share_id field (nullable, no unique constraint)
2. Populates share_id for existing records with unique random values
3. Makes the field non-nullable and adds unique constraint
"""

import secrets
import string

from django.db import migrations, models


def _generate_share_id():
    chars = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(10))


def populate_share_ids(apps, schema_editor):
    WishList = apps.get_model("favourites", "WishList")
    used_ids = set()
    for wishlist in WishList.objects.all():
        share_id = _generate_share_id()
        while share_id in used_ids:
            share_id = _generate_share_id()
        used_ids.add(share_id)
        wishlist.share_id = share_id
        wishlist.save(update_fields=["share_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("favourites", "0001_initial"),
    ]

    operations = [
        # Step 1: Add field as nullable without index
        migrations.AddField(
            model_name="wishlist",
            name="share_id",
            field=models.CharField(
                blank=True,
                default="",
                editable=False,
                help_text="Unique, non-guessable identifier for sharing",
                max_length=10,
                verbose_name="Share ID",
            ),
            preserve_default=False,
        ),
        # Step 2: Populate existing records
        migrations.RunPython(populate_share_ids, migrations.RunPython.noop),
        # Step 3: Make unique and set proper default
        migrations.AlterField(
            model_name="wishlist",
            name="share_id",
            field=models.CharField(
                db_index=True,
                default=_generate_share_id,
                editable=False,
                help_text="Unique, non-guessable identifier for sharing",
                max_length=10,
                unique=True,
                verbose_name="Share ID",
            ),
        ),
    ]
