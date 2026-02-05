import json
from decimal import Decimal

from django.contrib import messages
from django.db import IntegrityError
from django.db.models import Count, Prefetch
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.html import format_html
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from apps.catalog.models import Product, ProductImage

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


@require_GET
def favourites_page(request: HttpRequest) -> HttpResponse:
    """Main favourites page showing all wishlists."""
    wishlists = _get_user_wishlists(request).prefetch_related(
        Prefetch(
            "items",
            queryset=WishListItem.objects.select_related("product").prefetch_related(
                Prefetch("product__images", queryset=ProductImage.objects.order_by("sort_order"))
            ),
        )
    ).annotate(item_count=Count("items"))

    # Get or create default wishlist
    if not wishlists.filter(is_default=True).exists():
        if request.user.is_authenticated:
            WishList.get_or_create_default(user=request.user)
        else:
            WishList.get_or_create_default(session_key=_get_session_key(request))
        # Re-fetch wishlists
        wishlists = _get_user_wishlists(request).prefetch_related(
            Prefetch(
                "items",
                queryset=WishListItem.objects.select_related("product").prefetch_related(
                    Prefetch("product__images", queryset=ProductImage.objects.order_by("sort_order"))
                ),
            )
        ).annotate(item_count=Count("items"))

    # Get active wishlist from query param or default
    active_wishlist_id = request.GET.get("list")
    if active_wishlist_id:
        try:
            active_wishlist = wishlists.get(pk=int(active_wishlist_id))
        except (ValueError, WishList.DoesNotExist):
            active_wishlist = wishlists.filter(is_default=True).first()
    else:
        active_wishlist = wishlists.filter(is_default=True).first()

    return render(
        request,
        "favourites/favourites_page.html",
        {
            "wishlists": wishlists,
            "active_wishlist": active_wishlist,
            "page_title": _("Favourites"),
        },
    )


@require_GET
def wishlist_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Detail view for a single wishlist."""
    wishlists = _get_user_wishlists(request)
    wishlist = get_object_or_404(wishlists, pk=pk)

    items = wishlist.items.select_related("product").prefetch_related(
        Prefetch("product__images", queryset=ProductImage.objects.order_by("sort_order"))
    )

    return render(
        request,
        "favourites/wishlist_detail.html",
        {
            "wishlist": wishlist,
            "items": items,
            "wishlists": wishlists,
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

    if len(name) > 100:
        if request.headers.get("HX-Request"):
            return HttpResponse(
                '<div class="text-red-600 text-sm">' + _("Name is too long (max 100 characters).") + "</div>",
                status=400,
            )
        messages.error(request, _("Name is too long (max 100 characters)."))
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
    return redirect("favourites:favourites_page")


@require_POST
def delete_wishlist(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a wishlist (cannot delete default)."""
    wishlists = _get_user_wishlists(request)
    wishlist = get_object_or_404(wishlists, pk=pk)

    if wishlist.is_default:
        if request.headers.get("HX-Request"):
            return JsonResponse(
                {"success": False, "message": _("Cannot delete the default Favourites list.")},
                status=400,
            )
        messages.error(request, _("Cannot delete the default Favourites list."))
        return redirect("favourites:favourites_page")

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
            "message": _("Added to {list_name}.").format(list_name=wishlist.name),
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
        item = get_object_or_404(
            WishListItem, product_id=product_id, wishlist_id=wishlist_id, wishlist__in=wishlists
        )
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
                "message": _("Removed {product_name} from {count} list(s).").format(
                    product_name=product_name, count=count
                ),
                "product_id": int(product_id),
                "product_name": product_name,
            }
        )
    else:
        return JsonResponse(
            {"success": False, "message": _("Item or product ID is required.")}, status=400
        )

    # Get updated wishlist stats
    item_count = wishlist.items.count()
    total_value = float(wishlist.total_value)

    return JsonResponse(
        {
            "success": True,
            "message": _("Removed {product_name} from {list_name}.").format(
                product_name=product_name, list_name=wishlist.name
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
        return JsonResponse(
            {"success": False, "message": _("Item and target wishlist are required.")}, status=400
        )

    wishlists = _get_user_wishlists(request)
    item = get_object_or_404(WishListItem, pk=item_id, wishlist__in=wishlists)
    target_wishlist = get_object_or_404(wishlists, pk=target_wishlist_id)

    # Check if already in target
    if WishListItem.objects.filter(wishlist=target_wishlist, product=item.product).exists():
        return JsonResponse(
            {"success": False, "message": _("Product is already in the target list.")}, status=400
        )

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
    wishlist_id = request.POST.get("wishlist_id")

    if not wishlist_id:
        return JsonResponse({"success": False, "message": _("Wishlist ID is required.")}, status=400)

    wishlists = _get_user_wishlists(request)
    wishlist = get_object_or_404(wishlists, pk=wishlist_id)

    items = wishlist.items.select_related("product").all()
    added_count = 0
    unavailable_count = 0

    for item in items:
        if item.product.stock > 0:
            # Import cart logic
            from apps.cart.models import Cart, CartLine

            # Get or create cart
            cart_id = request.session.get("cart_id")
            cart = None
            if cart_id:
                cart = Cart.objects.filter(id=cart_id).first()
            if not cart:
                cart = Cart.objects.create(
                    customer=request.user if request.user.is_authenticated else None
                )
                request.session["cart_id"] = cart.id

            # Add to cart
            line, created = CartLine.objects.get_or_create(
                cart=cart,
                product=item.product,
                defaults={"quantity": 1, "price": item.product.price},
            )
            if not created:
                line.quantity += 1
                line.save(update_fields=["quantity"])

            cart.recalculate()
            added_count += 1
        else:
            unavailable_count += 1

    message = _("{count} item(s) added to cart.").format(count=added_count)
    if unavailable_count > 0:
        message += " " + _("{count} item(s) were unavailable.").format(count=unavailable_count)

    return JsonResponse(
        {
            "success": True,
            "message": message,
            "added_count": added_count,
            "unavailable_count": unavailable_count,
        }
    )


@require_GET
def get_wishlists(request: HttpRequest) -> HttpResponse:
    """Get all wishlists for the current user (for dropdowns)."""
    wishlists = _get_user_wishlists(request).annotate(item_count=Count("items"))

    # Ensure default wishlist exists
    if not wishlists.filter(is_default=True).exists():
        if request.user.is_authenticated:
            WishList.get_or_create_default(user=request.user)
        else:
            WishList.get_or_create_default(session_key=_get_session_key(request))
        wishlists = _get_user_wishlists(request).annotate(item_count=Count("items"))

    data = []
    for wl in wishlists:
        data.append(
            {
                "id": wl.id,
                "name": wl.name,
                "is_default": wl.is_default,
                "item_count": wl.item_count,
            }
        )

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
def wishlist_items_partial(request: HttpRequest, pk: int) -> HttpResponse:
    """Partial template for wishlist items (HTMX)."""
    wishlists = _get_user_wishlists(request)
    wishlist = get_object_or_404(wishlists, pk=pk)

    items = wishlist.items.select_related("product").prefetch_related(
        Prefetch("product__images", queryset=ProductImage.objects.order_by("sort_order"))
    )

    return render(
        request,
        "favourites/partials/wishlist_items.html",
        {"wishlist": wishlist, "items": items, "wishlists": wishlists},
    )


@require_GET
def wishlists_sidebar_partial(request: HttpRequest) -> HttpResponse:
    """Partial template for wishlists sidebar (HTMX)."""
    wishlists = _get_user_wishlists(request).annotate(item_count=Count("items"))
    active_id = request.GET.get("active")
    active_wishlist = None
    if active_id:
        try:
            active_wishlist = wishlists.get(pk=int(active_id))
        except (ValueError, WishList.DoesNotExist):
            pass

    return render(
        request,
        "favourites/partials/wishlists_sidebar.html",
        {"wishlists": wishlists, "active_wishlist": active_wishlist},
    )
