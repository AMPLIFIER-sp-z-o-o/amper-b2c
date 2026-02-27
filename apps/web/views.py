from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import IntegrityError, connection
from django.db.models import Count, Max, Min, Prefetch, Q
from django.db.models.functions import Coalesce
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from health_check.views import MainView

from apps.catalog.models import (
    VISIBLE_STATUSES,
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
    HomepageSection,
    HomepageSectionBanner,
    HomepageSectionCategoryBox,
    HomepageSectionCategoryItem,
    HomepageSectionProduct,
    HomepageSectionType,
)
from apps.support.draft_utils import (
    apply_draft_to_existing_instance,
    apply_draft_to_instance,
    get_draft_session_by_token,
)
from apps.web.models import DynamicPage, SiteSettings


def server_error(request, *args, **kwargs):
    return render(request, "500.html", status=500)


def product_list(request, category_id=None, category_slug=None):
    """Product list page."""
    products = Product.objects.filter(status__in=VISIBLE_STATUSES).prefetch_related("images").order_by("name")

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


def _get_site_currency_for_labels() -> str:
    try:
        settings_obj = SiteSettings.get_settings()
        if settings_obj and settings_obj.currency:
            return settings_obj.currency
    except Exception:
        pass
    return SiteSettings.Currency.USD


def dynamic_page_detail(request, slug: str, pk: int):
    page = get_object_or_404(DynamicPage, pk=pk)
    apply_draft_to_existing_instance(request, page)

    if slug != page.slug:
        return redirect(page.get_absolute_url(), permanent=True)

    if not page.is_active and not getattr(request, "draft_preview_enabled", False):
        raise Http404("Page not found")

    return render(
        request,
        "web/dynamicpage_detail.html",
        {
            "page": page,
            "page_title": page.meta_title or page.name,
            "page_description": page.meta_description,
            "page_canonical_url": page.get_absolute_url(),
        },
    )


def terms_page(request):
    """Serve the Terms and Conditions page from a DynamicPage with slug='terms'."""
    try:
        page, _created = DynamicPage.objects.get_or_create(
            slug="terms",
            defaults={
                "name": "Terms and Conditions",
                "meta_title": "Terms and Conditions",
                "content": "<p>Your terms and conditions go here.</p>",
                "is_active": True,
            },
        )
    except IntegrityError:
        # Sequence out of sync after seed data – reset it and fetch existing row
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT setval(pg_get_serial_sequence('web_dynamicpage', 'id'), "
                "COALESCE((SELECT MAX(id) FROM web_dynamicpage), 0) + 1, false)"
            )
        page = DynamicPage.objects.filter(slug="terms").first()
        if page is None:
            page = DynamicPage.objects.create(
                slug="terms",
                name="Terms and Conditions",
                meta_title="Terms and Conditions",
                content="<p>Your terms and conditions go here.</p>",
                is_active=True,
            )
    apply_draft_to_existing_instance(request, page)
    return render(
        request,
        "web/dynamicpage_detail.html",
        {
            "page": page,
            "page_title": page.meta_title or page.name,
            "page_description": page.meta_description,
        },
    )


def privacy_page(request):
    """Serve the Privacy Policy page from a DynamicPage with slug='privacy-policy'."""
    try:
        page, _created = DynamicPage.objects.get_or_create(
            slug="privacy-policy",
            defaults={
                "name": "Privacy Policy",
                "meta_title": "Privacy Policy",
                "content": "<p>Your privacy policy goes here.</p>",
                "is_active": True,
            },
        )
    except IntegrityError:
        # Sequence out of sync after seed data – reset it and fetch existing row
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT setval(pg_get_serial_sequence('web_dynamicpage', 'id'), "
                "COALESCE((SELECT MAX(id) FROM web_dynamicpage), 0) + 1, false)"
            )
        page = DynamicPage.objects.filter(slug="privacy-policy").first()
        if page is None:
            page = DynamicPage.objects.create(
                slug="privacy-policy",
                name="Privacy Policy",
                meta_title="Privacy Policy",
                content="<p>Your privacy policy goes here.</p>",
                is_active=True,
            )
    apply_draft_to_existing_instance(request, page)
    return render(
        request,
        "web/dynamicpage_detail.html",
        {
            "page": page,
            "page_title": page.meta_title or page.name,
            "page_description": page.meta_description,
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
                    section_products__product__status__in=VISIBLE_STATUSES,
                ),
            )
        )
        .filter(product_count__gt=0)
        .prefetch_related(
            Prefetch(
                "section_products",
                queryset=(
                    HomepageSectionProduct.objects.select_related("product__category")
                    .prefetch_related(
                        "product__images",
                        Prefetch(
                            "product__attribute_values",
                            queryset=ProductAttributeValue.objects.select_related("option__attribute")
                            .filter(option__attribute__show_on_tile=True)
                            .order_by("option__attribute__tile_display_order", "option__attribute__name"),
                            to_attr="tile_attributes_prefetch",
                        ),
                    )
                    .filter(product__status__in=VISIBLE_STATUSES)
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
                    section_products__product__status__in=VISIBLE_STATUSES,
                ),
            )
        )
        .filter(product_count__gt=0)
        .prefetch_related(
            Prefetch(
                "section_products",
                queryset=(
                    HomepageSectionProduct.objects.select_related("product__category")
                    .prefetch_related(
                        "product__images",
                        Prefetch(
                            "product__attribute_values",
                            queryset=ProductAttributeValue.objects.select_related("option__attribute")
                            .filter(option__attribute__show_on_tile=True)
                            .order_by("option__attribute__tile_display_order", "option__attribute__name"),
                            to_attr="tile_attributes_prefetch",
                        ),
                    )
                    .filter(product__status__in=VISIBLE_STATUSES)
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

    all_sections = (
        list(product_sections)
        + list(banner_sections)
        + list(custom_sections)
        + list(storefront_hero_sections)
        + list(product_slider_sections)
    )
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


def search_suggestions(request):
    """
    Live search endpoint for products.
    Returns JSON with matching products for search autocomplete dropdown.
    Shows text-only suggestions (no images).
    Supports optional category filtering.
    """
    query = request.GET.get("q", "").strip()
    category_id = request.GET.get("category_id", "").strip()

    if len(query) < 2:
        return JsonResponse({"suggestions": [], "total_count": 0, "query": ""})

    # Start with active products
    products = Product.objects.filter(status__in=VISIBLE_STATUSES)

    # Apply category filter if specified
    descendant_ids = None
    if category_id:
        try:
            category = Category.objects.get(id=int(category_id))
            descendant_ids = _get_descendant_category_ids(category)
            products = products.filter(category_id__in=descendant_ids)
        except (ValueError, Category.DoesNotExist):
            pass

    # Search products by name
    products = products.filter(Q(name__icontains=query)).select_related("category").order_by("name")[:8]

    # Get total count for "See all results" link
    total_products = Product.objects.filter(status__in=VISIBLE_STATUSES)
    if descendant_ids:
        total_products = total_products.filter(category_id__in=descendant_ids)
    total_count = total_products.filter(Q(name__icontains=query)).count()

    suggestions = []
    for product in products:
        suggestions.append(
            {
                "id": product.id,
                "text": product.name,
                "category_name": product.category.name if product.category else None,
            }
        )

    return JsonResponse(
        {
            "suggestions": suggestions,
            "total_count": total_count,
            "query": query,
        }
    )


def search_results(request):
    """
    Search results page - displays products matching the search query.
    Reuses the product_list logic with search-specific behavior.
    Supports optional category filtering via category_slug parameter.
    """
    search_query = request.GET.get("q", "").strip()
    highlight_product_id = request.GET.get("product_id", "").strip()
    category_slug = request.GET.get("category", "").strip()

    if not search_query:
        return redirect("web:home")

    # Start with active products
    products = Product.objects.filter(status__in=VISIBLE_STATUSES)

    # Apply category filter if specified
    search_category = None
    if category_slug:
        try:
            search_category = Category.objects.get(slug=category_slug)
            # Get all descendant category IDs (including the category itself)
            descendant_ids = [search_category.id]

            def get_all_children(cat):
                children = list(cat.children.all())
                all_children = children[:]
                for child in children:
                    all_children.extend(get_all_children(child))
                return all_children

            descendants = get_all_children(search_category)
            descendant_ids.extend([d.id for d in descendants])
            products = products.filter(category_id__in=descendant_ids)
        except Category.DoesNotExist:
            search_category = None

    # Apply search filter
    products = products.filter(Q(name__icontains=search_query) | Q(description__icontains=search_query))

    # Store base products for attribute computation (before attribute filtering)
    base_search_products = products

    # Attribute filtering - parse slug-based params (e.g., attr_1=4-hp)
    selected_attributes = set()
    selected_attributes_by_attr = {}
    selected_attributes_slugs = set()
    applied_attribute_filter = False
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
                    selected_attributes_by_attr[attr_id] = set(valid_option_ids)
                    # Filter products that have any of these attribute options
                    products = products.filter(attribute_values__option_id__in=valid_option_ids)
                    applied_attribute_filter = True
            except (ValueError, TypeError):
                pass

    if applied_attribute_filter:
        products = products.distinct()

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

    # If a specific product ID is provided, prioritize it
    highlighted_product = None
    if highlight_product_id:
        try:
            product_id = int(highlight_product_id)
            highlighted_product = products.filter(id=product_id).first()
            if highlighted_product:
                # Exclude it from main queryset to avoid duplicates
                products = products.exclude(id=product_id)
        except (ValueError, TypeError):
            pass

    # Sorting - by relevance (stock, then recency)
    current_sort = request.GET.get("sort", "relevance")
    sort_field = ["-stock", "-created_at"]  # Default relevance
    for key, field, label in SORT_OPTIONS:
        if key == current_sort:
            sort_field = field
            break
    else:
        current_sort = "relevance"
    products = products.order_by(*sort_field)

    # Prefetch images and tile attributes for display (avoid N+1 queries)
    products = products.select_related("category").prefetch_related(
        Prefetch("images", queryset=ProductImage.objects.order_by("sort_order")),
        Prefetch(
            "attribute_values",
            queryset=ProductAttributeValue.objects.select_related("option__attribute")
            .filter(option__attribute__show_on_tile=True)
            .order_by("option__attribute__tile_display_order", "option__attribute__name"),
            to_attr="tile_attributes_prefetch",
        ),
    )

    # Get total count before pagination
    total_count = products.count()
    if highlighted_product:
        total_count += 1

    # Get per_page from request
    per_page_param = request.GET.get("per_page", "")
    try:
        per_page = int(per_page_param) if per_page_param else PRODUCTS_PER_PAGE
        if per_page not in ALLOWED_PER_PAGE:
            per_page = PRODUCTS_PER_PAGE
    except (ValueError, TypeError):
        per_page = PRODUCTS_PER_PAGE

    # Pagination
    paginator = Paginator(products, per_page)
    page_number = request.GET.get("page", 1)
    try:
        products_page = paginator.page(page_number)
    except PageNotAnInteger:
        products_page = paginator.page(1)
    except EmptyPage:
        products_page = paginator.page(paginator.num_pages)

    # If on first page and we have a highlighted product, prepend it
    if highlighted_product and products_page.number == 1:
        products_list = list(products_page.object_list)
        products_list.insert(0, highlighted_product)
        products_page.object_list = products_list

    # Get price range for all active products
    price_range = Product.objects.filter(status__in=VISIBLE_STATUSES).aggregate(
        min_price=Coalesce(Min("price"), Decimal("0")),
        max_price=Coalesce(Max("price"), Decimal("0")),
    )

    # Build query strings for pagination
    query_params = request.GET.copy()
    query_params.pop("page", None)
    query_params.pop("view", None)
    query_string = query_params.urlencode()

    query_params_without_sort = query_params.copy()
    query_params_without_sort.pop("sort", None)
    query_string_without_sort = query_params_without_sort.urlencode()

    view_mode = "list"

    # Pagination display info
    start_index = (products_page.number - 1) * per_page + 1
    end_index = min(products_page.number * per_page, total_count)

    page_title = _('Search results: "%(query)s"') % {"query": search_query}

    # Get available attributes for filtering based on search results
    # Use base_search_products (before attribute filtering) so options don't disappear
    base_product_ids = list(base_search_products.values_list("id", flat=True)[:1000])

    # Get all attribute options that have products in the search results
    base_option_ids = (
        ProductAttributeValue.objects.filter(product_id__in=base_product_ids)
        .values("option_id")
        .annotate(product_count=Count("product_id", distinct=True))
        .filter(product_count__gt=0)
    )
    base_option_id_to_count = {item["option_id"]: item["product_count"] for item in base_option_ids}
    base_option_ids_set = set(base_option_id_to_count.keys())

    # Also get counts for currently filtered products
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
        attr_definitions = (
            AttributeDefinition.objects.filter(options__id__in=base_option_ids_set)
            .distinct()
            .prefetch_related(
                Prefetch(
                    "options", queryset=AttributeOption.objects.filter(id__in=base_option_ids_set).order_by("value")
                )
            )
            .order_by("name")
        )

        for attr in attr_definitions:
            has_selected_options = bool(selected_attributes_by_attr.get(attr.id))
            options_with_products = []
            for opt in attr.options.all():
                opt.product_count = filtered_option_id_to_count.get(opt.id, 0)

                # Hide no-op options: when selecting it would not change current results.
                # Keep currently selected options visible so users can unselect them.
                if (
                    total_count > 0
                    and not has_selected_options
                    and opt.id not in selected_attributes
                    and opt.product_count == total_count
                ):
                    continue

                options_with_products.append(opt)
            if options_with_products:
                attr.filtered_options = options_with_products
                available_attributes.append(attr)

    # Build active filters list for display chips
    display_currency = _get_site_currency_for_labels()
    active_filters = []

    # Price filters
    if current_price_min:
        active_filters.append(
            {
                "type": "price_min",
                "value": current_price_min,
                "label": _("Price: from %(price)s %(currency)s")
                % {"price": current_price_min, "currency": display_currency},
            }
        )
    if current_price_max:
        active_filters.append(
            {
                "type": "price_max",
                "value": current_price_max,
                "label": _("Price: to %(price)s %(currency)s")
                % {"price": current_price_max, "currency": display_currency},
            }
        )

    # Attribute filters - create lookup for option values
    selected_option_ids = set()
    attr_slug_to_info = {}
    for key in request.GET.keys():
        if key.startswith("attr_"):
            attr_id = key[5:]
            option_slugs = request.GET.getlist(key)
            for slug_val in option_slugs:
                option_id = AttributeOption.parse_slug(slug_val)
                if option_id:
                    selected_option_ids.add(option_id)
                    if attr_id not in attr_slug_to_info:
                        attr_slug_to_info[attr_id] = []
                    attr_slug_to_info[attr_id].append((slug_val, option_id))

    # Fetch option details for selected options
    if selected_option_ids:
        options_with_attrs = AttributeOption.objects.filter(id__in=selected_option_ids).select_related("attribute")
        option_lookup = {opt.id: opt for opt in options_with_attrs}

        for attr_id, slug_option_pairs in attr_slug_to_info.items():
            for slug_val, option_id in slug_option_pairs:
                opt = option_lookup.get(option_id)
                if opt:
                    active_filters.append(
                        {
                            "type": f"attr_{attr_id}",
                            "value": slug_val,
                            "label": f"{opt.attribute.name}: {opt.value}",
                        }
                    )

    context = {
        "products": products_page,
        "page_title": page_title,
        "total_count": total_count,
        "start_index": start_index,
        "end_index": end_index,
        "view_mode": view_mode,
        "per_page": per_page,
        "breadcrumb": [],
        "current_category": None,
        "filter_categories": list(Category.objects.filter(parent__isnull=True)),
        "selected_category_ids": [],
        "sort_options": SORT_OPTIONS,
        "current_sort": current_sort,
        "query_string": query_string,
        "query_string_without_sort": query_string_without_sort,
        "search_query": search_query,
        "price_range": price_range,
        "current_price_min": current_price_min,
        "current_price_max": current_price_max,
        "available_attributes": available_attributes,
        "selected_attributes": selected_attributes,
        "selected_attributes_slugs": selected_attributes_slugs,
        "subcategories_nav": [],
        "current_category_product_count": None,
        "parent_category_product_count": None,
        "active_filters": active_filters,
        "is_search_page": True,
        "highlighted_product_id": int(highlight_product_id) if highlight_product_id.isdigit() else None,
        "search_category": search_category,
    }

    # Return partial template for in-place filter/pagination HTMX updates.
    # History-restore requests must return full HTML, otherwise back/forward can
    # restore only the fragment and lose page chrome/sidebar.
    if (
        request.headers.get("HX-Request")
        and not request.headers.get("HX-Soft-Nav")
        and not request.headers.get("HX-History-Restore-Request")
    ):
        return render(request, "web/product_list_partial.html", context)

    return render(request, "web/product_list.html", context)


# Sort options: (key, ordering_field_or_list, display_label)
SORT_OPTIONS = [
    ("relevance", ["-stock", "-created_at"], _("Most relevant")),
    ("price_asc", ["price"], _("Price: Low to High")),
    ("price_desc", ["-price"], _("Price: High to Low")),
]

PRODUCTS_PER_PAGE = 30
ALLOWED_PER_PAGE = [30, 60, 90]


def _get_descendant_category_ids(category):
    """Recursively get all descendant category IDs including the category itself."""
    ids = [category.id]
    for child in category.children.all():
        ids.extend(_get_descendant_category_ids(child))
    return ids


def _get_descendant_category_ids_from_cache(category, category_children_map):
    """
    Get all descendant category IDs using pre-loaded children map.
    Avoids N+1 queries by using the cached category hierarchy.
    """
    ids = [category.id]
    children = category_children_map.get(category.id, [])
    for child in children:
        ids.extend(_get_descendant_category_ids_from_cache(child, category_children_map))
    return ids


def _build_category_children_map():
    """
    Build a map of parent_id -> list of child categories.
    Loads all categories in a single query.
    """
    all_categories = list(Category.objects.only("id", "parent_id", "name", "slug").all())
    children_map = {}
    for cat in all_categories:
        parent_id = cat.parent_id
        if parent_id not in children_map:
            children_map[parent_id] = []
        children_map[parent_id].append(cat)
    return children_map, {cat.id: cat for cat in all_categories}


def _get_category_product_counts_batch(category_ids):
    """
    Get product counts for multiple categories in a single query.
    Returns a dict of category_id -> product_count.
    """
    counts = (
        Product.objects.filter(status__in=VISIBLE_STATUSES, category_id__in=category_ids)
        .values("category_id")
        .annotate(count=Count("id"))
    )
    return {item["category_id"]: item["count"] for item in counts}


def _get_category_total_product_count(category, category_children_map, product_counts_by_category):
    """
    Get total product count for a category including all descendants.
    Uses pre-loaded data to avoid N+1 queries.
    """
    descendant_ids = _get_descendant_category_ids_from_cache(category, category_children_map)
    return sum(product_counts_by_category.get(cid, 0) for cid in descendant_ids)


def _get_category_product_count(category):
    """Get total product count for a category including all descendants."""
    category_ids = _get_descendant_category_ids(category)
    return Product.objects.filter(status__in=VISIBLE_STATUSES, category_id__in=category_ids).count()


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
        breadcrumb.insert(
            0,
            {
                "category": current,
                "siblings": list(Category.objects.filter(parent=current.parent).only("id", "name", "slug")),
            },
        )
        current = current.parent
    return breadcrumb


def product_list(request, category_id=None, category_slug=None):
    """
    Display product listing page with filtering, sorting, and pagination.
    """
    # Get current category from URL - use ID for faster lookup
    current_category = None
    if category_id:
        current_category = Category.objects.select_related("parent").filter(id=category_id).first()
        if not current_category:
            raise Http404("Category not found")
        if category_slug and current_category.slug != category_slug:
            redirect_url = current_category.get_absolute_url()
            if request.GET:
                redirect_url = f"{redirect_url}?{request.GET.urlencode()}"
            return redirect(redirect_url, permanent=True)

        # Apply draft changes to category early so boolean fields like show_banners
        # are updated before we use them to decide what to load
        apply_draft_to_existing_instance(request, current_category)

    # Start with active products
    products = Product.objects.filter(status__in=VISIBLE_STATUSES)

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
        products = products.filter(Q(name__icontains=search_query) | Q(description__icontains=search_query))

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
    selected_attributes_by_attr = {}
    selected_attributes_slugs = set()
    applied_attribute_filter = False
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
                    selected_attributes_by_attr[attr_id] = set(valid_option_ids)
                    # Filter products that have any of these attribute options
                    products = products.filter(attribute_values__option_id__in=valid_option_ids)
                    applied_attribute_filter = True
            except (ValueError, TypeError):
                pass

    if applied_attribute_filter:
        products = products.distinct()

    # Sorting
    current_sort = request.GET.get("sort", SORT_OPTIONS[0][0])
    sort_field = SORT_OPTIONS[0][1]
    for key, field, label in SORT_OPTIONS:
        if key == current_sort:
            sort_field = field
            break
    else:
        current_sort = SORT_OPTIONS[0][0]
    products = products.order_by(*sort_field)

    # Prefetch images and tile attributes for display (avoid N+1 queries)
    products = products.select_related("category").prefetch_related(
        Prefetch("images", queryset=ProductImage.objects.order_by("sort_order")),
        Prefetch(
            "attribute_values",
            queryset=ProductAttributeValue.objects.select_related("option__attribute")
            .filter(option__attribute__show_on_tile=True)
            .order_by("option__attribute__tile_display_order", "option__attribute__name"),
            to_attr="tile_attributes_prefetch",
        ),
    )

    # Get total count before pagination
    total_count = products.count()

    # Get per_page from request (mobile only, default to PRODUCTS_PER_PAGE)
    per_page_param = request.GET.get("per_page", "")
    try:
        per_page = int(per_page_param) if per_page_param else PRODUCTS_PER_PAGE
        if per_page not in ALLOWED_PER_PAGE:
            per_page = PRODUCTS_PER_PAGE
    except (ValueError, TypeError):
        per_page = PRODUCTS_PER_PAGE

    # Pagination
    paginator = Paginator(products, per_page)
    page_number = request.GET.get("page", 1)
    try:
        products_page = paginator.page(page_number)
    except PageNotAnInteger:
        products_page = paginator.page(1)
    except EmptyPage:
        products_page = paginator.page(paginator.num_pages)

    # Get price range for all active products (for filter hints)
    price_range = Product.objects.filter(status__in=VISIBLE_STATUSES).aggregate(
        min_price=Coalesce(Min("price"), Decimal("0")),
        max_price=Coalesce(Max("price"), Decimal("0")),
    )

    # Get available attributes for filtering - show all options that have products in base category,
    # not just in filtered results (so options don't disappear when filtering)
    # First, get the base product set (before attribute filtering) for the category
    base_products = Product.objects.filter(status__in=VISIBLE_STATUSES)
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
        attr_definitions = (
            AttributeDefinition.objects.filter(options__id__in=base_option_ids_set)
            .distinct()
            .prefetch_related(
                Prefetch(
                    "options", queryset=AttributeOption.objects.filter(id__in=base_option_ids_set).order_by("value")
                )
            )
            .order_by("name")
        )

        for attr in attr_definitions:
            # Get all options for this attribute that exist in base category
            has_selected_options = bool(selected_attributes_by_attr.get(attr.id))
            options_with_products = []
            for opt in attr.options.all():
                opt.product_count = filtered_option_id_to_count.get(opt.id, 0)

                # Hide no-op options: when selecting it would not change current results.
                # Keep currently selected options visible so users can unselect them.
                if (
                    total_count > 0
                    and not has_selected_options
                    and opt.id not in selected_attributes
                    and opt.product_count == total_count
                ):
                    continue

                options_with_products.append(opt)
            if options_with_products:
                attr.filtered_options = options_with_products
                available_attributes.append(attr)

    # Build filter categories
    filter_categories = _build_category_filter_tree(current_category)

    # Get selected category IDs from query params
    selected_category_ids = [str(c) for c in request.GET.getlist("category") if c.isdigit()]

    # Build query strings for pagination and sorting (removing view as it's now in localStorage)
    query_params = request.GET.copy()
    query_params.pop("page", None)
    query_params.pop("view", None)
    query_string = query_params.urlencode()

    # Build query string without sort parameter (for sort links)
    query_params_without_sort = query_params.copy()
    query_params_without_sort.pop("sort", None)
    query_string_without_sort = query_params_without_sort.urlencode()

    # Get view mode (list or grid) - default to list, overridden by localStorage in JS
    view_mode = "list"

    # Calculate pagination info for display (e.g., "1-30 z 144")
    start_index = (products_page.number - 1) * per_page + 1
    end_index = min(products_page.number * per_page, total_count)

    # Build breadcrumb
    breadcrumb = _build_breadcrumb(current_category) if current_category else []

    # Build subcategories navigation for sidebar with optimized batch loading
    subcategories_nav = []
    current_category_product_count = None
    parent_category_product_count = None

    if current_category:
        # Load all category data and product counts in batch (avoid N+1)
        category_children_map, all_categories_by_id = _build_category_children_map()

        # Get all category IDs we need counts for
        all_category_ids = list(all_categories_by_id.keys())
        product_counts_by_category = _get_category_product_counts_batch(all_category_ids)

        # Build subcategories with product counts
        children = category_children_map.get(current_category.id, [])
        for child in children:
            child.total_product_count = _get_category_total_product_count(
                child, category_children_map, product_counts_by_category
            )
            if child.total_product_count > 0:
                subcategories_nav.append(child)

        # Get current category product count using cached data
        current_category_product_count = _get_category_total_product_count(
            current_category, category_children_map, product_counts_by_category
        )
        if current_category.parent:
            parent_category_product_count = _get_category_total_product_count(
                current_category.parent, category_children_map, product_counts_by_category
            )

    # Determine page title
    if search_query:
        page_title = _('Search results: "%(query)s"') % {"query": search_query}
    elif current_category:
        page_title = current_category.name
    else:
        page_title = _("All products")

    # Build active filters list for display chips
    display_currency = _get_site_currency_for_labels()
    active_filters = []

    # Price filters
    if current_price_min:
        active_filters.append(
            {
                "type": "price_min",
                "value": current_price_min,
                "label": _("Price: from %(price)s %(currency)s")
                % {"price": current_price_min, "currency": display_currency},
            }
        )
    if current_price_max:
        active_filters.append(
            {
                "type": "price_max",
                "value": current_price_max,
                "label": _("Price: to %(price)s %(currency)s")
                % {"price": current_price_max, "currency": display_currency},
            }
        )

    # Attribute filters - create lookup for option values
    selected_option_ids = set()
    attr_slug_to_info = {}  # Maps attr_id -> list of (slug, option_id)
    for key in request.GET.keys():
        if key.startswith("attr_"):
            attr_id = key[5:]  # Remove "attr_" prefix
            option_slugs = request.GET.getlist(key)
            for slug_val in option_slugs:
                option_id = AttributeOption.parse_slug(slug_val)
                if option_id:
                    selected_option_ids.add(option_id)
                    if attr_id not in attr_slug_to_info:
                        attr_slug_to_info[attr_id] = []
                    attr_slug_to_info[attr_id].append((slug_val, option_id))

    # Fetch option details for selected options
    if selected_option_ids:
        options_with_attrs = AttributeOption.objects.filter(id__in=selected_option_ids).select_related("attribute")
        option_lookup = {opt.id: opt for opt in options_with_attrs}

        # Build active filter entries for each selected attribute option
        for attr_id, slug_option_pairs in attr_slug_to_info.items():
            for slug_val, option_id in slug_option_pairs:
                opt = option_lookup.get(option_id)
                if opt:
                    active_filters.append(
                        {
                            "type": f"attr_{attr_id}",
                            "value": slug_val,
                            "label": f"{opt.attribute.name}: {opt.value}",
                        }
                    )

    context = {
        "products": products_page,
        "page_title": page_title,
        "total_count": total_count,
        "start_index": start_index,
        "end_index": end_index,
        "view_mode": view_mode,
        "per_page": per_page,
        "breadcrumb": breadcrumb,
        "current_category": current_category,
        "filter_categories": filter_categories,
        "selected_category_ids": selected_category_ids,
        "sort_options": SORT_OPTIONS,
        "current_sort": current_sort,
        "query_string": query_string,
        "query_string_without_sort": query_string_without_sort,
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
        "active_filters": active_filters,
    }

    # Check if filters or non-default sorting are applied
    # When filters/sorting are active, banners and recommended products should be hidden
    has_filters_or_sorting = bool(active_filters) or current_sort != SORT_OPTIONS[0][0]
    context["has_filters_or_sorting"] = has_filters_or_sorting

    # Fetch category banners and recommended products (only when no filters/sorting applied)
    if current_category and not has_filters_or_sorting:
        # Get active banners for the category (only if show_banners is enabled)
        if current_category.show_banners:
            category_banners = CategoryBanner.objects.filter(
                category=current_category,
                is_active=True,
            ).order_by("order", "-created_at")
            context["category_banners"] = list(category_banners)

        # Get recommended products for the category (only if show_recommended_products is enabled)
        if current_category.show_recommended_products:
            recommended_products = (
                CategoryRecommendedProduct.objects.filter(
                    category=current_category,
                    product__status__in=VISIBLE_STATUSES,
                )
                .select_related("product", "product__category")
                .prefetch_related(
                    Prefetch(
                        "product__images",
                        queryset=ProductImage.objects.order_by("sort_order", "id"),
                    ),
                    Prefetch(
                        "product__attribute_values",
                        queryset=ProductAttributeValue.objects.select_related("option__attribute")
                        .filter(option__attribute__show_on_tile=True)
                        .order_by("option__attribute__tile_display_order", "option__attribute__name"),
                        to_attr="tile_attributes_prefetch",
                    ),
                )
                .order_by("order", "id")[:12]
            )
            context["recommended_products"] = list(recommended_products)

    # Return partial template for in-place filter/pagination HTMX updates.
    # History-restore requests must return full HTML, otherwise back/forward can
    # restore only the fragment and lose page chrome/sidebar.
    if (
        request.headers.get("HX-Request")
        and not request.headers.get("HX-Soft-Nav")
        and not request.headers.get("HX-History-Restore-Request")
    ):
        return render(request, "web/product_list_partial.html", context)

    return render(request, "web/product_list.html", context)
