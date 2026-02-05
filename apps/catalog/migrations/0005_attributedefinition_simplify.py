"""
Migration to simplify AttributeDefinition model:
- Remove display_name field
- Change name field to be the display name (max_length=150, not unique)
- Add slug field (AutoSlugField, unique)

Data migration:
1. Copy display_name values to name
2. Generate slug from the new name values
"""

from autoslug import AutoSlugField
from django.db import migrations, models
from django.utils.text import slugify


def copy_display_name_to_name_and_generate_slug(apps, schema_editor):
    """Copy display_name to name and generate slug from it."""
    AttributeDefinition = apps.get_model("catalog", "AttributeDefinition")
    
    for attr in AttributeDefinition.objects.all():
        # Copy display_name to name
        attr.name = attr.display_name
        # Generate unique slug
        base_slug = slugify(attr.name)
        slug = base_slug
        counter = 1
        while AttributeDefinition.objects.filter(slug=slug).exclude(pk=attr.pk).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        attr.slug = slug
        attr.save()


def reverse_copy_name_to_display_name(apps, schema_editor):
    """Reverse: copy name back to display_name."""
    AttributeDefinition = apps.get_model("catalog", "AttributeDefinition")
    
    for attr in AttributeDefinition.objects.all():
        attr.display_name = attr.name
        attr.name = slugify(attr.name)  # Convert to slug-like format
        attr.save()


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0004_add_attribute_tile_display_settings"),
    ]

    operations = [
        # Step 1: Add slug field (no index initially to avoid conflicts)
        migrations.AddField(
            model_name="attributedefinition",
            name="slug",
            field=models.CharField(max_length=255, blank=True, default=""),
            preserve_default=False,
        ),
        
        # Step 2: Also add slug to historical model
        migrations.AddField(
            model_name="historicalattributedefinition",
            name="slug",
            field=models.CharField(max_length=255, blank=True, default=""),
            preserve_default=False,
        ),
        
        # Step 3: Run data migration to populate name from display_name and generate slugs
        migrations.RunPython(
            copy_display_name_to_name_and_generate_slug,
            reverse_copy_name_to_display_name,
        ),
        
        # Step 4: Remove display_name field first (before altering name)
        migrations.RemoveField(
            model_name="attributedefinition",
            name="display_name",
        ),
        migrations.RemoveField(
            model_name="historicalattributedefinition",
            name="display_name",
        ),
        
        # Step 5: Remove unique constraint from name field and change max_length
        migrations.AlterField(
            model_name="attributedefinition",
            name="name",
            field=models.CharField(max_length=150, verbose_name="Name"),
        ),
        migrations.AlterField(
            model_name="historicalattributedefinition",
            name="name",
            field=models.CharField(max_length=150, verbose_name="Name"),
        ),
        
        # Step 6: Convert slug to AutoSlugField with unique constraint
        migrations.AlterField(
            model_name="attributedefinition",
            name="slug",
            field=AutoSlugField(always_update=False, populate_from="name", unique=True),
        ),
        migrations.AlterField(
            model_name="historicalattributedefinition",
            name="slug",
            field=AutoSlugField(always_update=False, db_index=True, editable=False, populate_from="name"),
        ),
        
        # Step 7: Update ordering
        migrations.AlterModelOptions(
            name="attributedefinition",
            options={"ordering": ["name"]},
        ),
    ]
