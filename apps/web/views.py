from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Count, Max, Min, Prefetch, Q
from django.db.models.functions import Coalesce
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from health_check.views import MainView

from apps.catalog.models import (
    AttributeDefinition,
    AttributeOption,
    Category,
    Product,
    ProductAttributeValue,
    ProductImage,
    ProductStatus,
)
from apps.homepage.models import (
    Banner,
    HomepageSection,
    HomepageSectionBanner,
    HomepageSectionCategoryBox,
    HomepageSectionCategoryItem,
    HomepageSectionProduct,
    HomepageSectionType,
)
from apps.support.draft_utils import apply_draft_to_instance, get_draft_session_by_token


def product_list(request, category_id=None, category_slug=None):
    """Product list page."""
    products = (
        Product.objects.filter(status=ProductStatus.ACTIVE, stock__gt=0)
        .prefetch_related("images")
        .order_by("name")
    )

    category = None
    if category_id:
        try:
            category = Category.objects.get(id=category_id)
            products = products.filter(category=category)
        except Category.DoesNotExist:
            raise Http404("Category not found")

    return render(
        request,
        "web/product_list.html",
        {
            "products": products,
            "category": category,
        },
    )


def _get_new_draft_instances(request, model_class, model_name: str):
    if not getattr(request, "draft_preview_enabled", False):
        return []

    drafts = getattr(request, "draft_changes", []) or []
    instances = []
    for draft in drafts:
        content_type = getattr(draft, "content_type", None)
        if not content_type:
            continue
        if content_type.app_label != model_class._meta.app_label or content_type.model != model_name:
            continue
        if draft.object_id:
            continue

        payload = draft.payload if isinstance(draft.payload, dict) else {}
        form_data = payload.get("form_data", {}) if isinstance(payload, dict) else {}
        temp_files = payload.get("temp_files", {}) if isinstance(payload, dict) else {}
        instance = model_class()
        apply_draft_to_instance(instance, form_data, temp_files)
        instances.append(instance)

    return instances


def home(request):
    banners = list(Banner.get_active_banners())
    draft_banners = _get_new_draft_instances(request, Banner, "banner")
    if draft_banners:
        draft_banners = [
            banner for banner in draft_banners if banner.is_active and banner.is_available() and banner.image
        ]
        if draft_banners:
            banners = banners + draft_banners
            banners.sort(key=lambda x: (x.order, -(x.created_at.timestamp() if x.created_at else 0)))

    product_sections = (
        HomepageSection.get_active_sections()
        .filter(section_type=HomepageSectionType.PRODUCT_LIST)
        .annotate(
            product_count=Count(
                "section_products",
                filter=Q(
                    section_products__product__status=ProductStatus.ACTIVE,
                    section_products__product__stock__gt=0,
                ),
            )
        )
        .filter(product_count__gt=0)
        .prefetch_related(
            Prefetch(
                "section_products",
                queryset=(
                    HomepageSectionProduct.objects.select_related("product")
                    .prefetch_related("product__images")
                    .filter(product__status=ProductStatus.ACTIVE, product__stock__gt=0)
                    .order_by("order", "id")
                ),
            )
        )
    )

    banner_sections = (
        HomepageSection.get_active_sections()
        .filter(section_type=HomepageSectionType.BANNER_SECTION)
        .annotate(banner_count=Count("section_banners"))
        .filter(banner_count__gt=0)
        .prefetch_related(
            Prefetch(
                "section_banners",
                queryset=HomepageSectionBanner.objects.order_by("order", "id"),
            )
        )
    )

    custom_sections = (
        HomepageSection.get_active_sections()
        .filter(section_type=HomepageSectionType.CUSTOM_SECTION)
        .exclude(custom_html__isnull=True)
        .exclude(custom_html__exact="")
    )

    storefront_hero_sections = (
        HomepageSection.get_active_sections()
        .filter(section_type=HomepageSectionType.STOREFRONT_HERO)
        .prefetch_related(
            Prefetch(
                "category_boxes",
                queryset=HomepageSectionCategoryBox.objects.order_by("order", "id").prefetch_related(
                    Prefetch("items", queryset=HomepageSectionCategoryItem.objects.order_by("order", "id"))
                ),
            )
        )
    )

    product_slider_sections = (
        HomepageSection.get_active_sections()
        .filter(section_type=HomepageSectionType.PRODUCT_SLIDER)
        .annotate(
            product_count=Count(
                "section_products",
                filter=Q(
                    section_products__product__status=ProductStatus.ACTIVE,
                    section_products__product__stock__gt=0,
                ),
            )
        )
        .filter(product_count__gt=0)
        .prefetch_related(
            Prefetch(
                "section_products",
                queryset=(
                    HomepageSectionProduct.objects.select_related("product")
                    .prefetch_related("product__images")
                    .filter(product__status=ProductStatus.ACTIVE, product__stock__gt=0)
                    .order_by("order", "id")
                ),
            )
        )
    )

    draft_sections = _get_new_draft_instances(request, HomepageSection, "homepagesection")
    if draft_sections:
        draft_custom_sections = []
        for section in draft_sections:
            if section.section_type != HomepageSectionType.CUSTOM_SECTION:
                continue
            if not (section.custom_html or "").strip():
                continue
            if not section.is_enabled:
                continue
            if not section.is_available():
                continue
            draft_custom_sections.append(section)

        if draft_custom_sections:
            custom_sections = list(custom_sections) + draft_custom_sections

    all_sections = list(product_sections) + list(banner_sections) + list(custom_sections) + list(storefront_hero_sections) + list(product_slider_sections)
    all_sections.sort(key=lambda x: (x.order, -x.created_at.timestamp() if x.created_at else 0))

    # Prepare filtered banners for banner sections (only those with images)
    for section in all_sections:
        if section.section_type == HomepageSectionType.BANNER_SECTION:
            valid_banners = [b for b in section.section_banners.all() if b.image]
            section._filtered_banners = valid_banners

    return render(
        request,
        "web/index.html",
        {
            "banners": banners,
            "homepage_sections": all_sections,
        },
    )


def simulate_error(request):
    raise Exception("This is a simulated error.")


def preview_draft(request, token: str):
    draft_session = get_draft_session_by_token(token)
    if not draft_session:
        raise Http404

    next_url = request.GET.get("next") or "/"
    # Add preview_token to URL for draft preview to work
    separator = "&" if "?" in next_url else "?"
    return redirect(f"{next_url}{separator}preview_token={draft_session.share_token}")


class HealthCheck(MainView):
    def get(self, request, *args, **kwargs):
        tokens = settings.HEALTH_CHECK_TOKENS
        if tokens and request.GET.get("token") not in tokens:
            raise Http404
        return super().get(request, *args, **kwargs)


def product_search(request):
    """
    Live search endpoint for products.
    Returns JSON with matching products for search autocomplete.
    """
    query = request.GET.get("q", "").strip()

    if len(query) < 2:
        return JsonResponse({"products": [], "categories": [], "total_count": 0})

    # Search products by name
    products = (
        Product.objects.filter(status=ProductStatus.ACTIVE, stock__gt=0)
        .filter(Q(name__icontains=query))
        .select_related("category")
        .prefetch_related("images")
        .order_by("name")[:10]
    )

    # Search categories by name
    categories = Category.objects.filter(name__icontains=query).order_by("name")[:5]

    # Get total count for "See all results" link
    total_count = (
        Product.objects.filter(status=ProductStatus.ACTIVE, stock__gt=0)
        .filter(Q(name__icontains=query))
        .count()
    )

    products_data = []
    for product in products:
        image_url = None
        first_image = product.images.first()
        if first_image and first_image.image:
            image_url = first_image.image.url

        products_data.append(
            {
                "id": product.id,
                "name": product.name,
                "slug": product.slug,
                "price": str(product.price),
                "image_url": image_url,
                "category_name": product.category.name if product.category else None,
            }
        )

    categories_data = [
        {"id": cat.id, "name": cat.name, "slug": cat.slug, "url": cat.get_absolute_url()}
        for cat in categories
    ]

    return JsonResponse(
        {
            "products": products_data,
            "categories": categories_data,
            "total_count": total_count,
            "query": query,
        }
    )


# Sort options: (key, ordering_field_or_list, display_label)
SORT_OPTIONS = [
    ("relevance", ["-sales_total", "-created_at"], _("Most relevant")),
    ("rating", ["-sales_total"], _("Customer rating: Best")),
    ("newest", ["-created_at"], _("Newest")),
    ("price_asc", ["price"], _("Price: Low to High")),
    ("price_desc", ["-price"], _("Price: High to Low")),
    ("name_asc", ["name"], _("Name: A-Z")),
    ("name_desc", ["-name"], _("Name: Z-A")),
]

PRODUCTS_PER_PAGE = 36


def _get_descendant_category_ids(category):
    """Recursively get all descendant category IDs including the category itself."""
    ids = [category.id]
    for child in category.children.all():
        ids.extend(_get_descendant_category_ids(child))
    return ids


def _get_category_product_count(category):
    """Get total product count for a category including all descendants."""
    category_ids = _get_descendant_category_ids(category)
    return Product.objects.filter(
        status=ProductStatus.ACTIVE,
        stock__gt=0,
        category_id__in=category_ids
    ).count()


def _build_category_filter_tree(current_category=None):
    """Build a list of categories to show in the filter sidebar."""
    if current_category:
        # If we're in a category, show its children (subcategories)
        if current_category.children.exists():
            return list(current_category.children.all())
        # If no children, show siblings (same parent)
        elif current_category.parent:
            return list(current_category.parent.children.all())
        # If root category with no children, show all root categories
        else:
            return list(Category.objects.filter(parent__isnull=True))
    else:
        # Not in a category - show root categories
        return list(Category.objects.filter(parent__isnull=True))


def _build_breadcrumb(category):
    """Build breadcrumb path from root to current category."""
    breadcrumb = []
    current = category
    while current:
        breadcrumb.insert(0, {
            "category": current,
            "siblings": list(Category.objects.filter(parent=current.parent).only("id", "name", "slug"))
        })
        current = current.parent
    return breadcrumb


def product_list(request, category_id=None, category_slug=None):
    """
    Display product listing page with filtering, sorting, and pagination.
    """
    # Get current category from URL - use ID for faster lookup
    current_category = None
    if category_id:
        current_category = Category.objects.select_related('parent').filter(id=category_id).first()
        if not current_category:
            raise Http404("Category not found")

    # Start with active products
    products = Product.objects.filter(status=ProductStatus.ACTIVE, stock__gt=0)

    # Category filtering
    if current_category:
        # Include products from this category and all its descendants
        category_ids = _get_descendant_category_ids(current_category)
        products = products.filter(category_id__in=category_ids)
    else:
        # Check for category query parameters (multiple selection)
        category_params = request.GET.getlist("category")
        if category_params:
            try:
                selected_cat_ids = [int(c) for c in category_params if c.isdigit()]
                if selected_cat_ids:
                    # For each selected category, include its descendants too
                    all_category_ids = []
                    for cat_id in selected_cat_ids:
                        cat = Category.objects.filter(id=cat_id).first()
                        if cat:
                            all_category_ids.extend(_get_descendant_category_ids(cat))
                    if all_category_ids:
                        products = products.filter(category_id__in=all_category_ids)
            except (ValueError, TypeError):
                pass

    # Search filter
    search_query = request.GET.get("q", "").strip()
    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) | Q(description__icontains=search_query)
        )

    # Price filtering
    current_price_min = request.GET.get("price_min", "").strip()
    current_price_max = request.GET.get("price_max", "").strip()
    try:
        if current_price_min:
            products = products.filter(price__gte=Decimal(current_price_min))
    except (InvalidOperation, ValueError):
        current_price_min = ""
    try:
        if current_price_max:
            products = products.filter(price__lte=Decimal(current_price_max))
    except (InvalidOperation, ValueError):
        current_price_max = ""

    # Attribute filtering - parse slug-based params (e.g., attr_1=4-hp)
    selected_attributes = set()
    selected_attributes_slugs = set()
    for key in request.GET.keys():
        if key.startswith("attr_"):
            try:
                attr_id = int(key[5:])
                option_slugs = request.GET.getlist(key)
                valid_option_ids = []
                for slug_val in option_slugs:
                    option_id = AttributeOption.parse_slug(slug_val)
                    if option_id:
                        valid_option_ids.append(option_id)
                        selected_attributes_slugs.add(slug_val)
                if valid_option_ids:
                    selected_attributes.update(valid_option_ids)
                    # Filter products that have any of these attribute options
                    products = products.filter(
                        attribute_values__option_id__in=valid_option_ids
                    )
            except (ValueError, TypeError):
                pass

    # Sorting
    current_sort = request.GET.get("sort", "newest")
    sort_field = ["-created_at"]  # default
    for key, field, label in SORT_OPTIONS:
        if key == current_sort:
            sort_field = field
            break
    products = products.order_by(*sort_field)

    # Prefetch images for display
    products = products.select_related("category").prefetch_related(
        Prefetch("images", queryset=ProductImage.objects.order_by("sort_order"))
    )

    # Get total count before pagination
    total_count = products.count()

    # Pagination
    paginator = Paginator(products, PRODUCTS_PER_PAGE)
    page_number = request.GET.get("page", 1)
    try:
        products_page = paginator.page(page_number)
    except PageNotAnInteger:
        products_page = paginator.page(1)
    except EmptyPage:
        products_page = paginator.page(paginator.num_pages)

    # Get price range for all active products (for filter hints)
    price_range = Product.objects.filter(status=ProductStatus.ACTIVE, stock__gt=0).aggregate(
        min_price=Coalesce(Min("price"), Decimal("0")),
        max_price=Coalesce(Max("price"), Decimal("0")),
    )

    # Get available attributes for filtering - show all options that have products in base category,
    # not just in filtered results (so options don't disappear when filtering)
    # First, get the base product set (before attribute filtering) for the category
    base_products = Product.objects.filter(status=ProductStatus.ACTIVE, stock__gt=0)
    if current_category:
        category_ids = _get_descendant_category_ids(current_category)
        base_products = base_products.filter(category_id__in=category_ids)
    
    base_product_ids = list(base_products.values_list("id", flat=True)[:1000])
    
    # Get all attribute options that have products in the base category
    base_option_ids = (
        ProductAttributeValue.objects.filter(product_id__in=base_product_ids)
        .values("option_id")
        .annotate(product_count=Count("product_id", distinct=True))
        .filter(product_count__gt=0)
    )
    base_option_id_to_count = {item["option_id"]: item["product_count"] for item in base_option_ids}
    base_option_ids_set = set(base_option_id_to_count.keys())
    
    # Also get counts for currently filtered products (to show how many products match current filters)
    product_ids_for_attributes = list(products.values_list("id", flat=True)[:1000])
    filtered_option_counts = (
        ProductAttributeValue.objects.filter(product_id__in=product_ids_for_attributes)
        .values("option_id")
        .annotate(product_count=Count("product_id", distinct=True))
        .filter(product_count__gt=0)
    )
    filtered_option_id_to_count = {item["option_id"]: item["product_count"] for item in filtered_option_counts}
    
    # Get attribute definitions that have relevant options
    available_attributes = []
    if base_option_ids_set:
        # Get all attribute definitions that have at least one option with products in base category
        attr_definitions = AttributeDefinition.objects.filter(
            options__id__in=base_option_ids_set
        ).distinct().prefetch_related(
            Prefetch(
                "options",
                queryset=AttributeOption.objects.filter(id__in=base_option_ids_set).order_by("value")
            )
        ).order_by("display_name")
        
        for attr in attr_definitions:
            # Get all options for this attribute that exist in base category
            options_with_products = list(attr.options.all())
            if options_with_products:
                # Add product count from filtered results (0 if not in filtered set)
                for opt in options_with_products:
                    opt.product_count = filtered_option_id_to_count.get(opt.id, 0)
                attr.filtered_options = options_with_products
                available_attributes.append(attr)

    # Build filter categories
    filter_categories = _build_category_filter_tree(current_category)

    # Get selected category IDs from query params
    selected_category_ids = [
        str(c) for c in request.GET.getlist("category") if c.isdigit()
    ]

    # Build query string without page parameter (for pagination links)
    query_params = request.GET.copy()
    query_params.pop("page", None)
    query_string = query_params.urlencode()

    # Build query string without view parameter (for view toggle links)
    query_params_without_view = request.GET.copy()
    query_params_without_view.pop("page", None)
    query_params_without_view.pop("view", None)
    query_string_without_view = query_params_without_view.urlencode()

    # Get view mode (list or grid) - default to list on desktop, grid on mobile handled via JS
    view_mode = request.GET.get("view", "list")
    if view_mode not in ("list", "grid"):
        view_mode = "list"

    # Calculate pagination info for display (e.g., "1-36 z 144")
    start_index = (products_page.number - 1) * PRODUCTS_PER_PAGE + 1
    end_index = min(products_page.number * PRODUCTS_PER_PAGE, total_count)

    # Build breadcrumb
    breadcrumb = _build_breadcrumb(current_category) if current_category else []

    # Build subcategories navigation for sidebar
    subcategories_nav = []
    if current_category and current_category.children.exists():
        for child in current_category.children.all():
            child.total_product_count = _get_category_product_count(child)
            if child.total_product_count > 0:
                subcategories_nav.append(child)
    
    # Get current category product count
    current_category_product_count = None
    parent_category_product_count = None
    if current_category:
        current_category_product_count = _get_category_product_count(current_category)
        if current_category.parent:
            parent_category_product_count = _get_category_product_count(current_category.parent)

    # Determine page title
    if search_query:
        page_title = _('Search results: "%(query)s"') % {"query": search_query}
    elif current_category:
        page_title = current_category.name
    else:
        page_title = _("All products")

    context = {
        "products": products_page,
        "page_title": page_title,
        "total_count": total_count,
        "start_index": start_index,
        "end_index": end_index,
        "view_mode": view_mode,
        "breadcrumb": breadcrumb,
        "current_category": current_category,
        "filter_categories": filter_categories,
        "selected_category_ids": selected_category_ids,
        "sort_options": SORT_OPTIONS,
        "current_sort": current_sort,
        "query_string": query_string,
        "query_string_without_view": query_string_without_view,
        "search_query": search_query,
        "price_range": price_range,
        "current_price_min": current_price_min,
        "current_price_max": current_price_max,
        "available_attributes": available_attributes,
        "selected_attributes": selected_attributes,
        "selected_attributes_slugs": selected_attributes_slugs,
        "subcategories_nav": subcategories_nav,
        "current_category_product_count": current_category_product_count,
        "parent_category_product_count": parent_category_product_count,
    }

    # Return partial template for HTMX requests
    if request.headers.get("HX-Request"):
        return render(request, "web/product_list_partial.html", context)

    return render(request, "web/product_list.html", context)
