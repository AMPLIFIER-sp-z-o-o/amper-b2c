from django.conf import settings
from django.db.models import Count, Prefetch, Q
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from health_check.views import MainView

from apps.catalog.models import Category, Product, ProductStatus
from apps.homepage.models import (
    Banner,
    HomepageSection,
    HomepageSectionBanner,
    HomepageSectionProduct,
    HomepageSectionType,
    StorefrontCategoryBox,
    StorefrontCategoryItem,
    StorefrontHeroSection,
)
from apps.support.draft_utils import apply_draft_to_instance, apply_drafts_to_context, get_draft_session_by_token


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
        .annotate(product_count=Count("section_products"))
        .filter(product_count__gt=0)
        .prefetch_related(
            Prefetch(
                "section_products",
                queryset=(
                    HomepageSectionProduct.objects.select_related("product")
                    .prefetch_related("product__images")
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

    all_sections = list(product_sections) + list(banner_sections) + list(custom_sections)
    all_sections.sort(key=lambda x: (x.order, -x.created_at.timestamp() if x.created_at else 0))

    # Prepare filtered banners for banner sections (only those with images)
    for section in all_sections:
        if section.section_type == HomepageSectionType.BANNER_SECTION:
            valid_banners = [b for b in section.section_banners.all() if b.image]
            section._filtered_banners = valid_banners

    # Get active Storefront Hero Section
    storefront_category_boxes = None
    draft_preview_enabled = getattr(request, "draft_preview_enabled", False)
    draft_changes_map = getattr(request, "draft_changes_map", {})

    if draft_preview_enabled:
        storefront_hero = (
            StorefrontHeroSection.objects.prefetch_related(
                Prefetch(
                    "category_boxes",
                    queryset=StorefrontCategoryBox.objects.order_by("order", "id").prefetch_related(
                        Prefetch("items", queryset=StorefrontCategoryItem.objects.order_by("order", "id"))
                    ),
                )
            )
            .order_by("id")
            .first()
        )

        if storefront_hero and draft_changes_map:
            apply_drafts_to_context(storefront_hero, draft_changes_map)

        if storefront_hero:
            storefront_category_boxes = list(storefront_hero.category_boxes.all())
            if draft_changes_map:
                storefront_category_boxes = apply_drafts_to_context(storefront_category_boxes, draft_changes_map)
                for box in storefront_category_boxes:
                    items = list(box.items.all())
                    if items:
                        items = apply_drafts_to_context(items, draft_changes_map)
                    box.draft_items = items

            if not storefront_hero.is_active or not storefront_hero.is_available():
                storefront_hero = None
                storefront_category_boxes = None
    else:
        storefront_hero = StorefrontHeroSection.get_active_section()

    return render(
        request,
        "web/index.html",
        {
            "banners": banners,
            "homepage_sections": all_sections,
            "storefront_hero": storefront_hero,
            "storefront_category_boxes": storefront_category_boxes,
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
        Product.objects.filter(status=ProductStatus.ACTIVE)
        .filter(Q(name__icontains=query))
        .select_related("category")
        .prefetch_related("images")
        .order_by("name")[:10]
    )

    # Search categories by name
    categories = Category.objects.filter(name__icontains=query).order_by("name")[:5]

    # Get total count for "See all results" link
    total_count = Product.objects.filter(status=ProductStatus.ACTIVE).filter(Q(name__icontains=query)).count()

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

    categories_data = [{"id": cat.id, "name": cat.name, "slug": cat.slug} for cat in categories]

    return JsonResponse(
        {
            "products": products_data,
            "categories": categories_data,
            "total_count": total_count,
            "query": query,
        }
    )
