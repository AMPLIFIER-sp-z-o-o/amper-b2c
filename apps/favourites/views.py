
from django.contrib import messages
from django.db import IntegrityError
from django.db.models import Count, Prefetch, Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.template.loader import render_to_string
from django.utils.html import format_html
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from apps.catalog.models import Product, ProductAttributeValue, ProductImage

from .models import WishList, WishListItem


def _get_session_key(request: HttpRequest) -> str:
    """Get or create session key for the request."""
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def _get_user_wishlists(request: HttpRequest):
    """Get all wishlists for the current user or session."""
    if request.user.is_authenticated:
        return WishList.objects.filter(user=request.user)
    else:
        session_key = _get_session_key(request)
        return WishList.objects.filter(session_key=session_key, user__isnull=True)


def _get_product_wishlist_status(request: HttpRequest, product_ids: list[int]) -> dict[int, list[int]]:
    """
    Get which products are in which wishlists.
    Returns a dict mapping product_id -> list of wishlist_ids.
    """
    wishlists = _get_user_wishlists(request)
    items = WishListItem.objects.filter(
        wishlist__in=wishlists,
        product_id__in=product_ids,
    ).values("product_id", "wishlist_id")

    status = {}
    for item in items:
        if item["product_id"] not in status:
            status[item["product_id"]] = []
        status[item["product_id"]].append(item["wishlist_id"])

    return status


def _get_sorted_items(items_qs, sort_param: str):
    """Apply sorting to wishlist items queryset."""
    if sort_param == "oldest":
        return items_qs.order_by("created_at")
    # Default: recently added (newest first)
    return items_qs.order_by("-created_at")


def _filter_wishlist_items(items_qs, request: HttpRequest):
    """Apply search, sort, and availability filters to wishlist items."""
    search_query = request.GET.get("q", "").strip()
    sort_param = request.GET.get("sort", "recent")
    available_param = request.GET.get("available")
    # Default to OFF (show all items) unless explicitly turned on
    available_only = available_param == "1" if available_param is not None else False

    if search_query:
        items_qs = items_qs.filter(Q(product__name__icontains=search_query))

    if available_only:
        items_qs = items_qs.filter(product__stock__gt=0)

    items_qs = _get_sorted_items(items_qs, sort_param)

    return items_qs, search_query, sort_param, available_only


@require_GET
def favourites_page(request: HttpRequest) -> HttpResponse:
    """Main favourites page showing all wishlists."""
    wishlists = (
        _get_user_wishlists(request)
        .annotate(item_count=Count("items"))
        .prefetch_related(
            Prefetch(
                "items",
                queryset=WishListItem.objects.select_related("product")
                .prefetch_related(Prefetch("product__images", queryset=ProductImage.objects.order_by("sort_order")))
                .order_by("-created_at"),
                to_attr="prefetched_items",
            )
        )
    )

    # Determine if we show overview or detail
    active_wishlist_id = request.GET.get("list")
    show_overview = False
    is_shared_view = False  # True when viewing someone else's list

    if active_wishlist_id:
        try:
            active_wishlist = wishlists.get(share_id=active_wishlist_id)
        except WishList.DoesNotExist:
            # Check if this is a shared list from another user
            try:
                active_wishlist = WishList.objects.get(share_id=active_wishlist_id)
                is_shared_view = True
            except WishList.DoesNotExist:
                active_wishlist = wishlists.filter(is_default=True).first()
    else:
        # No specific list selected → always show overview (card tiles)
        show_overview = True
        active_wishlist = None

    # Apply filters to active wishlist items (only in detail mode)
    search_query = ""
    current_sort = "recent"
    available_only = False
    filtered_items = None
    has_unavailable = False
    if active_wishlist:
        items_qs = active_wishlist.items.select_related("product__category").prefetch_related(
            Prefetch("product__images", queryset=ProductImage.objects.order_by("sort_order")),
            Prefetch(
                "product__attribute_values",
                queryset=ProductAttributeValue.objects.select_related("option__attribute")
                .filter(option__attribute__show_on_tile=True)
                .order_by("option__attribute__tile_display_order", "option__attribute__name"),
                to_attr="tile_attributes_prefetch",
            ),
        )
        # Check if any items are unavailable (stock <= 0) before filtering
        has_unavailable = active_wishlist.items.filter(product__stock__lte=0).exists()
        filtered_items, search_query, current_sort, available_only = _filter_wishlist_items(items_qs, request)

    # Sort wishlists for overview mode
    list_sort = request.GET.get("list_sort", "updated_desc")
    if show_overview:
        if list_sort == "updated_asc":
            wishlists = wishlists.order_by("updated_at")
        elif list_sort == "alpha_asc":
            wishlists = wishlists.order_by("name")
        elif list_sort == "alpha_desc":
            wishlists = wishlists.order_by("-name")
        else:
            # Default: updated_desc (newest first)
            wishlists = wishlists.order_by("-updated_at")

    # Check if all wishlists are empty (for onboarding display)
    # Also true when no wishlists exist at all
    has_wishlists = _get_user_wishlists(request).exists()
    all_lists_empty = (
        not has_wishlists or not WishListItem.objects.filter(wishlist__in=_get_user_wishlists(request)).exists()
    )

    return render(
        request,
        "favourites/favourites_page.html",
        {
            "wishlists": wishlists,
            "active_wishlist": active_wishlist,
            "filtered_items": filtered_items,
            "search_query": search_query,
            "current_sort": current_sort,
            "available_only": available_only,
            "has_unavailable": has_unavailable,
            "show_overview": show_overview,
            "is_shared_view": is_shared_view,
            "list_sort": list_sort,
            "all_lists_empty": all_lists_empty,
            "page_title": _("Shopping lists"),
        },
    )


@require_GET
def wishlist_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Detail view for a single wishlist."""
    wishlists = _get_user_wishlists(request)
    wishlist = get_object_or_404(wishlists, pk=pk)

    items_qs = wishlist.items.select_related("product__category").prefetch_related(
        Prefetch("product__images", queryset=ProductImage.objects.order_by("sort_order")),
        Prefetch(
            "product__attribute_values",
            queryset=ProductAttributeValue.objects.select_related("option__attribute")
            .filter(option__attribute__show_on_tile=True)
            .order_by("option__attribute__tile_display_order", "option__attribute__name"),
            to_attr="tile_attributes_prefetch",
        ),
    )

    has_unavailable = wishlist.items.filter(product__stock__lte=0).exists()
    items, search_query, current_sort, available_only = _filter_wishlist_items(items_qs, request)

    return render(
        request,
        "favourites/wishlist_detail.html",
        {
            "wishlist": wishlist,
            "items": items,
            "wishlists": wishlists,
            "search_query": search_query,
            "current_sort": current_sort,
            "available_only": available_only,
            "has_unavailable": has_unavailable,
            "page_title": wishlist.name,
        },
    )


@require_POST
def create_wishlist(request: HttpRequest) -> HttpResponse:
    """Create a new wishlist."""
    name = request.POST.get("name", "").strip()

    if not name:
        if request.headers.get("HX-Request"):
            return HttpResponse(
                '<div class="text-red-600 text-sm">' + _("Please enter a name for the list.") + "</div>",
                status=400,
            )
        messages.error(request, _("Please enter a name for the list."))
        return redirect("favourites:favourites_page")

    if len(name) > 64:
        if request.headers.get("HX-Request"):
            return HttpResponse(
                '<div class="text-red-600 text-sm">' + _("Name is too long (max 64 characters).") + "</div>",
                status=400,
            )
        messages.error(request, _("Name is too long (max 64 characters)."))
        return redirect("favourites:favourites_page")

    # Check for existing name
    existing = _get_user_wishlists(request).filter(name__iexact=name).exists()
    if existing:
        if request.headers.get("HX-Request"):
            return HttpResponse(
                '<div class="text-red-600 text-sm">' + _("A list with this name already exists.") + "</div>",
                status=400,
            )
        messages.error(request, _("A list with this name already exists."))
        return redirect("favourites:favourites_page")

    # Create wishlist
    if request.user.is_authenticated:
        wishlist = WishList.objects.create(name=name, user=request.user)
    else:
        wishlist = WishList.objects.create(name=name, session_key=_get_session_key(request))

    # Add products from product picker if any
    product_ids = request.POST.getlist("product_ids")
    if product_ids:
        from apps.catalog.models import Product

        products = Product.objects.filter(id__in=product_ids)
        for product in products:
            WishListItem.objects.get_or_create(wishlist=wishlist, product=product)

    # Copy items from another wishlist (when coming from Copy to List → Create New List)
    copy_item_ids = request.POST.getlist("copy_item_ids")
    if copy_item_ids:
        source_items = WishListItem.objects.filter(
            pk__in=copy_item_ids, wishlist__in=_get_user_wishlists(request)
        ).select_related("product")
        for item in source_items:
            WishListItem.objects.get_or_create(
                wishlist=wishlist,
                product=item.product,
                defaults={"price_when_added": item.price_when_added},
            )

    if request.headers.get("HX-Request"):
        # Return JSON for HTMX
        return JsonResponse(
            {
                "success": True,
                "wishlist": {
                    "id": wishlist.id,
                    "name": wishlist.name,
                    "is_default": wishlist.is_default,
                },
                "message": _("List created successfully."),
            }
        )

    messages.success(request, _("List created successfully."))
    return redirect("favourites:favourites_page")


@require_POST
def update_wishlist(request: HttpRequest, pk: int) -> HttpResponse:
    """Update wishlist name or description."""
    wishlists = _get_user_wishlists(request)
    wishlist = get_object_or_404(wishlists, pk=pk)

    name = request.POST.get("name", "").strip()
    description = request.POST.get("description", "").strip()

    if not name:
        if request.headers.get("HX-Request"):
            return HttpResponse(
                '<div class="text-red-600 text-sm">' + _("Please enter a name for the list.") + "</div>",
                status=400,
            )
        messages.error(request, _("Please enter a name for the list."))
        return redirect("favourites:favourites_page")

    # Check for duplicate name (excluding current)
    existing = wishlists.filter(name__iexact=name).exclude(pk=pk).exists()
    if existing:
        if request.headers.get("HX-Request"):
            return HttpResponse(
                '<div class="text-red-600 text-sm">' + _("A list with this name already exists.") + "</div>",
                status=400,
            )
        messages.error(request, _("A list with this name already exists."))
        return redirect("favourites:favourites_page")

    wishlist.name = name
    wishlist.description = description
    wishlist.save()

    if request.headers.get("HX-Request"):
        return JsonResponse(
            {
                "success": True,
                "wishlist": {
                    "id": wishlist.id,
                    "name": wishlist.name,
                    "description": wishlist.description,
                },
                "message": _("List updated successfully."),
            }
        )

    messages.success(request, _("List updated successfully."))
    return redirect(f"{reverse('favourites:favourites_page')}?list={wishlist.share_id}")


@require_POST
def delete_wishlist(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a wishlist."""
    wishlists = _get_user_wishlists(request)
    wishlist = get_object_or_404(wishlists, pk=pk)

    wishlist.delete()

    if request.headers.get("HX-Request"):
        return JsonResponse({"success": True, "message": _("List deleted successfully.")})

    messages.success(request, _("List deleted successfully."))
    return redirect("favourites:favourites_page")


@require_POST
def add_to_wishlist(request: HttpRequest) -> HttpResponse:
    """Add a product to a wishlist."""
    product_id = request.POST.get("product_id")
    wishlist_id = request.POST.get("wishlist_id")

    if not product_id:
        return JsonResponse({"success": False, "message": _("Product ID is required.")}, status=400)

    product = get_object_or_404(Product, pk=product_id)

    # Get or create wishlist
    wishlists = _get_user_wishlists(request)
    if wishlist_id:
        try:
            wishlist = wishlists.get(pk=int(wishlist_id))
        except (ValueError, WishList.DoesNotExist):
            return JsonResponse({"success": False, "message": _("Wishlist not found.")}, status=404)
    else:
        # Use default wishlist
        if request.user.is_authenticated:
            wishlist = WishList.get_or_create_default(user=request.user)
        else:
            wishlist = WishList.get_or_create_default(session_key=_get_session_key(request))

    # Add item
    try:
        item = WishListItem.objects.create(
            wishlist=wishlist,
            product=product,
            price_when_added=product.price,
        )
    except IntegrityError:
        # Product already in wishlist
        return JsonResponse(
            {
                "success": False,
                "already_in_list": True,
                "message": _("Product is already in this list."),
            },
            status=400,
        )

    # Get all wishlists for the response
    all_wishlists = list(wishlists.values("id", "name", "is_default"))

    return JsonResponse(
        {
            "success": True,
            "message": format_html(
                _("Added <strong>{product_name}</strong> to {list_name}."),
                product_name=product.name,
                list_name=wishlist.name,
            ),
            "item": {
                "id": item.id,
                "wishlist_id": wishlist.id,
                "wishlist_name": wishlist.name,
                "product_id": product.id,
            },
            "wishlists": all_wishlists,
        }
    )


@require_POST
def remove_from_wishlist(request: HttpRequest) -> HttpResponse:
    """Remove a product from a wishlist."""
    item_id = request.POST.get("item_id")
    product_id = request.POST.get("product_id")
    wishlist_id = request.POST.get("wishlist_id")

    wishlists = _get_user_wishlists(request)

    if item_id:
        # Remove by item ID
        item = get_object_or_404(WishListItem, pk=item_id, wishlist__in=wishlists)
        wishlist = item.wishlist
        product_id = item.product_id
        product_name = item.product.name
        item.delete()
    elif product_id and wishlist_id:
        # Remove by product and wishlist
        item = get_object_or_404(WishListItem, product_id=product_id, wishlist_id=wishlist_id, wishlist__in=wishlists)
        wishlist = item.wishlist
        product_name = item.product.name
        item.delete()
    elif product_id:
        # Remove from all wishlists
        items = WishListItem.objects.filter(product_id=product_id, wishlist__in=wishlists)
        count = items.count()
        # Get product name from first item
        first_item = items.first()
        product_name = first_item.product.name if first_item else ""
        items.delete()
        return JsonResponse(
            {
                "success": True,
                "message": format_html(
                    _("Removed <strong>{product_name}</strong> from {count} list(s)."),
                    product_name=product_name,
                    count=count,
                ),
                "product_id": int(product_id),
                "product_name": product_name,
            }
        )
    else:
        return JsonResponse({"success": False, "message": _("Item or product ID is required.")}, status=400)

    # Get updated wishlist stats
    item_count = wishlist.items.count()
    total_value = float(wishlist.total_value)

    return JsonResponse(
        {
            "success": True,
            "message": format_html(
                _("Removed <strong>{product_name}</strong> from {list_name}."),
                product_name=product_name,
                list_name=wishlist.name,
            ),
            "product_id": int(product_id),
            "product_name": product_name,
            "wishlist_id": wishlist.id,
            "wishlist_item_count": item_count,
            "wishlist_total_value": total_value,
        }
    )


@require_POST
def move_item(request: HttpRequest) -> HttpResponse:
    """Move an item from one wishlist to another."""
    item_id = request.POST.get("item_id")
    target_wishlist_id = request.POST.get("target_wishlist_id")

    if not item_id or not target_wishlist_id:
        return JsonResponse({"success": False, "message": _("Item and target wishlist are required.")}, status=400)

    wishlists = _get_user_wishlists(request)
    item = get_object_or_404(WishListItem, pk=item_id, wishlist__in=wishlists)
    target_wishlist = get_object_or_404(wishlists, pk=target_wishlist_id)

    # Check if already in target
    if WishListItem.objects.filter(wishlist=target_wishlist, product=item.product).exists():
        return JsonResponse({"success": False, "message": _("Product is already in the target list.")}, status=400)

    # Move item
    source_wishlist = item.wishlist
    item.wishlist = target_wishlist
    item.save()

    return JsonResponse(
        {
            "success": True,
            "message": _("Moved to {list_name}.").format(list_name=target_wishlist.name),
            "item_id": item.id,
            "source_wishlist_id": source_wishlist.id,
            "target_wishlist_id": target_wishlist.id,
        }
    )


@require_POST
def add_all_to_cart(request: HttpRequest) -> HttpResponse:
    """Add all items from a wishlist to the cart."""
    from apps.cart.models import Cart, CartLine
    from apps.cart.services import refresh_cart_totals_from_db
    from apps.catalog.models import ProductStatus

    wishlist_id = request.POST.get("wishlist_id")

    if not wishlist_id:
        return JsonResponse({"success": False, "message": _("Wishlist ID is required.")}, status=400)

    wishlists = _get_user_wishlists(request)
    wishlist = get_object_or_404(wishlists, pk=wishlist_id)

    items = wishlist.items.select_related("product").all()
    added_count = 0
    unavailable_count = 0

    # Get or create cart ONCE before the loop
    cart_id = request.session.get("cart_id")
    cart = None
    if cart_id:
        cart = Cart.objects.filter(id=cart_id).first()
    if not cart:
        cart = Cart.objects.create(customer=request.user if request.user.is_authenticated else None)
        request.session["cart_id"] = cart.id

    for item in items:
        product = item.product
        is_purchasable = product.status == ProductStatus.ACTIVE and product.stock > 0
        if not is_purchasable:
            unavailable_count += 1
            continue

        line, created = CartLine.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={"quantity": 1, "price": product.price},
        )

        if created:
            added_count += 1
            continue

        current_quantity = line.quantity
        if current_quantity >= product.stock:
            unavailable_count += 1
            # Keep price fresh even when we cannot increase quantity.
            if line.price != product.price:
                line.price = product.price
                line.save(update_fields=["price"])
            continue

        line.quantity = min(current_quantity + 1, product.stock)
        line.price = product.price
        line.save(update_fields=["quantity", "price"])
        added_count += 1

    # Ensure totals/discounts are consistent with the current DB state.
    cart.recalculate()
    refresh_cart_totals_from_db(cart)

    message = _("{count} item(s) added to cart.").format(count=added_count)
    if unavailable_count > 0:
        message += " " + _("{count} item(s) were unavailable.").format(count=unavailable_count)

    # Render nav dropdown lines HTML so the client can refresh the dropdown without reloading.
    cart_lines = list(cart.lines.select_related("product").all())
    nav_cart_lines_html = "".join(
        render_to_string("Cart/nav_cart_line.html", {"line": line}, request=request) for line in cart_lines
    )

    lines_count = sum(int(line.quantity or 0) for line in cart_lines)
    delivery_cost = cart.delivery_method.get_cost_for_cart(cart.subtotal) if cart.delivery_method else 0

    response = JsonResponse(
        {
            "success": True,
            "message": message,
            "added_count": added_count,
            "unavailable_count": unavailable_count,
            "cart_id": cart.id,
            "lines_count": lines_count,
            "cart_total": str(cart.total),
            "cart_subtotal": str(cart.subtotal),
            "discount_total": str(cart.discount_total),
            "delivery_cost": str(delivery_cost),
            "nav_cart_lines_html": nav_cart_lines_html,
        }
    )
    response.set_cookie("cart_id", cart.id, max_age=60 * 60 * 24 * 10)
    return response


@require_GET
def get_wishlists(request: HttpRequest) -> HttpResponse:
    """Get all wishlists for the current user (for dropdowns).

    Optional query params:
      - product_id: If provided, each wishlist entry will include
        ``contains_product`` (bool) indicating whether the product is in that list.
    """
    wishlists = _get_user_wishlists(request).annotate(item_count=Count("items"))

    # Determine per-list containment when product_id is provided
    product_id = request.GET.get("product_id")
    containing_ids: set[int] = set()
    if product_id:
        try:
            pid = int(product_id)
            containing_ids = set(
                WishListItem.objects.filter(wishlist__in=wishlists, product_id=pid).values_list(
                    "wishlist_id", flat=True
                )
            )
        except (ValueError, TypeError):
            pass

    data = []
    for wl in wishlists:
        entry = {
            "id": wl.id,
            "name": wl.name,
            "is_default": wl.is_default,
            "item_count": wl.item_count,
        }
        if product_id:
            entry["contains_product"] = wl.id in containing_ids
        data.append(entry)

    return JsonResponse({"wishlists": data})


@require_GET
def check_product_status(request: HttpRequest) -> HttpResponse:
    """Check which wishlists contain specific products."""
    product_ids = request.GET.get("product_ids", "")
    if not product_ids:
        return JsonResponse({"status": {}})

    try:
        product_ids = [int(pid) for pid in product_ids.split(",")]
    except ValueError:
        return JsonResponse({"status": {}})

    status = _get_product_wishlist_status(request, product_ids)

    return JsonResponse({"status": status})


@require_POST
def toggle_favourite(request: HttpRequest) -> HttpResponse:
    """Toggle a product in the default wishlist (quick add/remove)."""
    product_id = request.POST.get("product_id")

    if not product_id:
        return JsonResponse({"success": False, "message": _("Product ID is required.")}, status=400)

    product = get_object_or_404(Product, pk=product_id)

    # Get default wishlist
    if request.user.is_authenticated:
        wishlist = WishList.get_or_create_default(user=request.user)
    else:
        wishlist = WishList.get_or_create_default(session_key=_get_session_key(request))

    # Check if exists
    existing = wishlist.items.filter(product=product).first()
    if existing:
        # Remove
        existing.delete()
        # Get updated wishlist stats
        item_count = wishlist.items.count()
        total_value = float(wishlist.total_value)
        return JsonResponse(
            {
                "success": True,
                "action": "removed",
                "is_favourite": False,
                "message": format_html(
                    _("Removed <strong>{product_name}</strong> from Favourites."),
                    product_name=product.name,
                ),
                "product_id": int(product_id),
                "product_name": product.name,
                "wishlist_id": wishlist.id,
                "wishlist_item_count": item_count,
                "wishlist_total_value": total_value,
            }
        )
    else:
        # Add
        WishListItem.objects.create(
            wishlist=wishlist,
            product=product,
            price_when_added=product.price,
        )
        # Get updated wishlist stats
        item_count = wishlist.items.count()
        total_value = float(wishlist.total_value)
        return JsonResponse(
            {
                "success": True,
                "action": "added",
                "is_favourite": True,
                "message": format_html(
                    _("Added <strong>{product_name}</strong> to Favourites."),
                    product_name=product.name,
                ),
                "product_id": int(product_id),
                "product_name": product.name,
                "wishlist_id": wishlist.id,
                "wishlist_item_count": item_count,
                "wishlist_total_value": total_value,
            }
        )


# Partial templates for HTMX
@require_GET
def wishlist_items_partial(request: HttpRequest) -> HttpResponse:
    """Partial template for wishlist items (HTMX)."""
    share_id = request.GET.get("list")
    if not share_id:
        return HttpResponse("", status=400)

    wishlists = _get_user_wishlists(request)
    wishlist = get_object_or_404(wishlists, share_id=share_id)

    items_qs = wishlist.items.select_related("product__category").prefetch_related(
        Prefetch("product__images", queryset=ProductImage.objects.order_by("sort_order")),
        Prefetch(
            "product__attribute_values",
            queryset=ProductAttributeValue.objects.select_related("option__attribute")
            .filter(option__attribute__show_on_tile=True)
            .order_by("option__attribute__tile_display_order", "option__attribute__name"),
            to_attr="tile_attributes_prefetch",
        ),
    )
    items, search_query, current_sort, available_only = _filter_wishlist_items(items_qs, request)
    has_unavailable = wishlist.items.filter(product__stock__lte=0).exists()

    return render(
        request,
        "favourites/partials/wishlist_products.html",
        {
            "wishlist": wishlist,
            "items": items,
            "wishlists": wishlists,
            "search_query": search_query,
            "current_sort": current_sort,
            "available_only": available_only,
            "has_unavailable": has_unavailable,
        },
    )


@require_GET
def wishlists_sidebar_partial(request: HttpRequest) -> HttpResponse:
    """Partial template for wishlists sidebar (HTMX)."""
    wishlists = _get_user_wishlists(request).annotate(item_count=Count("items"))
    active_id = request.GET.get("active")
    active_wishlist = None
    if active_id:
        try:
            active_wishlist = wishlists.get(share_id=active_id)
        except WishList.DoesNotExist:
            pass

    return render(
        request,
        "favourites/partials/wishlists_sidebar.html",
        {"wishlists": wishlists, "active_wishlist": active_wishlist},
    )


@require_POST
def copy_items(request: HttpRequest) -> HttpResponse:
    """Copy selected items to another wishlist."""
    item_ids = request.POST.getlist("item_ids")
    target_wishlist_id = request.POST.get("target_wishlist_id")

    if not item_ids or not target_wishlist_id:
        return JsonResponse({"success": False, "message": _("Please select items and a target list.")}, status=400)

    wishlists = _get_user_wishlists(request)
    target_wishlist = get_object_or_404(wishlists, pk=target_wishlist_id)
    items = WishListItem.objects.filter(pk__in=item_ids, wishlist__in=wishlists)

    copied_count = 0
    skipped_count = 0
    last_copied_product_name = ""
    for item in items:
        if WishListItem.objects.filter(wishlist=target_wishlist, product=item.product).exists():
            skipped_count += 1
            continue
        WishListItem.objects.create(
            wishlist=target_wishlist,
            product=item.product,
            price_when_added=item.price_when_added,
        )
        last_copied_product_name = item.product.name
        copied_count += 1

    if copied_count == 1:
        message = format_html(
            _("Copied <strong>{product_name}</strong> to {list_name}."),
            product_name=last_copied_product_name,
            list_name=target_wishlist.name,
        )
    else:
        message = _("{count} products copied to {list_name}.").format(
            count=copied_count, list_name=target_wishlist.name
        )
    if skipped_count == 1:
        message += " " + _("1 product already existed.")
    elif skipped_count > 1:
        message += " " + _("{count} products already existed.").format(count=skipped_count)

    return JsonResponse({"success": True, "message": message, "copied_count": copied_count})


@require_POST
def bulk_remove(request: HttpRequest) -> HttpResponse:
    """Remove multiple items from a wishlist."""
    item_ids = request.POST.getlist("item_ids")

    if not item_ids:
        return JsonResponse({"success": False, "message": _("Please select items to remove.")}, status=400)

    wishlists = _get_user_wishlists(request)
    items = WishListItem.objects.filter(pk__in=item_ids, wishlist__in=wishlists)
    count = items.count()

    # Get wishlist for response stats
    first_item = items.first()
    wishlist = first_item.wishlist if first_item else None

    items.delete()

    response_data = {"success": True, "message": _("{count} item(s) removed.").format(count=count)}
    if wishlist:
        response_data["wishlist_id"] = wishlist.id
        response_data["wishlist_item_count"] = wishlist.items.count()
        response_data["wishlist_total_value"] = float(wishlist.total_value)

    return JsonResponse(response_data)


@require_GET
def get_all_products(request: HttpRequest) -> HttpResponse:
    """Get all unique products across all wishlists for the product picker modal."""
    wishlists = _get_user_wishlists(request)
    items = (
        WishListItem.objects.filter(wishlist__in=wishlists)
        .select_related("product")
        .prefetch_related(Prefetch("product__images", queryset=ProductImage.objects.order_by("sort_order")))
        .order_by("-created_at")
    )

    # Deduplicate by product
    seen = set()
    products = []
    for item in items:
        if item.product_id not in seen:
            seen.add(item.product_id)
            first_image = item.product.images.first()
            products.append(
                {
                    "id": item.product_id,
                    "name": item.product.name,
                    "image_url": first_image.image.url if first_image else "",
                    "price": float(item.product.price),
                }
            )

    return JsonResponse({"products": products})
