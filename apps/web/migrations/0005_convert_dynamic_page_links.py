from django.db import migrations


def _dynamic_page_url(dynamic_page):
    if not dynamic_page:
        return ""
    return f"/dynamic-page/{dynamic_page.slug}/{dynamic_page.pk}/"


def convert_dynamic_page_links(apps, schema_editor):
    navbar_item = apps.get_model("web", "NavbarItem")
    footer_section_link = apps.get_model("web", "FooterSectionLink")

    for item in (
        navbar_item.objects.select_related("dynamic_page")
        .filter(item_type="dynamic_page")
        .iterator()
    ):
        if item.dynamic_page_id:
            url = _dynamic_page_url(item.dynamic_page)
            label = item.label or item.dynamic_page.title
        else:
            url = item.url
            label = item.label

        item.item_type = "custom_link"
        if url:
            item.url = url
        if label:
            item.label = label
        item.dynamic_page = None
        item.save(update_fields=["item_type", "url", "label", "dynamic_page"])

    for link in (
        footer_section_link.objects.select_related("dynamic_page")
        .filter(link_type="dynamic_page")
        .iterator()
    ):
        if link.dynamic_page_id:
            url = _dynamic_page_url(link.dynamic_page)
            label = link.label or link.dynamic_page.title
        else:
            url = link.url
            label = link.label

        link.link_type = "custom_url"
        if url:
            link.url = url
        if label:
            link.label = label
        link.dynamic_page = None
        link.save(update_fields=["link_type", "url", "label", "dynamic_page"])


class Migration(migrations.Migration):
    dependencies = [
        ("web", "0004_dynamicpage_footersectionlink_link_type_and_more"),
    ]

    operations = [
        migrations.RunPython(convert_dynamic_page_links, migrations.RunPython.noop),
    ]
