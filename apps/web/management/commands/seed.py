"""
Seed command for populating the database with predefined data.

It populates the current database with site settings, categories, products, etc.

Credentials loaded from environment variables (.env file):
- AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY -> MediaStorageSettings
- MEDIA_CDN_DOMAIN_URL -> MediaStorageSettings CDN domain (optional)
- GOOGLE_CLIENT_ID, GOOGLE_SECRET_ID -> SocialApp (Google OAuth)
- SMTP_PASSWORD -> SystemSettings (SendGrid API key)

Default superuser:
- Email: admin@example.com
- Password: admin

Usage:
    uv run manage.py seed
    uv run manage.py seed --local  # Use only local seed media files (no URL fallback)
    uv run manage.py seed --fast  # Skip history/media checks for faster local reset
    uv run manage.py seed --skip-users  # Skip superuser creation
"""

import os
import re
import json
from collections import defaultdict
from contextlib import contextmanager
from decimal import Decimal
from itertools import cycle
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialApp
from django.conf import settings
from django.contrib.sites.models import Site
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.utils import NotSupportedError
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify

from apps.catalog.models import (
    AttributeDefinition,
    AttributeOption,
    Category,
    CategoryBanner,
    CategoryRecommendedProduct,
    Product,
    ProductAttributeValue,
    ProductImage,
)
from apps.homepage.models import (
    Banner,
    BannerGroup,
    BannerSettings,
    BannerType,
    HomepageSection,
    HomepageSectionBanner,
    HomepageSectionCategoryBox,
    HomepageSectionCategoryItem,
    HomepageSectionProduct,
)
from apps.media.models import MediaStorageSettings
from apps.media.storage import DynamicMediaStorage
from apps.users.models import CustomUser, SocialAppSettings
from apps.web.management.seed_media import (
    collect_seed_media_paths_from_generated_data,
    resolve_local_seed_media_path,
)
from apps.web.models import (
    BottomBar,
    BottomBarLink,
    CustomCSS,
    DynamicPage,
    Footer,
    FooterSection,
    FooterSectionLink,
    FooterSocialMedia,
    Navbar,
    NavbarItem,
    SiteSettings,
    SystemSettings,
    TopBar,
)
from apps.cart.models import DeliveryMethod, PaymentMethod

# Site domain is read from SITE_DOMAIN env var (default: localhost:8000).
# On QA/production, set e.g. SITE_DOMAIN=amper-b2c.ampliapps.com
_SITE_DOMAIN = os.environ.get("SITE_DOMAIN", "localhost:8000")
_SITE_SCHEME = "http" if _SITE_DOMAIN.startswith("localhost") else "https"
_SITE_URL = f"{_SITE_SCHEME}://{_SITE_DOMAIN}"
_MEDIA_CDN_DOMAIN_URL = os.environ.get("MEDIA_CDN_DOMAIN_URL", "").strip()
if _MEDIA_CDN_DOMAIN_URL.startswith(("http://", "https://")):
    _MEDIA_CDN_DOMAIN_URL = _MEDIA_CDN_DOMAIN_URL.split("://", 1)[1]
_MEDIA_CDN_DOMAIN_URL = _MEDIA_CDN_DOMAIN_URL.strip("/")


def _load_generated_seed_overrides(filename):
    path = settings.BASE_DIR / "assets" / "seeds" / "generated" / filename
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


_PRODUCT_NAME_OVERRIDES = {
    int(key): value
    for key, value in _load_generated_seed_overrides("product_name_overrides.json").items()
    if str(key).isdigit() and isinstance(value, str) and value.strip()
}

_CATEGORY_NAME_OVERRIDES = {
    int(key): value
    for key, value in _load_generated_seed_overrides("category_name_overrides.json").items()
    if str(key).isdigit() and isinstance(value, str) and value.strip()
}

_ATTRIBUTE_DEFINITION_NAME_OVERRIDES = {
    int(key): value
    for key, value in _load_generated_seed_overrides("attribute_definition_name_overrides.json").items()
    if str(key).isdigit() and isinstance(value, str) and value.strip()
}


def _load_generated_seed_list(filename):
    path = settings.BASE_DIR / "assets" / "seeds" / "generated" / filename
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



def _load_generated_seed_dict(filename):
    path = settings.BASE_DIR / "assets" / "seeds" / "generated" / filename
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

SITES_DATA = _load_generated_seed_list("sites_data.json")
for _site in SITES_DATA:
    _site["domain"] = _SITE_DOMAIN

TOPBAR_DATA = _load_generated_seed_list("topbar_data.json")

CUSTOM_CSS_DATA = _load_generated_seed_list("custom_css_data.json")

SITE_SETTINGS_DATA = _load_generated_seed_list("site_settings_data.json")
for _site_settings in SITE_SETTINGS_DATA:
    _site_settings["site_url"] = _SITE_URL
    _currency = str(_site_settings.get("currency", "")).upper().strip()
    if _currency not in {SiteSettings.Currency.PLN, SiteSettings.Currency.EUR, SiteSettings.Currency.USD}:
        _currency = SiteSettings.Currency.USD
    _site_settings["currency"] = _currency

SYSTEM_SETTINGS_DATA = _load_generated_seed_list("system_settings_data.json")

DYNAMIC_PAGES_DATA = _load_generated_seed_list("dynamic_pages_data.json")

NAVBAR_DATA = _load_generated_seed_list("navbar_data.json")

FOOTER_DATA = _load_generated_seed_list("footer_data.json")

FOOTER_SECTIONS_DATA = _load_generated_seed_list("footer_sections_data.json")

FOOTER_SECTION_LINKS_DATA = _load_generated_seed_list("footer_section_links_data.json")

FOOTER_SOCIAL_MEDIA_DATA = _load_generated_seed_list("footer_social_media_data.json")

BOTTOMBAR_DATA = _load_generated_seed_list("bottombar_data.json")

BOTTOMBAR_LINKS_DATA = _load_generated_seed_list("bottombar_links_data.json")

CATEGORIES_DATA = _load_generated_seed_list("categories_data.json")

ATTRIBUTE_DEFINITIONS_DATA = _load_generated_seed_list("attribute_definitions_data.json")

ATTRIBUTE_OPTIONS_DATA = _load_generated_seed_list("attribute_options_data.json")

PRODUCTS_DATA = _load_generated_seed_list("products_data.json")

DELIVERY_METHODS_DATA = _load_generated_seed_list("delivery_methods_data.json")

PAYMENT_METHODS_DATA = _load_generated_seed_list("payment_methods_data.json")



def _build_product_images_data():
    return [
        {
            "id": index,
            "product_id": product["id"],
            "image": f"product-images/seed/product-{product.get('_image_product_id', product['id'])}.jpg",
            "alt_text": product["name"],
            "sort_order": 0,
        }
        for index, product in enumerate(PRODUCTS_DATA, start=1)
    ]

PRODUCT_ATTRIBUTE_VALUES_DATA = _load_generated_seed_list("product_attribute_values_data.json")

PRODUCT_IMAGES_DATA = _build_product_images_data()

BANNER_SETTINGS_DATA = _load_generated_seed_dict("banner_settings_data.json")

BANNERS_DATA = _load_generated_seed_list("banners_data.json")

HOMEPAGE_SECTIONS_DATA = _load_generated_seed_list("homepage_sections_data.json")

HOMEPAGE_SECTION_CATEGORY_BOXES_DATA = _load_generated_seed_list("homepage_section_category_boxes_data.json")

HOMEPAGE_SECTION_CATEGORY_ITEMS_DATA = _load_generated_seed_list("homepage_section_category_items_data.json")

HOMEPAGE_SECTION_PRODUCTS_DATA = _load_generated_seed_list("homepage_section_products_data.json")

HOMEPAGE_SECTION_BANNERS_DATA = _load_generated_seed_list("homepage_section_banners_data.json")

# =============================================================================
# Category Banners & Recommended Products
# =============================================================================

CATEGORY_BANNERS_DATA = _load_generated_seed_list("category_banners_data.json")

STATIC_MEDIA_SEED_FILES = _load_generated_seed_list("static_media_seed_files.json")

STATIC_MEDIA_SEED_SOURCES = _load_generated_seed_dict("static_media_seed_sources.json")

STATIC_MEDIA_FORCE_SYNC_FILES = set(_load_generated_seed_list("static_media_force_sync_files.json"))

CATEGORY_RECOMMENDED_PRODUCTS_DATA = _load_generated_seed_list("category_recommended_products_data.json")

MEDIA_STORAGE_SETTINGS_DATA = _load_generated_seed_dict("media_storage_settings_data.json")
MEDIA_STORAGE_SETTINGS_DATA["cdn_enabled"] = bool(_MEDIA_CDN_DOMAIN_URL)
MEDIA_STORAGE_SETTINGS_DATA["cdn_domain"] = _MEDIA_CDN_DOMAIN_URL
ALL_SEED_MEDIA_FILES = collect_seed_media_paths_from_generated_data()

# =============================================================================
# COMMAND
# =============================================================================


@contextmanager
def _disable_simple_history():
    previous = getattr(settings, "SIMPLE_HISTORY_ENABLED", True)
    settings.SIMPLE_HISTORY_ENABLED = False
    try:
        yield
    finally:
        settings.SIMPLE_HISTORY_ENABLED = previous


class Command(BaseCommand):
    help = "Seed database with predefined data"


    def add_arguments(self, parser):
        parser.add_argument(
            "--fast",
            action="store_true",
            help="Speed up seeding by skipping history generation and media validation checks",
        )
        parser.add_argument(
            "--with-history",
            action="store_true",
            help="Force history generation even in --fast mode",
        )
        parser.add_argument(
            "--skip-users",
            action="store_true",
            help="Skip creating the default superuser",
        )
        parser.add_argument(
            "--local",
            action="store_true",
            help="Use only local seed media files (assets/seeds/generated/media), disable URL fallback",
        )

    def handle(self, *args, **options):
        skip_users = options["skip_users"]
        fast_mode = options["fast"]
        with_history = options["with_history"]
        local_only = options["local"]

        self._skip_media_checks = fast_mode
        self._skip_history = fast_mode and not with_history
        self._local_only_media = local_only
        self._storage_exists_cache = {}
        self._warned_missing_paths = set()
        self._warned_seed_sync_failures = set()
        self._synced_local_paths = set()
        self._synced_remote_paths = set()
        self._logged_sync_paths = set()
        self._active_media_provider = "local"

        self.stdout.write(self.style.NOTICE("Seeding database with predefined data..."))
        if fast_mode:
            self.stdout.write("  Fast mode: enabled")
        if local_only:
            self.stdout.write("  Local media mode: enabled (URL fallback disabled)")

        with transaction.atomic():
            with _disable_simple_history():
                self._seed_sites()
                self._seed_topbar()
                self._seed_custom_css()
                self._seed_media_storage_settings()
                self._seed_static_media_assets()
                self._seed_site_settings()
                self._seed_system_settings()
                self._seed_dynamic_pages()
                self._seed_footer()
                self._seed_bottombar()
                self._seed_categories()
                self._seed_category_banners()
                self._seed_category_recommended_products()
                self._seed_navbar()
                self._seed_attributes()
                self._seed_products()
                self._seed_banners()
                self._seed_homepage_sections()
                self._seed_storefront_hero_section()
                self._seed_delivery_methods()
                self._seed_payment_methods()
                # MediaFile entries are auto-created by signals when Banner, ProductImage etc. are saved
                self._seed_social_apps()

                if not skip_users:
                    self._create_superuser()

                # Fix PostgreSQL sequences after inserting with explicit IDs
                self._fix_sequences()

        # Populate history outside the big seed transaction to avoid one huge final COMMIT.
        # Create initial history only once; skip when any historical records already exist.
        if self._skip_history:
            self.stdout.write("  History: skipped (fast mode)")
        elif self._history_exists():
            self.stdout.write("  History: skipped (already exists)")
        else:
            self._populate_history()

        self.stdout.write(self.style.SUCCESS("Database seeded successfully!"))

    def _is_s3_storage(self, storage):
        return hasattr(storage, "bucket") or storage.__class__.__name__ == "S3Boto3Storage"

    def _ensure_public_acl(self, storage, relative_path):
        if not self._is_s3_storage(storage):
            return

        try:
            from apps.media.storage import _build_s3_key

            media_settings = MediaStorageSettings.get_settings()
            key = _build_s3_key(relative_path, media_settings)
            storage.bucket.Object(key).Acl().put(ACL="public-read")
        except Exception:
            pass

    def _sync_from_local_seed_media(self, storage, relative_path, replace_existing=False):
        local_path = resolve_local_seed_media_path(relative_path)
        if not local_path or not local_path.exists() or not local_path.is_file():
            return False

        try:
            if replace_existing:
                try:
                    storage.delete(relative_path)
                except Exception:
                    pass

            with open(local_path, "rb") as local_file:
                storage.save(relative_path, ContentFile(local_file.read()))

            self._storage_exists_cache[relative_path] = True
            self._synced_local_paths.add(relative_path)
            self._ensure_public_acl(storage, relative_path)

            if relative_path not in self._logged_sync_paths:
                self._logged_sync_paths.add(relative_path)
                self.stdout.write(f"    Synced media from local seed: {relative_path}")

            return True
        except Exception as exc:
            if relative_path not in self._warned_seed_sync_failures:
                self._warned_seed_sync_failures.add(relative_path)
                self.stdout.write(
                    self.style.WARNING(
                        f"    Warning: Failed local media sync for {relative_path}: {exc}"
                    )
                )
            return False

    def _sync_from_remote_seed_source(self, storage, relative_path, replace_existing=False):
        if getattr(self, "_local_only_media", False):
            return False

        source_url = STATIC_MEDIA_SEED_SOURCES.get(relative_path)
        if not source_url:
            return False

        try:
            content = self._download_static_seed_asset(source_url)
            if replace_existing:
                try:
                    storage.delete(relative_path)
                except Exception:
                    pass

            storage.save(relative_path, ContentFile(content))
            self._storage_exists_cache[relative_path] = True
            self._synced_remote_paths.add(relative_path)
            self._ensure_public_acl(storage, relative_path)

            if relative_path not in self._logged_sync_paths:
                self._logged_sync_paths.add(relative_path)
                self.stdout.write(f"    Synced media from URL source: {relative_path}")

            return True
        except (HTTPError, URLError, OSError, TimeoutError) as exc:
            if relative_path not in self._warned_seed_sync_failures:
                self._warned_seed_sync_failures.add(relative_path)
                self.stdout.write(
                    self.style.WARNING(
                        f"    Warning: Failed URL media sync for {relative_path}: {exc}"
                    )
                )
            return False

    def _ensure_media_in_storage(self, storage, relative_path, warn_if_missing=True, force_sync=False):
        if getattr(self, "_skip_media_checks", False):
            return

        if not relative_path:
            return

        exists = self._storage_exists_cache.get(relative_path)
        if exists is None:
            try:
                exists = storage.exists(relative_path)
            except Exception:
                exists = False
            self._storage_exists_cache[relative_path] = exists

        if exists and not force_sync:
            self._ensure_public_acl(storage, relative_path)
            return

        if not getattr(self, "_local_only_media", False) and getattr(self, "_active_media_provider", "local") == "s3":
            if warn_if_missing and relative_path not in self._warned_missing_paths:
                self._warned_missing_paths.add(relative_path)
                self.stdout.write(self.style.WARNING(f"    Warning: Missing in storage: {relative_path}"))
            return

        if self._sync_from_local_seed_media(storage, relative_path, replace_existing=bool(exists and force_sync)):
            return

        try:
            exists_now = storage.exists(relative_path)
        except Exception:
            exists_now = False
        self._storage_exists_cache[relative_path] = exists_now

        if exists_now:
            self._ensure_public_acl(storage, relative_path)
            return

        if warn_if_missing and relative_path not in self._warned_missing_paths:
            self._warned_missing_paths.add(relative_path)
            self.stdout.write(self.style.WARNING(f"    Warning: Missing in storage: {relative_path}"))

    def _upload_if_missing(self, instance, field_name, relative_path, warn_if_missing=True):
        """Ensure referenced media file exists in active storage according to active provider mode."""
        image_field = getattr(instance, field_name)
        storage = image_field.storage
        self._ensure_media_in_storage(storage, relative_path, warn_if_missing=warn_if_missing)

    def _bulk_upsert_by_id(self, model, rows, update_fields, batch_size=1000):
        """Bulk upsert by explicit id with fallback for DB backends without conflict updates."""
        if not rows:
            return

        try:
            model.objects.bulk_create(
                [model(**row) for row in rows],
                batch_size=batch_size,
                update_conflicts=True,
                update_fields=update_fields,
                unique_fields=["id"],
            )
        except (NotSupportedError, TypeError):
            for row in rows:
                record_id = row["id"]
                defaults = {key: value for key, value in row.items() if key != "id"}
                model.objects.update_or_create(id=record_id, defaults=defaults)

    def _parse_datetime(self, dt_str):
        """Parse datetime string."""
        if not dt_str:
            return None
        return parse_datetime(dt_str)

    def _download_static_seed_asset(self, source_url, timeout=30):
        request = Request(source_url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=timeout) as response:
            return response.read()

    def _seed_static_media_assets(self):
        """Ensure all seed media files exist in active storage."""
        if getattr(self, "_skip_media_checks", False):
            self.stdout.write("  Seed media assets: skipped (fast mode)")
            return

        storage = DynamicMediaStorage()
        missing = 0
        for relative_path in ALL_SEED_MEDIA_FILES:
            force_sync = relative_path in STATIC_MEDIA_FORCE_SYNC_FILES
            self._ensure_media_in_storage(
                storage,
                relative_path,
                warn_if_missing=True,
                force_sync=force_sync,
            )
            if self._storage_exists_cache.get(relative_path):
                continue
            missing += 1

        available = len(ALL_SEED_MEDIA_FILES) - missing
        self.stdout.write(
            "  Seed media assets: "
            f"{len(ALL_SEED_MEDIA_FILES)} records "
            f"({available} available, {missing} missing, "
            f"{len(self._synced_local_paths)} synced from local, "
            f"{len(self._synced_remote_paths)} synced from URL)"
        )

    def _seed_sites(self):
        """Seed Site model."""
        self._bulk_upsert_by_id(
            Site,
            [{"id": item["id"], "domain": item["domain"], "name": item["name"]} for item in SITES_DATA],
            update_fields=["domain", "name"],
        )
        self.stdout.write(f"  Site: {len(SITES_DATA)} records")

    def _seed_topbar(self):
        """Seed TopBar model."""
        self._bulk_upsert_by_id(
            TopBar,
            [
                {
                    "id": item["id"],
                    "name": item["name"],
                    "singleton_key": item["singleton_key"],
                    "content_type": item["content_type"],
                    "background_color": item["background_color"],
                    "text": item["text"],
                    "link_label": item["link_label"],
                    "link_url": item["link_url"],
                    "custom_html": item["custom_html"],
                    "custom_css": item["custom_css"],
                    "custom_js": item["custom_js"],
                    "is_active": item["is_active"],
                    "available_from": self._parse_datetime(item["available_from"]),
                    "available_to": self._parse_datetime(item["available_to"]),
                    "order": item["order"],
                }
                for item in TOPBAR_DATA
            ],
            update_fields=[
                "name",
                "singleton_key",
                "content_type",
                "background_color",
                "text",
                "link_label",
                "link_url",
                "custom_html",
                "custom_css",
                "custom_js",
                "is_active",
                "available_from",
                "available_to",
                "order",
            ],
        )
        self.stdout.write(f"  TopBar: {len(TOPBAR_DATA)} records")

    def _seed_custom_css(self):
        """Seed CustomCSS model."""
        self._bulk_upsert_by_id(
            CustomCSS,
            [
                {
                    "id": item["id"],
                    "custom_css": item["custom_css"],
                    "custom_css_active": item["custom_css_active"],
                }
                for item in CUSTOM_CSS_DATA
            ],
            update_fields=["custom_css", "custom_css_active"],
        )
        self.stdout.write(f"  CustomCSS: {len(CUSTOM_CSS_DATA)} records")

    def _seed_site_settings(self):
        """Seed SiteSettings model."""
        self._bulk_upsert_by_id(
            SiteSettings,
            [
                {
                    "id": item["id"],
                    "store_name": item["store_name"],
                    "site_url": item["site_url"],
                    "description": item["description"],
                    "keywords": item["keywords"],
                    "default_image": item["default_image"],
                    "currency": item["currency"],
                    "logo": item.get("logo", ""),
                }
                for item in SITE_SETTINGS_DATA
            ],
            update_fields=[
                "store_name",
                "site_url",
                "description",
                "keywords",
                "default_image",
                "currency",
                "logo",
            ],
        )
        site_settings_probe = SiteSettings()
        for item in SITE_SETTINGS_DATA:
            if item.get("logo"):
                self._upload_if_missing(site_settings_probe, "logo", item["logo"])
        self.stdout.write(f"  SiteSettings: {len(SITE_SETTINGS_DATA)} records")

    def _seed_system_settings(self):
        """Seed SystemSettings model (SMTP, Turnstile config)."""
        from apps.utils.encryption import encrypt_value

        smtp_password = os.environ.get("SMTP_PASSWORD", "")

        rows = []
        for item in SYSTEM_SETTINGS_DATA:
            row = {
                "id": item["id"],
                "smtp_host": item["smtp_host"],
                "smtp_port": item["smtp_port"],
                "smtp_username": item["smtp_username"],
                "smtp_use_tls": item["smtp_use_tls"],
                "smtp_use_ssl": item["smtp_use_ssl"],
                "smtp_default_from_email": item["smtp_default_from_email"],
                "smtp_timeout": item["smtp_timeout"],
                "smtp_enabled": item["smtp_enabled"],
                "turnstile_enabled": item["turnstile_enabled"],
            }
            if smtp_password:
                row["smtp_password_encrypted"] = encrypt_value(smtp_password)
            rows.append(row)

        update_fields = [
            "smtp_host",
            "smtp_port",
            "smtp_username",
            "smtp_use_tls",
            "smtp_use_ssl",
            "smtp_default_from_email",
            "smtp_timeout",
            "smtp_enabled",
            "turnstile_enabled",
        ]
        if smtp_password:
            update_fields.append("smtp_password_encrypted")

        self._bulk_upsert_by_id(
            SystemSettings,
            rows,
            update_fields=update_fields,
        )
        self.stdout.write(f"  SystemSettings: {len(SYSTEM_SETTINGS_DATA)} records")

    def _seed_dynamic_pages(self):
        """Seed DynamicPage model."""
        self._bulk_upsert_by_id(
            DynamicPage,
            [
                {
                    "id": item["id"],
                    "name": item["name"],
                    "slug": item["slug"],
                    "meta_title": item.get("meta_title", ""),
                    "meta_description": item.get("meta_description", ""),
                    "is_active": item.get("is_active", True),
                    "exclude_from_sitemap": item.get("exclude_from_sitemap", False),
                    "seo_noindex": item.get("seo_noindex", False),
                    "content": item.get("content", ""),
                }
                for item in DYNAMIC_PAGES_DATA
            ],
            update_fields=[
                "name",
                "slug",
                "meta_title",
                "meta_description",
                "is_active",
                "exclude_from_sitemap",
                "seo_noindex",
                "content",
            ],
        )
        self.stdout.write(f"  DynamicPage: {len(DYNAMIC_PAGES_DATA)} records")

    def _seed_footer(self):
        """Seed Footer and related models."""
        self._bulk_upsert_by_id(
            Footer,
            [
                {
                    "id": item["id"],
                    "singleton_key": item["singleton_key"],
                    "content_type": item["content_type"],
                    "custom_html": item["custom_html"],
                    "custom_css": item["custom_css"],
                    "custom_js": item["custom_js"],
                    "is_active": item["is_active"],
                }
                for item in FOOTER_DATA
            ],
            update_fields=["singleton_key", "content_type", "custom_html", "custom_css", "custom_js", "is_active"],
        )
        self.stdout.write(f"  Footer: {len(FOOTER_DATA)} records")

        self._bulk_upsert_by_id(
            FooterSection,
            [
                {
                    "id": item["id"],
                    "footer_id": item["footer_id"],
                    "name": item["name"],
                    "order": item["order"],
                }
                for item in FOOTER_SECTIONS_DATA
            ],
            update_fields=["footer", "name", "order"],
        )
        self.stdout.write(f"  FooterSection: {len(FOOTER_SECTIONS_DATA)} records")

        self._bulk_upsert_by_id(
            FooterSectionLink,
            [
                {
                    "id": item["id"],
                    "section_id": item["section_id"],
                    "label": item.get("label", ""),
                    "url": item.get("url", ""),
                    "link_type": item.get("link_type", "custom_url"),
                    "dynamic_page_id": item.get("dynamic_page_id"),
                    "order": item["order"],
                }
                for item in FOOTER_SECTION_LINKS_DATA
            ],
            update_fields=["section", "label", "url", "link_type", "dynamic_page", "order"],
        )
        self.stdout.write(f"  FooterSectionLink: {len(FOOTER_SECTION_LINKS_DATA)} records")

        self._bulk_upsert_by_id(
            FooterSocialMedia,
            [
                {
                    "id": item["id"],
                    "footer_id": item["footer_id"],
                    "platform": item["platform"],
                    "label": item["label"],
                    "url": item["url"],
                    "is_active": item["is_active"],
                    "order": item["order"],
                }
                for item in FOOTER_SOCIAL_MEDIA_DATA
            ],
            update_fields=["footer", "platform", "label", "url", "is_active", "order"],
        )
        self.stdout.write(f"  FooterSocialMedia: {len(FOOTER_SOCIAL_MEDIA_DATA)} records")

    def _seed_bottombar(self):
        """Seed BottomBar and related models."""
        self._bulk_upsert_by_id(
            BottomBar,
            [
                {
                    "id": item["id"],
                    "singleton_key": item["singleton_key"],
                    "is_active": item["is_active"],
                }
                for item in BOTTOMBAR_DATA
            ],
            update_fields=["singleton_key", "is_active"],
        )
        self.stdout.write(f"  BottomBar: {len(BOTTOMBAR_DATA)} records")

        self._bulk_upsert_by_id(
            BottomBarLink,
            [
                {
                    "id": item["id"],
                    "bottom_bar_id": item["bottom_bar_id"],
                    "label": item["label"],
                    "url": item["url"],
                    "order": item["order"],
                }
                for item in BOTTOMBAR_LINKS_DATA
            ],
            update_fields=["bottom_bar", "label", "url", "order"],
        )
        self.stdout.write(f"  BottomBarLink: {len(BOTTOMBAR_LINKS_DATA)} records")

    def _seed_navbar(self):
        """Seed Navbar and default custom navigation items mirroring standard categories."""
        for item in NAVBAR_DATA:
            Navbar.objects.update_or_create(
                id=item["id"],
                defaults={
                    "singleton_key": item["singleton_key"],
                    "mode": item["mode"],
                },
            )
        self.stdout.write(f"  Navbar: {len(NAVBAR_DATA)} records")

        navbar = Navbar.get_settings()

        # Create custom navbar items matching standard (alphabetical root categories)
        # Seed first 8 categories as custom items example
        root_categories = list(Category.objects.filter(parent__isnull=True).order_by("name")[:8])

        # Clear existing items for a clean mirror
        NavbarItem.objects.filter(navbar=navbar).delete()

        navbar_items = []
        for index, category in enumerate(root_categories, start=1):
            navbar_items.append(
                NavbarItem(
                    navbar=navbar,
                    item_type=NavbarItem.ItemType.CATEGORY,
                    category=category,
                    label="",
                    url="",
                    open_in_new_tab=False,
                    label_color="",
                    icon="",
                    order=index,
                    is_active=True,
                )
            )

        # Add separator at position 9
        navbar_items.append(
            NavbarItem(
                navbar=navbar,
                item_type=NavbarItem.ItemType.SEPARATOR,
                category=None,
                label="",
                url="",
                open_in_new_tab=False,
                label_color="",
                icon="",
                order=9,
                is_active=True,
            )
        )

        # Add "Promotions" custom link at position 10 with red color
        navbar_items.append(
            NavbarItem(
                navbar=navbar,
                item_type=NavbarItem.ItemType.CUSTOM_LINK,
                category=None,
                label="Promotions",
                url="/dynamic-page/promotions/2/",
                open_in_new_tab=False,
                label_color="#dc2626",
                icon="",
                order=10,
                is_active=True,
            )
        )

        dynamic_page = DynamicPage.objects.filter(slug="privacy-policy").first()
        if dynamic_page:
            navbar_items.append(
                NavbarItem(
                    navbar=navbar,
                    item_type=NavbarItem.ItemType.CUSTOM_LINK,
                    dynamic_page=None,
                    category=None,
                    label=dynamic_page.name,
                    url=dynamic_page.get_absolute_url(),
                    open_in_new_tab=False,
                    label_color="",
                    icon="",
                    order=11,
                    is_active=True,
                )
            )

        if navbar_items:
            NavbarItem.objects.bulk_create(navbar_items)
        self.stdout.write(f"  NavbarItem: {len(navbar_items)} records")

    def _seed_categories(self):
        """Seed Category model."""
        # First pass: create categories without parent_id
        self._bulk_upsert_by_id(
            Category,
            [
                {
                    "id": item["id"],
                    "name": item["name"],
                    "slug": item["slug"],
                    "parent_id": None,
                    "image": item["image"],
                    "icon": item.get("icon", "circle"),
                }
                for item in CATEGORIES_DATA
            ],
            update_fields=["name", "slug", "parent", "image", "icon"],
        )
        # Second pass: set parent_id
        parent_updates = [
            Category(id=item["id"], parent_id=item["parent_id"])
            for item in CATEGORIES_DATA
            if item["parent_id"]
        ]
        if parent_updates:
            Category.objects.bulk_update(parent_updates, ["parent"], batch_size=1000)
        self.stdout.write(f"  Category: {len(CATEGORIES_DATA)} records")

    def _seed_category_banners(self):
        """Seed CategoryBanner models."""
        for item in CATEGORY_BANNERS_DATA:
            obj, created = CategoryBanner.objects.update_or_create(
                id=item["id"],
                defaults={
                    "category_id": item["category_id"],
                    "name": item["name"],
                    "tab_title": item.get("tab_title", ""),
                    "image": item["image"],
                    "mobile_image": item.get("mobile_image", ""),
                    "url": item.get("url", ""),
                    "is_active": item.get("is_active", True),
                    "order": item.get("order", 0),
                },
            )
            self._upload_if_missing(
                obj,
                "image",
                item["image"],
            )
            if item.get("mobile_image"):
                self._upload_if_missing(
                    obj,
                    "mobile_image",
                    item["mobile_image"],
                )
        self.stdout.write(f"  CategoryBanner: {len(CATEGORY_BANNERS_DATA)} records")

    def _seed_category_recommended_products(self):
        """Seed CategoryRecommendedProduct models."""
        self._bulk_upsert_by_id(
            CategoryRecommendedProduct,
            [
                {
                    "id": item["id"],
                    "category_id": item["category_id"],
                    "product_id": item["product_id"],
                    "order": item.get("order", 0),
                }
                for item in CATEGORY_RECOMMENDED_PRODUCTS_DATA
            ],
            update_fields=["category", "product", "order"],
        )
        self.stdout.write(f"  CategoryRecommendedProduct: {len(CATEGORY_RECOMMENDED_PRODUCTS_DATA)} records")

    def _seed_attributes(self):
        """Seed AttributeDefinition and AttributeOption models."""
        self._bulk_upsert_by_id(
            AttributeDefinition,
            [
                {
                    "id": item["id"],
                    "name": item["name"],
                    "show_on_tile": item.get("show_on_tile", True),
                    "tile_display_order": item.get("tile_display_order", 0),
                }
                for item in ATTRIBUTE_DEFINITIONS_DATA
            ],
            update_fields=["name", "show_on_tile", "tile_display_order"],
        )
        self.stdout.write(f"  AttributeDefinition: {len(ATTRIBUTE_DEFINITIONS_DATA)} records")

        self._bulk_upsert_by_id(
            AttributeOption,
            [
                {
                    "id": item["id"],
                    "attribute_id": item["attribute_id"],
                    "value": item["value"],
                }
                for item in ATTRIBUTE_OPTIONS_DATA
            ],
            update_fields=["attribute", "value"],
        )
        self.stdout.write(f"  AttributeOption: {len(ATTRIBUTE_OPTIONS_DATA)} records")

    def _seed_products(self):
        """Seed Product and related models."""
        self._bulk_upsert_by_id(
            Product,
            [
                {
                    "id": item["id"],
                    "name": item["name"],
                    "slug": item["slug"],
                    "category_id": item["category_id"],
                    "status": item["status"],
                    "price": Decimal(item["price"]),
                    "stock": item["stock"],
                    "sales_total": Decimal(item["sales_total"]),
                    "revenue_total": Decimal(item["revenue_total"]),
                    "sales_per_day": Decimal(item["sales_per_day"]),
                    "sales_per_month": Decimal(item["sales_per_month"]),
                    "description": item["description"],
                }
                for item in PRODUCTS_DATA
            ],
            update_fields=[
                "name",
                "slug",
                "category",
                "status",
                "price",
                "stock",
                "sales_total",
                "revenue_total",
                "sales_per_day",
                "sales_per_month",
                "description",
            ],
        )
        self.stdout.write(f"  Product: {len(PRODUCTS_DATA)} records")

        seeded_image_ids = {item["id"] for item in PRODUCT_IMAGES_DATA}
        ProductImage.objects.exclude(id__in=seeded_image_ids).delete()

        self._bulk_upsert_by_id(
            ProductImage,
            [
                {
                    "id": item["id"],
                    "product_id": item["product_id"],
                    "image": item["image"],
                    "alt_text": item["alt_text"],
                    "sort_order": item["sort_order"],
                }
                for item in PRODUCT_IMAGES_DATA
            ],
            update_fields=["product", "image", "alt_text", "sort_order"],
        )
        product_image_probe = ProductImage()
        for item in PRODUCT_IMAGES_DATA:
            self._upload_if_missing(product_image_probe, "image", item["image"], warn_if_missing=False)
        self.stdout.write(f"  ProductImage: {len(PRODUCT_IMAGES_DATA)} records")

        ProductAttributeValue.objects.bulk_create(
            [
                ProductAttributeValue(
                    product_id=item["product_id"],
                    option_id=item["option_id"],
                )
                for item in PRODUCT_ATTRIBUTE_VALUES_DATA
            ],
            ignore_conflicts=True,
            batch_size=2000,
        )
        self.stdout.write(f"  ProductAttributeValue: {len(PRODUCT_ATTRIBUTE_VALUES_DATA)} records")

    def _seed_banners(self):
        """Seed BannerGroup, BannerSettings and Banner models."""
        # First, ensure BannerGroup instances exist for each type
        content_group, _ = BannerGroup.objects.update_or_create(
            banner_type=BannerType.CONTENT,
            defaults={
                "is_active": BANNER_SETTINGS_DATA["active_banner_type"] == "content",
                "available_from": self._parse_datetime(BANNER_SETTINGS_DATA["available_from"]),
                "available_to": self._parse_datetime(BANNER_SETTINGS_DATA["available_to"]),
            },
        )
        simple_group, _ = BannerGroup.objects.update_or_create(
            banner_type=BannerType.SIMPLE,
            defaults={
                "is_active": BANNER_SETTINGS_DATA["active_banner_type"] == "simple",
                "available_from": self._parse_datetime(BANNER_SETTINGS_DATA["available_from"]),
                "available_to": self._parse_datetime(BANNER_SETTINGS_DATA["available_to"]),
            },
        )
        self.stdout.write("  BannerGroup: 2 records")

        # Seed the legacy settings singleton for backwards compatibility
        settings_obj = BannerSettings.get_settings()
        settings_obj.active_banner_type = BANNER_SETTINGS_DATA["active_banner_type"]
        settings_obj.available_from = self._parse_datetime(BANNER_SETTINGS_DATA["available_from"])
        settings_obj.available_to = self._parse_datetime(BANNER_SETTINGS_DATA["available_to"])
        settings_obj.save()
        self.stdout.write("  BannerSettings: configured")

        # Map banner types to groups
        group_map = {
            "content": content_group,
            "simple": simple_group,
        }

        # Then seed the banners
        for item in BANNERS_DATA:
            defaults = {
                "group": group_map.get(item["banner_type"]),
                "banner_type": item["banner_type"],
                "name": item["name"],
                "image": item["image"],
                "mobile_image": item["mobile_image"],
                "url": item.get("url", ""),
                "is_active": item["is_active"],
                "order": item["order"],
                "available_from": self._parse_datetime(item.get("available_from")),
                "available_to": self._parse_datetime(item.get("available_to")),
            }
            # Add content banner fields if present
            if "badge_label" in item:
                defaults.update(
                    {
                        "badge_label": item.get("badge_label", ""),
                        "badge_text": item.get("badge_text", ""),
                        "title": item.get("title", ""),
                        "subtitle": item.get("subtitle", ""),
                        "text_alignment": item.get("text_alignment", "left"),
                        "overlay_opacity": item.get("overlay_opacity", 50),
                        "primary_button_text": item.get("primary_button_text", ""),
                        "primary_button_url": item.get("primary_button_url", "#"),
                        "primary_button_open_in_new_tab": item.get("primary_button_open_in_new_tab", False),
                        "primary_button_icon": item.get("primary_button_icon", ""),
                        "secondary_button_text": item.get("secondary_button_text", ""),
                        "secondary_button_url": item.get("secondary_button_url", "#"),
                        "secondary_button_open_in_new_tab": item.get("secondary_button_open_in_new_tab", False),
                        "secondary_button_icon": item.get("secondary_button_icon", ""),
                    }
                )
            obj, created = Banner.objects.update_or_create(
                id=item["id"],
                defaults=defaults,
            )
            # Ensure images are uploaded to storage
            self._upload_if_missing(
                obj,
                "image",
                item["image"],
            )
            if item.get("mobile_image"):
                self._upload_if_missing(
                    obj,
                    "mobile_image",
                    item["mobile_image"],
                    )
        self.stdout.write(f"  Banner: {len(BANNERS_DATA)} records")

    def _seed_homepage_sections(self):
        """Seed HomepageSection and related models."""
        section_rows = []
        for item in HOMEPAGE_SECTIONS_DATA:
            row = {
                "id": item["id"],
                "section_type": item["section_type"],
                "name": item["name"],
                "title": item["title"],
                "custom_html": item["custom_html"],
                "custom_css": item["custom_css"],
                "custom_js": item["custom_js"],
                "is_enabled": item["is_enabled"],
                "available_from": self._parse_datetime(item["available_from"]),
                "available_to": self._parse_datetime(item["available_to"]),
                "order": item["order"],
                "subtitle": "",
                "primary_button_text": "",
                "primary_button_url": "",
                "primary_button_open_in_new_tab": False,
                "secondary_button_text": "",
                "secondary_button_url": "",
                "secondary_button_open_in_new_tab": False,
            }
            if item["section_type"] == "storefront_hero":
                row.update(
                    {
                        "subtitle": item.get("subtitle", ""),
                        "primary_button_text": item.get("primary_button_text", ""),
                        "primary_button_url": item.get("primary_button_url", ""),
                        "primary_button_open_in_new_tab": item.get("primary_button_open_in_new_tab", False),
                        "secondary_button_text": item.get("secondary_button_text", ""),
                        "secondary_button_url": item.get("secondary_button_url", ""),
                        "secondary_button_open_in_new_tab": item.get("secondary_button_open_in_new_tab", False),
                    }
                )
            section_rows.append(row)

        self._bulk_upsert_by_id(
            HomepageSection,
            section_rows,
            update_fields=[
                "section_type",
                "name",
                "title",
                "custom_html",
                "custom_css",
                "custom_js",
                "is_enabled",
                "available_from",
                "available_to",
                "order",
                "subtitle",
                "primary_button_text",
                "primary_button_url",
                "primary_button_open_in_new_tab",
                "secondary_button_text",
                "secondary_button_url",
                "secondary_button_open_in_new_tab",
            ],
        )
        self.stdout.write(f"  HomepageSection: {len(HOMEPAGE_SECTIONS_DATA)} records")

        self._bulk_upsert_by_id(
            HomepageSectionProduct,
            [
                {
                    "id": item["id"],
                    "section_id": item["section_id"],
                    "product_id": item["product_id"],
                    "order": item["order"],
                }
                for item in HOMEPAGE_SECTION_PRODUCTS_DATA
            ],
            update_fields=["section", "product", "order"],
        )
        self.stdout.write(f"  HomepageSectionProduct: {len(HOMEPAGE_SECTION_PRODUCTS_DATA)} records")

        self._bulk_upsert_by_id(
            HomepageSectionBanner,
            [
                {
                    "id": item["id"],
                    "section_id": item["section_id"],
                    "name": item["name"],
                    "image": item["image"],
                    "url": item["url"],
                    "order": item["order"],
                }
                for item in HOMEPAGE_SECTION_BANNERS_DATA
            ],
            update_fields=["section", "name", "image", "url", "order"],
        )
        section_banner_probe = HomepageSectionBanner()
        for item in HOMEPAGE_SECTION_BANNERS_DATA:
            self._upload_if_missing(section_banner_probe, "image", item["image"])
        self.stdout.write(f"  HomepageSectionBanner: {len(HOMEPAGE_SECTION_BANNERS_DATA)} records")

        # Seed category boxes for storefront hero sections
        self._bulk_upsert_by_id(
            HomepageSectionCategoryBox,
            [
                {
                    "id": item["id"],
                    "section_id": item["section_id"],
                    "title": item["title"],
                    "shop_link_text": item["shop_link_text"],
                    "shop_link_url": item["shop_link_url"],
                    "order": item["order"],
                }
                for item in HOMEPAGE_SECTION_CATEGORY_BOXES_DATA
            ],
            update_fields=["section", "title", "shop_link_text", "shop_link_url", "order"],
        )
        self.stdout.write(f"  HomepageSectionCategoryBox: {len(HOMEPAGE_SECTION_CATEGORY_BOXES_DATA)} records")

        self._bulk_upsert_by_id(
            HomepageSectionCategoryItem,
            [
                {
                    "id": item["id"],
                    "category_box_id": item["category_box_id"],
                    "name": item["name"],
                    "image": item["image"],
                    "url": item["url"],
                    "order": item["order"],
                }
                for item in HOMEPAGE_SECTION_CATEGORY_ITEMS_DATA
            ],
            update_fields=["category_box", "name", "image", "url", "order"],
        )
        section_category_item_probe = HomepageSectionCategoryItem()
        for item in HOMEPAGE_SECTION_CATEGORY_ITEMS_DATA:
            self._upload_if_missing(section_category_item_probe, "image", item["image"])
        self.stdout.write(f"  HomepageSectionCategoryItem: {len(HOMEPAGE_SECTION_CATEGORY_ITEMS_DATA)} records")

    def _seed_storefront_hero_section(self):
        """Legacy storefront hero section - now handled via HomepageSection with type storefront_hero."""
        # Category boxes and items are now seeded in _seed_homepage_sections
        self.stdout.write("  StorefrontHeroSection: skipped (using section type instead)")

    def _seed_media_storage_settings(self):
        """Seed MediaStorageSettings; provider comes from env (or forced local mode)."""
        if MEDIA_STORAGE_SETTINGS_DATA:
            settings_existed = MediaStorageSettings.objects.filter(pk=1).exists()
            settings_obj = MediaStorageSettings.get_settings()

            aws_access_key = os.environ.get("AWS_ACCESS_KEY_ID", "").strip()
            aws_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip()
            aws_bucket_name = os.environ.get("AWS_STORAGE_BUCKET_NAME", "").strip()
            default_bucket_name = str(MEDIA_STORAGE_SETTINGS_DATA.get("aws_bucket_name", "")).strip()
            resolved_bucket_name = aws_bucket_name or default_bucket_name
            s3_env_ready = bool(aws_access_key and aws_secret_key and resolved_bucket_name)

            if getattr(self, "_local_only_media", False):
                settings_obj.provider_type = "local"
            else:
                settings_obj.provider_type = "s3" if s3_env_ready else "local"

            if settings_obj.provider_type not in {"local", "s3"}:
                settings_obj.provider_type = "s3" if s3_env_ready else "local"

            if not settings_existed:
                settings_obj.aws_bucket_name = MEDIA_STORAGE_SETTINGS_DATA.get("aws_bucket_name", "")
                settings_obj.aws_region = MEDIA_STORAGE_SETTINGS_DATA.get("aws_region", settings_obj.aws_region)
                settings_obj.aws_location = MEDIA_STORAGE_SETTINGS_DATA.get("aws_location", settings_obj.aws_location)

            settings_obj.cdn_enabled = MEDIA_STORAGE_SETTINGS_DATA["cdn_enabled"]
            settings_obj.cdn_domain = MEDIA_STORAGE_SETTINGS_DATA["cdn_domain"]

            if resolved_bucket_name:
                settings_obj.aws_bucket_name = resolved_bucket_name

            if aws_access_key:
                settings_obj.aws_access_key_id = aws_access_key
            if aws_secret_key:
                settings_obj.aws_secret_access_key = aws_secret_key

            settings_obj.save()
            self._active_media_provider = settings_obj.provider_type

            if settings_obj.provider_type == "s3":
                if aws_access_key and aws_secret_key:
                    self.stdout.write("  MediaStorageSettings: provider=s3 (AWS keys loaded from env)")
                else:
                    self.stdout.write(
                        self.style.WARNING("  MediaStorageSettings: provider=s3 (AWS keys missing in env)")
                    )
            else:
                self.stdout.write("  MediaStorageSettings: provider=local (default)")

    def _seed_social_apps(self):
        """Seed SocialApp for Google OAuth with credentials from environment variables."""
        from django.contrib.sites.models import Site

        google_client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
        google_secret_id = os.environ.get("GOOGLE_SECRET_ID", "")

        if google_client_id and google_secret_id:
            site = Site.objects.get(pk=1)
            social_app, created = SocialApp.objects.update_or_create(
                provider="google",
                defaults={
                    "name": "Google",
                    "client_id": google_client_id,
                    "secret": google_secret_id,
                },
            )
            # Ensure the app is linked to the site
            if site not in social_app.sites.all():
                social_app.sites.add(site)
            # Ensure SocialAppSettings exists and is active
            SocialAppSettings.objects.get_or_create(social_app=social_app, defaults={"is_active": True})
            action = "created" if created else "updated"
            self.stdout.write(f"  SocialApp (Google): {action} with credentials from env")
        else:
            self.stdout.write(self.style.WARNING("  SocialApp (Google): skipped (credentials not found in env)"))

    def _create_superuser(self):
        """Create the default superuser."""
        email = "admin@example.com"
        password = "admin"

        user, created = CustomUser.objects.get_or_create(
            email=email,
            defaults={
                "username": email,
                "first_name": "Admin",
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )

        if created:
            user.set_password(password)
            user.save()
            EmailAddress.objects.get_or_create(user=user, email=email, defaults={"verified": True, "primary": True})
            self.stdout.write(self.style.SUCCESS(f"  Superuser created: {email} / {password}"))
        else:
            user.first_name = "Admin"
            user.is_staff = True
            user.is_superuser = True
            user.set_password(password)
            user.save()
            self.stdout.write(f"  Superuser updated: {email}")

    def _fix_sequences(self):
        """
        Fix PostgreSQL sequences after inserting records with explicit IDs.

        When using update_or_create with explicit IDs, PostgreSQL sequences
        don't get updated, causing IntegrityError on subsequent inserts.
        This resets each sequence to the max ID in its table.
        """
        from django.db import connection

        # Tables that were seeded with explicit IDs
        tables = [
            "web_footersection",
            "web_footersectionlink",
            "web_footersocialmedia",
            "web_bottombarlink",
            "web_navbar",
            "web_navbaritem",
            "web_topbar",
            "web_footer",
            "web_bottombar",
            "web_customcss",
            "web_sitesettings",
            "web_dynamicpage",
            "catalog_category",
            "catalog_categorybanner",
            "catalog_categoryrecommendedproduct",
            "catalog_product",
            "catalog_productimage",
            "catalog_attributedefinition",
            "catalog_attributeoption",
            "catalog_productattributevalue",
            "homepage_banner",
            "homepage_bannergroup",
            "homepage_bannersettings",
            "homepage_homepagesection",
            "homepage_homepagesectionproduct",
            "homepage_homepagesectionbanner",
            "homepage_homepagesectioncategorybox",
            "homepage_homepagesectioncategoryitem",
            "homepage_storefrontherosection",
            "homepage_storefrontcategorybox",
            "homepage_storefrontcategoryitem",
            "cart_deliverymethod",
            "cart_paymentmethod"
        ]

        fixed_count = 0
        with connection.cursor() as cursor:
            for table in tables:
                try:
                    # Get max ID from table
                    cursor.execute(f"SELECT MAX(id) FROM {table}")
                    max_id = cursor.fetchone()[0]
                    if max_id is None:
                        continue

                    # Reset sequence to max_id
                    seq_name = f"{table}_id_seq"
                    cursor.execute(f"SELECT setval('{seq_name}', %s)", [max_id])
                    fixed_count += 1
                except Exception:
                    # Table might not exist or have a different sequence name
                    pass

        self.stdout.write(f"  Sequences fixed: {fixed_count} tables")

    def _history_exists(self):
        """Return True if any simple-history model already contains records."""
        from django.apps import apps as django_apps

        for model in django_apps.get_models():
            history_manager = getattr(model, "history", None)
            historical_model = getattr(history_manager, "model", None)
            if historical_model is None:
                continue

            try:
                if historical_model.objects.exists():
                    return True
            except Exception:
                continue

        return False

    def _populate_history(self):
        """Populate historical records for seeded data."""
        try:
            call_command("populate_history", auto=True, stdout=self.stdout, stderr=self.stderr)
            self.stdout.write("  History: initial records created")
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"  History: skipped ({exc})"))

    def _seed_delivery_methods(self):
        """Seed DeliveryMethod model."""
        if not DELIVERY_METHODS_DATA:
            self.stdout.write("  DeliveryMethod: 0 records (no data)")
            return

        self._bulk_upsert_by_id(
            DeliveryMethod,
            [
                {
                    "id": item["id"],
                    "name": item["name"],
                    "price": Decimal(item["price"]),
                    "delivery_time": int(item["delivery_time"]),
                    "free_from": Decimal(item["free_from"]) if item.get("free_from") else None,
                    "is_active": item.get("is_active", True),
                }
                for item in DELIVERY_METHODS_DATA
            ],
            update_fields=[
                "name",
                "price",
                "delivery_time",
                "free_from",
                "is_active",
            ],
        )

        self.stdout.write(f"  DeliveryMethod: {len(DELIVERY_METHODS_DATA)} records")

    def _seed_payment_methods(self):
        """Seed PaymentMethod model."""
        if not PAYMENT_METHODS_DATA:
            self.stdout.write("  PaymentMethod: 0 records (no data)")
            return

        self._bulk_upsert_by_id(
            PaymentMethod,
            [
                {
                    "id": item["id"],
                    "name": item["name"],
                    "default_payment_time": int(item["default_payment_time"]) if item.get("default_payment_time") else None,
                    "additional_fees": Decimal(item["additional_fees"]) if item.get("additional_fees") is not None else None,
                    "is_active": item.get("is_active", True),
                }
                for item in PAYMENT_METHODS_DATA
            ],
            update_fields=[
                "name",
                "default_payment_time",
                "additional_fees",
                "is_active",
            ],
        )

        self.stdout.write(f"  PaymentMethod: {len(PAYMENT_METHODS_DATA)} records")
