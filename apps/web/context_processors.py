from django.conf import settings

from apps.catalog.models import Category, Product, ProductStatus
from apps.web.models import BottomBar, CustomCSS, Footer, Navbar, SiteSettings, TopBar

from .meta import absolute_url, get_server_root


def _safe_call(callback, default=None):
    try:
        return callback()
    except Exception:
        return default


def _category_has_products(category, category_ids_with_products):
    """
    Recursively check if a category or any of its descendants has active products.
    Uses a pre-computed set of category IDs with products for efficiency.
    """
    if category.id in category_ids_with_products:
        return True
    # Check children recursively (use prefetched children if available)
    for child in category.children.all():
        if _category_has_products(child, category_ids_with_products):
            return True
    return False


def _filter_categories_with_products(categories):
    """
    Filter a list of categories to only include those with products
    (either directly or in their subcategories).
    """
    if not categories:
        return []

    # Get all category IDs that have at least one active product
    category_ids_with_products = set(
        Product.objects.filter(status=ProductStatus.ACTIVE, stock__gt=0)
        .values_list("category_id", flat=True)
        .distinct()
    )

    # Filter categories that have products (directly or in children)
    return [cat for cat in categories if _category_has_products(cat, category_ids_with_products)]


def project_meta(request):
    # Build project metadata from SiteSettings
    project_data = {
        "NAME": settings.PROJECT_METADATA.get("NAME", ""),
        "URL": settings.PROJECT_METADATA.get("URL", ""),
        "DESCRIPTION": settings.PROJECT_METADATA.get("DESCRIPTION", ""),
        "IMAGE": settings.PROJECT_METADATA.get("IMAGE", None),
        "KEYWORDS": settings.PROJECT_METADATA.get("KEYWORDS", ""),
    }

    site_currency = "PLN"  # default
    site_settings_obj = _safe_call(SiteSettings.get_settings)
    if site_settings_obj:
        if site_settings_obj.store_name:
            project_data["NAME"] = site_settings_obj.store_name
        if site_settings_obj.site_url:
            project_data["URL"] = site_settings_obj.site_url
        if site_settings_obj.description:
            project_data["DESCRIPTION"] = site_settings_obj.description
        if site_settings_obj.keywords:
            project_data["KEYWORDS"] = site_settings_obj.keywords
        site_currency = site_settings_obj.currency or "PLN"
        if site_settings_obj.default_image:
            project_data["IMAGE"] = site_settings_obj.default_image.url

    # Build title from name and description
    name = str(project_data["NAME"])
    description = str(project_data["DESCRIPTION"])
    if name and description:
        project_data["TITLE"] = f"{name} | {description}"
    else:
        project_data["TITLE"] = name or description

    theme_cookie = request.COOKIES.get("theme", "")

    return {
        "project_meta": project_data,
        "site_currency": site_currency,
        "server_url": get_server_root(),
        "page_url": absolute_url(request.path),
        "page_title": "",
        "page_description": "",
        "page_image": "",
        "light_theme": settings.LIGHT_THEME,
        "dark_theme": settings.DARK_THEME,
        "current_theme": theme_cookie,
        "dark_mode": theme_cookie == settings.DARK_THEME,
        "turnstile_key": getattr(settings, "TURNSTILE_KEY", None),
        "use_i18n": getattr(settings, "USE_I18N", False) and len(getattr(settings, "LANGUAGES", [])) > 1,
    }


def google_analytics_id(request):
    """
    Adds google analytics id to all requests
    """
    if settings.GOOGLE_ANALYTICS_ID:
        return {
            "GOOGLE_ANALYTICS_ID": settings.GOOGLE_ANALYTICS_ID,
        }
    else:
        return {}


def top_bar_section(request):
    """
    Adds the active top bar to all requests.

    When draft preview is enabled, we return the TopBar singleton
    so that draft changes to is_active or availability dates can be previewed.
    The template checks top_bar.is_active to decide what to render.
    """
    draft_preview_enabled = getattr(request, "draft_preview_enabled", False)

    if draft_preview_enabled:
        # In draft preview, always return the singleton so draft changes can be applied
        top_bar = _safe_call(lambda: TopBar.objects.first())
    else:
        top_bar = _safe_call(TopBar.get_active)

    return {
        "top_bar": top_bar,
    }


def site_settings(request):
    """
    Adds site settings to all requests for global site configuration.
    """
    settings_obj = _safe_call(CustomCSS.get_settings)

    return {
        "site_settings": settings_obj,
    }


def footer_context(request):
    """
    Adds footer configuration to all requests.
    Returns footer with sections (including links) and social media.

    When draft preview is enabled, we always fetch sections/social media
    so that draft changes to is_active or content_type can be previewed.
    The template checks footer.is_active to decide what to render.
    """
    footer = _safe_call(Footer.get_settings)
    footer_sections = []
    footer_social_media = []

    if footer:
        # Check if draft preview is enabled - if so, always fetch sections
        # because the draft might change is_active from False to True
        draft_preview_enabled = getattr(request, "draft_preview_enabled", False)

        should_fetch_sections = draft_preview_enabled or (
            footer.is_active and footer.content_type == Footer.ContentType.STANDARD
        )

        if should_fetch_sections:
            footer_sections = list(footer.sections.prefetch_related("links").order_by("order", "id"))
            footer_social_media = list(footer.social_media.filter(is_active=True).order_by("order", "id"))

    return {
        "footer": footer,
        "footer_sections": footer_sections,
        "footer_social_media": footer_social_media,
    }


def bottom_bar_context(request):
    """
    Adds bottom bar configuration to all requests.
    Returns bottom bar with links.

    When draft preview is enabled, we always fetch links
    so that draft changes to is_active can be previewed.
    The template checks bottom_bar.is_active to decide what to render.
    """
    bottom_bar = _safe_call(BottomBar.get_settings)
    bottom_bar_links = []

    if bottom_bar:
        # Check if draft preview is enabled - if so, always fetch links
        # because the draft might change is_active from False to True
        draft_preview_enabled = getattr(request, "draft_preview_enabled", False)

        should_fetch_links = draft_preview_enabled or bottom_bar.is_active

        if should_fetch_links:
            bottom_bar_links = list(bottom_bar.links.order_by("order", "id"))

    return {
        "bottom_bar": bottom_bar,
        "bottom_bar_links": bottom_bar_links,
    }


def navigation_categories(request):
    """
    Adds navigation categories to all requests.
    Returns parent categories with their children for mega menu navigation.
    Also handles custom navbar configuration if enabled.
    """
    # Get navbar configuration
    navbar = _safe_call(Navbar.get_settings)

    # Apply draft if enabled
    draft_preview_enabled = getattr(request, "draft_preview_enabled", False)
    if draft_preview_enabled and navbar:
        from apps.support.draft_utils import apply_drafts_to_context

        draft_changes_map = getattr(request, "draft_changes_map", {})
        if draft_changes_map:
            apply_drafts_to_context(navbar, draft_changes_map)

    navbar_mode = navbar.mode if navbar else Navbar.NavbarMode.STANDARD

    # Always get parent categories for "All categories" drawer and fallback
    # Filter out categories that have no products (directly or in children)
    parent_categories = _safe_call(
        lambda: _filter_categories_with_products(
            list(
                Category.objects.filter(parent__isnull=True)
                .prefetch_related(
                    "children",
                    "children__children",
                    "children__children__children",
                    "children__children__children__children",
                )
                .order_by("name")
            )
        ),
        default=[],
    )

    # Custom navbar items (only if custom mode is active)
    custom_navbar_items = []
    if navbar_mode == Navbar.NavbarMode.CUSTOM and navbar:

        def _get_items():
            items = list(
                navbar.items.filter(is_active=True)
                .select_related("category")
                .prefetch_related(
                    "category__children",
                    "category__children__children",
                    "category__children__children__children",
                )
                .order_by("order", "id")
            )
            # If draft enabled, apply drafts to the list of items
            if draft_preview_enabled and items:
                from apps.support.draft_utils import apply_drafts_to_context

                draft_changes_map = getattr(request, "draft_changes_map", {})
                if draft_changes_map:
                    # This handles inline items effectively if logical parent linkage exists,
                    # but here we might need direct application if items themselves are modified
                    apply_drafts_to_context(items, draft_changes_map)
            return items

        custom_navbar_items = _safe_call(_get_items, default=[])

    return {
        "nav_categories": parent_categories,
        "navbar": navbar,
        "navbar_mode": navbar_mode,
        "custom_navbar_items": custom_navbar_items,
    }
