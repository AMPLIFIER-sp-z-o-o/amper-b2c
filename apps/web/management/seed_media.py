import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
GENERATED_SEEDS_DIR = PROJECT_ROOT / "assets" / "seeds" / "generated"
GENERATED_MEDIA_DIR = GENERATED_SEEDS_DIR / "media"


def load_generated_seed_list(filename):
    path = GENERATED_SEEDS_DIR / filename
    if not path.exists():
        return []

    try:
        with open(path, encoding="utf-8") as file:
            payload = json.load(file)
            if isinstance(payload, list):
                return payload
    except Exception:
        pass

    return []


def load_generated_seed_dict(filename):
    path = GENERATED_SEEDS_DIR / filename
    if not path.exists():
        return {}

    try:
        with open(path, encoding="utf-8") as file:
            payload = json.load(file)
            if isinstance(payload, dict):
                return payload
    except Exception:
        pass

    return {}


def _normalize_media_path(value):
    if not isinstance(value, str):
        return None

    normalized = value.strip().strip("/")
    if not normalized:
        return None

    if normalized.startswith(("http://", "https://")):
        return None

    return normalized


def resolve_local_seed_media_path(relative_path):
    normalized = _normalize_media_path(relative_path)
    if not normalized:
        return None

    root = GENERATED_MEDIA_DIR.resolve()
    candidate = (GENERATED_MEDIA_DIR / normalized).resolve()
    if candidate != root and root not in candidate.parents:
        return None

    return candidate


def collect_seed_media_paths_from_generated_data():
    media_paths = set()

    for path in load_generated_seed_list("static_media_seed_files.json"):
        normalized = _normalize_media_path(path)
        if normalized:
            media_paths.add(normalized)

    model_media_fields = {
        "site_settings_data.json": ("logo", "default_image"),
        "categories_data.json": ("image",),
        "banners_data.json": ("image", "mobile_image"),
        "category_banners_data.json": ("image", "mobile_image"),
        "homepage_section_banners_data.json": ("image",),
        "homepage_section_category_items_data.json": ("image",),
    }

    for filename, fields in model_media_fields.items():
        for row in load_generated_seed_list(filename):
            for field in fields:
                normalized = _normalize_media_path(row.get(field))
                if normalized:
                    media_paths.add(normalized)

    for product in load_generated_seed_list("products_data.json"):
        product_id = product.get("_image_product_id", product.get("id"))
        if product_id is None:
            continue
        normalized = _normalize_media_path(f"product-images/seed/product-{product_id}.jpg")
        if normalized:
            media_paths.add(normalized)

    return sorted(media_paths)
