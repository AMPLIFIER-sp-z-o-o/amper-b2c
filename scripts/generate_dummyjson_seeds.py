import io
import json
import os
import re
import sys
import urllib.request
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import boto3
import django
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amplifier.settings")
django.setup()

from apps.media.models import MediaStorageSettings

BASE = Path("assets/seeds/generated")
HEADERS = {"User-Agent": "Mozilla/5.0"}
TARGET_PRODUCTS_PER_ROOT = 32

LEVEL1_SUBCATEGORY_TEMPLATES = [
    ("Featured", ["Top Rated", "Staff Picks"]),
    ("New", ["Just Arrived", "Fresh Picks"]),
    ("Popular", ["Best Sellers"]),
    ("Budget", []),
    ("Premium", []),
    ("Essentials", ["Everyday Picks"]),
    ("Seasonal", []),
]


def slugify(text: str) -> str:
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "item"


def write_json(name: str, payload) -> None:
    (BASE / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch_json(url: str):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def build_datasets(products_raw, categories_raw):
    slug_to_name = {entry["slug"]: (entry.get("name") or entry["slug"].replace("-", " ").title()) for entry in categories_raw}

    by_root = defaultdict(list)
    for product in products_raw:
        by_root[product["category"]].append(product)

    for root_slug in by_root:
        by_root[root_slug] = sorted(by_root[root_slug], key=lambda item: (-float(item.get("rating", 0) or 0), item["id"]))

    global_ranked_products = sorted(products_raw, key=lambda item: (-float(item.get("rating", 0) or 0), item["id"]))

    root_slugs = []
    for entry in categories_raw:
        slug = entry.get("slug")
        if slug and slug not in root_slugs:
            root_slugs.append(slug)
    for slug in sorted(by_root.keys()):
        if slug not in root_slugs:
            root_slugs.append(slug)

    categories = []
    root_meta = []
    next_category_id = 40

    for root_slug in root_slugs:
        root_id = next_category_id
        next_category_id += 1

        root_name = slug_to_name.get(root_slug, root_slug.replace("-", " ").title())
        root_slug_name = slugify(root_name)
        root_products = by_root.get(root_slug, [])

        level1_subcategories = []

        for parent_label, child_labels in LEVEL1_SUBCATEGORY_TEMPLATES:
            level1_id = next_category_id
            next_category_id += 1

            level1_name = f"{parent_label} {root_name}"
            level1_slug = slugify(level1_name)

            categories.append(
                {
                    "id": level1_id,
                    "name": level1_name,
                    "slug": level1_slug,
                    "parent_id": root_id,
                    "image": "",
                    "icon": "circle",
                }
            )

            nested_children = []
            for child_label in child_labels:
                child_id = next_category_id
                next_category_id += 1

                child_name = f"{child_label} {root_name}"
                child_slug = slugify(child_name)

                categories.append(
                    {
                        "id": child_id,
                        "name": child_name,
                        "slug": child_slug,
                        "parent_id": level1_id,
                        "image": "",
                        "icon": "circle",
                    }
                )

                nested_children.append(child_id)

            level1_subcategories.append(
                {
                    "id": level1_id,
                    "name": level1_name,
                    "children": nested_children,
                }
            )

        categories.append(
            {
                "id": root_id,
                "name": root_name,
                "slug": root_slug_name,
                "parent_id": None,
                "image": "",
                "icon": "circle",
            }
        )
        root_meta.append((root_slug, root_id, root_name, level1_subcategories, root_products))

    material_map = {
        "beauty": "Composite",
        "fragrances": "Glass",
        "skin-care": "Composite",
        "groceries": "Food Grade",
        "sunglasses": "Composite",
        "womens-bags": "Leather",
        "mens-shirts": "Cotton",
        "mens-shoes": "Leather",
        "womens-dresses": "Fabric",
        "womens-jewellery": "Metal",
        "womens-shoes": "Leather",
        "womens-watches": "Metal",
        "furniture": "Wood",
        "home-decoration": "Wood",
        "kitchen-accessories": "Steel",
        "laptops": "Aluminum",
        "smartphones": "Aluminum",
        "tablets": "Aluminum",
        "mobile-accessories": "Polymer",
        "motorcycle": "Metal",
        "vehicle": "Metal",
        "sports-accessories": "Polymer",
    }

    attribute_definitions = [
        {"id": 44, "name": "Category", "show_on_tile": True, "tile_display_order": 1},
        {"id": 45, "name": "Type", "show_on_tile": True, "tile_display_order": 2},
        {"id": 46, "name": "Brand", "show_on_tile": True, "tile_display_order": 3},
        {"id": 47, "name": "Material", "show_on_tile": True, "tile_display_order": 4},
        {"id": 48, "name": "Visual Label", "show_on_tile": False, "tile_display_order": 5},
    ]

    categories_by_id = {category["id"]: category for category in categories}

    next_option_id = [80]
    option_ids = {}
    attribute_options = []
    product_attribute_values = []

    def get_option_id(attribute_id: int, value: str) -> int:
        key = (attribute_id, value)
        if key in option_ids:
            return option_ids[key]

        option_id = next_option_id[0]
        next_option_id[0] += 1

        option_ids[key] = option_id
        attribute_options.append({"id": option_id, "attribute_id": attribute_id, "value": value})
        return option_id

    products = []
    root_generated_product_ids = {}
    next_product_id = 1

    for root_slug, root_id, root_name, level1_subcategories, grouped_products in root_meta:
        source_pool = grouped_products or global_ranked_products
        if not source_pool:
            continue

        selected_sources = [source_pool[index % len(source_pool)] for index in range(TARGET_PRODUCTS_PER_ROOT)]

        level1_ids = [subcategory["id"] for subcategory in level1_subcategories]
        level2_ids = [child_id for subcategory in level1_subcategories for child_id in subcategory["children"]]

        target_category_ids = [root_id] + level1_ids + level2_ids

        category_slots = list(target_category_ids)
        weighted_rotation = (
            [root_id] * 8
            + [category_id for category_id in level1_ids for _ in range(3)]
            + [category_id for category_id in level2_ids for _ in range(2)]
        )
        if not weighted_rotation:
            weighted_rotation = [root_id]

        remaining_slots = TARGET_PRODUCTS_PER_ROOT - len(category_slots)
        for index in range(max(0, remaining_slots)):
            category_slots.append(weighted_rotation[index % len(weighted_rotation)])

        generated_ids_for_root = []

        for index, source_product in enumerate(selected_sources[:TARGET_PRODUCTS_PER_ROOT]):
            category_id = category_slots[index]
            category_name = categories_by_id[category_id]["name"]

            title = (source_product.get("title") or f"Product {next_product_id}").strip()
            slug = f"{slugify(title)}-{next_product_id}"
            description = (source_product.get("description") or "").strip()
            brand = (source_product.get("brand") or "Generic").strip() or "Generic"
            tags = source_product.get("tags") or []
            visual_label = (tags[0] if tags else root_name).replace("-", " ").title()
            material = material_map.get(root_slug, "Mixed")

            price = Decimal(str(source_product.get("price", 0)))
            stock = int(source_product.get("stock", 0) or 0)
            rating = float(source_product.get("rating", 0) or 0)
            units_sold = max(1, int((rating + 1) * 12))

            product_id = next_product_id
            next_product_id += 1

            products.append(
                {
                    "id": product_id,
                    "name": title,
                    "slug": slug,
                    "category_id": category_id,
                    "status": "active" if stock > 0 else "disabled",
                    "price": f"{price:.2f}",
                    "stock": stock,
                    "sales_total": f"{units_sold:.2f}",
                    "revenue_total": f"{(price * Decimal(units_sold)):.2f}",
                    "sales_per_day": f"{max(1, int(rating * 2 + 1)):.2f}",
                    "sales_per_month": f"{max(5, int(rating * 18 + 5)):.2f}",
                    "description": description,
                    "_image_product_id": source_product["id"],
                }
            )

            generated_ids_for_root.append(product_id)

            for attribute_id, value in [
                (44, category_name),
                (45, root_name),
                (46, brand),
                (47, material),
                (48, visual_label),
            ]:
                option_id = get_option_id(attribute_id, value)
                product_attribute_values.append({"product_id": product_id, "option_id": option_id})

        root_generated_product_ids[root_id] = generated_ids_for_root

    category_recommended_products = []
    recommendation_id = 1
    for _, root_id, _, _, _ in root_meta:
        root_products_for_recommendation = root_generated_product_ids.get(root_id, [])
        for order, product_id in enumerate(root_products_for_recommendation[:4], start=1):
            category_recommended_products.append(
                {
                    "id": recommendation_id,
                    "category_id": root_id,
                    "product_id": product_id,
                    "order": order,
                }
            )
            recommendation_id += 1

    homepage_sections = json.loads((BASE / "homepage_sections_data.json").read_text(encoding="utf-8"))
    section_ids = [section["id"] for section in homepage_sections][:3] or [1]

    top_products = sorted(products, key=lambda item: (-float(item.get("sales_per_day", 0) or 0), item["id"]))[:18]
    homepage_section_products = []
    for index, product in enumerate(top_products, start=1):
        homepage_section_products.append(
            {
                "id": index,
                "section_id": section_ids[(index - 1) % len(section_ids)],
                "product_id": product["id"],
                "order": (index - 1) % 6,
            }
        )

    roots = sorted([category for category in categories if category["parent_id"] is None], key=lambda category: category["name"])
    selected_roots = roots[:16]
    icon_cycle = [
        "storefront/seed/computers.svg",
        "storefront/seed/gaming.svg",
        "storefront/seed/tablets.svg",
        "storefront/seed/fashion.svg",
        "storefront/seed/laptops.svg",
        "storefront/seed/watches.svg",
        "storefront/seed/accessories-tablets.svg",
        "storefront/seed/accessories.svg",
    ]

    homepage_section_category_items = []
    for index, category in enumerate(selected_roots, start=1):
        homepage_section_category_items.append(
            {
                "id": index,
                "category_box_id": 1 + ((index - 1) // 4),
                "name": category["name"],
                "image": icon_cycle[(index - 1) % len(icon_cycle)],
                "url": f"/category/{category['id']}/{category['slug']}/",
                "order": (index - 1) % 4,
            }
        )

    homepage_section_category_boxes = [
        {
            "id": 1,
            "section_id": 1,
            "title": "Top categories",
            "shop_link_text": "Shop now",
            "shop_link_url": "/products/",
            "order": 0,
        },
        {
            "id": 2,
            "section_id": 1,
            "title": "Popular departments",
            "shop_link_text": "Shop now",
            "shop_link_url": homepage_section_category_items[4]["url"] if len(homepage_section_category_items) > 4 else "/products/",
            "order": 1,
        },
        {
            "id": 3,
            "section_id": 21,
            "title": "Top promotions",
            "shop_link_text": "Show promotions",
            "shop_link_url": "/dynamic-page/promotions/2/",
            "order": 0,
        },
        {
            "id": 4,
            "section_id": 21,
            "title": "Shop by category",
            "shop_link_text": "Show promotions",
            "shop_link_url": "/products/",
            "order": 1,
        },
    ]

    first_root = roots[0]
    category_banners = [
        {
            "id": 1,
            "category_id": first_root["id"],
            "name": "Flowbite Category Banner 1 - iMac",
            "tab_title": "Computers",
            "image": "banners/seed/flowbite-carousel-1.jpg",
            "mobile_image": "",
            "url": f"/category/{first_root['id']}/{first_root['slug']}/",
            "is_active": True,
            "order": 0,
        },
        {
            "id": 2,
            "category_id": first_root["id"],
            "name": "Flowbite Category Banner 2 - Fashion",
            "tab_title": "New arrivals",
            "image": "banners/seed/flowbite-carousel-2.jpg",
            "mobile_image": "",
            "url": "/products/",
            "is_active": True,
            "order": 1,
        },
        {
            "id": 3,
            "category_id": first_root["id"],
            "name": "Flowbite Category Banner 3 - Gaming",
            "tab_title": "Gaming",
            "image": "banners/seed/flowbite-carousel-3.jpg",
            "mobile_image": "",
            "url": f"/category/{first_root['id']}/{first_root['slug']}/",
            "is_active": True,
            "order": 2,
        },
    ]

    return {
        "categories": categories,
        "products": products,
        "attribute_definitions": attribute_definitions,
        "attribute_options": attribute_options,
        "product_attribute_values": product_attribute_values,
        "category_recommended_products": category_recommended_products,
        "homepage_section_products": homepage_section_products,
        "homepage_section_category_items": homepage_section_category_items,
        "homepage_section_category_boxes": homepage_section_category_boxes,
        "category_banners": category_banners,
    }


def upload_images_to_s3(products_raw):
    settings = MediaStorageSettings.get_settings()
    client = boto3.client(
        "s3",
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )

    bucket = settings.aws_bucket_name
    prefix = (settings.aws_location or "media").strip("/")

    uploaded = 0
    failed = 0
    errors = []

    for product in products_raw:
        product_id = product["id"]
        image_url = (product.get("images") or [""])[0] or product.get("thumbnail")
        if not image_url:
            failed += 1
            continue

        try:
            request = urllib.request.Request(image_url, headers=HEADERS)
            with urllib.request.urlopen(request, timeout=90) as response:
                raw = response.read()

            image = Image.open(io.BytesIO(raw))
            if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
                image = image.convert("RGBA")
                white_background = Image.new("RGB", image.size, (255, 255, 255))
                white_background.paste(image, mask=image.split()[-1])
                image = white_background
            else:
                image = image.convert("RGB")

            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=94, optimize=True, progressive=True)
            buffer.seek(0)

            key = f"{prefix}/product-images/seed/product-{product_id}.jpg"

            client.upload_fileobj(buffer, bucket, key, ExtraArgs={"ContentType": "image/jpeg"})

            uploaded += 1
        except Exception as exception:
            failed += 1
            if len(errors) < 10:
                errors.append(
                    f"product_id={product_id} err={type(exception).__name__}: {exception} url={image_url}"
                )

    return uploaded, failed, errors


def main():
    products_raw = json.loads((BASE / "dummyjson_products_raw.json").read_text(encoding="utf-8"))
    categories_raw = json.loads((BASE / "dummyjson_categories_raw.json").read_text(encoding="utf-8"))

    datasets = build_datasets(products_raw, categories_raw)

    write_json("categories_data.json", datasets["categories"])
    write_json("products_data.json", datasets["products"])
    write_json("attribute_definitions_data.json", datasets["attribute_definitions"])
    write_json("attribute_options_data.json", datasets["attribute_options"])
    write_json("product_attribute_values_data.json", datasets["product_attribute_values"])
    write_json("category_recommended_products_data.json", datasets["category_recommended_products"])
    write_json("homepage_section_products_data.json", datasets["homepage_section_products"])
    write_json("homepage_section_category_items_data.json", datasets["homepage_section_category_items"])
    write_json("homepage_section_category_boxes_data.json", datasets["homepage_section_category_boxes"])
    write_json("category_banners_data.json", datasets["category_banners"])
    write_json("product_name_overrides.json", {})
    write_json("category_name_overrides.json", {})
    write_json("attribute_definition_name_overrides.json", {})

    uploaded, failed, errors = upload_images_to_s3(products_raw)

    print("generated_categories", len(datasets["categories"]))
    print("generated_products", len(datasets["products"]))
    print("generated_attribute_options", len(datasets["attribute_options"]))
    print("generated_pavs", len(datasets["product_attribute_values"]))
    print("uploaded_images", uploaded)
    print("failed_images", failed)
    if errors:
        print("sample_failures", errors)


if __name__ == "__main__":
    main()
