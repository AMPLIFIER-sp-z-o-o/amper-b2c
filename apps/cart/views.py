from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.catalog.models import Product, ProductStatus
from apps.favourites.models import WishList, WishListItem
from apps.orders.forms import CheckoutDetailsForm
from apps.orders.models import Coupon, CouponKind
from apps.users.models import ShippingAddress

from .checkout import (
    CHECKOUT_MODE_ORDER_SESSION,
    CHECKOUT_MODE_USER_DEFAULT,
    clear_checkout_session,
    get_checkout_mode,
    get_checkout_state,
    set_checkout_active_details,
    set_checkout_order_details,
    touch_checkout_session,
)
from .models import Cart, CartLine, DeliveryMethod, PaymentMethod
from .services import (
    _annotate_lines_with_stock_issues,
    _clear_cart_id,
    _get_cart_from_request,
    ensure_cart_methods_active,
    refresh_cart_totals_from_db,
)

_PHONE_CALLING_CODE_BY_COUNTRY_ISO2 = {
    "PL": "+48",
    "DE": "+49",
    "GB": "+44",
    "US": "+1",
    "FR": "+33",
    "ES": "+34",
    "IT": "+39",
    "NL": "+31",
    "BE": "+32",
    "CZ": "+420",
    "SK": "+421",
}


def _detect_country_iso2_from_request(request) -> str:
    """Best-effort country detection for phone prefix defaults.

    In production this is commonly provided by a CDN/WAF header.
    Falls back to PL.
    """
    meta = getattr(request, "META", {}) or {}
    candidates = [
        meta.get("HTTP_CF_IPCOUNTRY"),
        meta.get("HTTP_CLOUDFRONT_VIEWER_COUNTRY"),
        meta.get("HTTP_X_COUNTRY_CODE"),
        meta.get("HTTP_X_COUNTRY"),
    ]
    for value in candidates:
        if not value:
            continue
        iso2 = str(value).strip().upper()
        if len(iso2) == 2 and iso2.isalpha():
            return iso2
    return "PL"


def _get_default_phone_country_code(request) -> str:
    iso2 = _detect_country_iso2_from_request(request)
    return _PHONE_CALLING_CODE_BY_COUNTRY_ISO2.get(iso2, "+48")


def _get_cart_items_count(cart: Cart) -> int:
    """Total quantity of all products in the cart (sum of line.quantity)."""
    try:
        total = cart.lines.aggregate(total=Sum("quantity")).get("total")
    except Exception:
        total = None
    return int(total or 0)


# Create your views here.
def cart_page(request):
    cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")

    state = get_checkout_state(request, touch=False)
    checkout_details = state.active_details

    shipping_addresses = []
    if request.user.is_authenticated:
        shipping_addresses = request.user.shipping_addresses.all()

    if not cart_id:
        return render(
            request,
            "Cart/cart_page.html",
            {
                "lines": [],
                "products_count": 0,
                "shipping_addresses": shipping_addresses,
                "checkout_details": checkout_details,
                "total": Decimal("0.00"),
                "subtotal": Decimal("0.00"),
                "discount_total": Decimal("0.00"),
                "delivery_cost": Decimal("0.00"),
            },
        )

    cart = _get_cart_from_request(request, cart_id)
    if not cart and request.user.is_authenticated:
        # Self-heal: cookie/session might point to an old cart (e.g. after logout/login on shared device).
        cart = Cart.objects.filter(customer=request.user).order_by("-id").first()
        if cart:
            request.session["cart_id"] = cart.id

    if not cart:
        response = render(
            request,
            "Cart/cart_page.html",
            {
                "lines": [],
                "products_count": 0,
                "requires_cart_fix": False,
                "shipping_addresses": shipping_addresses,
                "checkout_details": checkout_details,
                "total": Decimal("0.00"),
                "subtotal": Decimal("0.00"),
                "discount_total": Decimal("0.00"),
                "delivery_cost": Decimal("0.00"),
            },
        )
        return _clear_cart_id(request, response=response)

    if not cart.lines.exists():
        # Cart exists in session, but it's empty.
        # Ensure the UI doesn't show persisted fees or checkout actions.
        cart.recalculate()
        return render(
            request,
            "Cart/cart_page.html",
            {
                "cart": cart,
                "lines": [],
                "products_count": 0,
                "requires_cart_fix": False,
                "shipping_addresses": shipping_addresses,
                "checkout_details": checkout_details,
                "total": Decimal("0.00"),
                "subtotal": Decimal("0.00"),
                "discount_total": Decimal("0.00"),
                "delivery_cost": Decimal("0.00"),
            },
        )

    # Keep cart pricing consistent with current DB state (prices/coupons can change in admin).
    refresh_result = refresh_cart_totals_from_db(cart)
    if refresh_result.get("coupon_cleared"):
        messages.error(request, _("Your promo code is no longer available."))

    # Re-fetch lines after refresh (line prices may have changed).
    lines = list(cart.lines.select_related("product").all())

    stock_issues = _annotate_lines_with_stock_issues(lines)
    requires_cart_fix = bool(stock_issues)

    request.session["cart_id"] = cart.id

    delivery_cost = cart.delivery_method.get_cost_for_cart(cart.subtotal) if cart.delivery_method else Decimal("0.00")

    shipping_addresses = []
    if request.user.is_authenticated:
        shipping_addresses = request.user.shipping_addresses.all()

    return render(
        request,
        "Cart/cart_page.html",
        {
            "cart": cart,
            "lines": lines,
            "products_count": sum(int(line.quantity or 0) for line in lines),
            "requires_cart_fix": requires_cart_fix,
            "shipping_addresses": shipping_addresses,
            "checkout_details": checkout_details,
            "total": cart.total,
            "subtotal": cart.subtotal,
            "discount_total": cart.discount_total,
            "delivery_cost": delivery_cost,
        },
    )


@require_POST
@login_required
def set_cart_address(request):
    address_id = request.POST.get("address_id")
    if not address_id:
        return JsonResponse({"success": False, "message": _("Address ID required")}, status=400)

    address = get_object_or_404(ShippingAddress, id=address_id, user=request.user)

    # Store in session as the active checkout details, but do NOT overwrite the
    # "address entered in this order" snapshot.
    checkout_details = get_checkout_state(request).active_details
    full_name = (address.full_name or "").strip()
    parts = full_name.split(None, 1)
    first_name = parts[0] if parts else ""
    last_name = parts[1] if len(parts) > 1 else ""
    checkout_details.update(
        {
            "first_name": first_name,
            "last_name": last_name,
            "phone_country_code": (address.phone_country_code or "+48").strip() or "+48",
            "phone_number": (address.phone_number or "").strip(),
            "email": request.user.email,
            "shipping_city": (address.shipping_city or "").strip(),
            "shipping_postal_code": (address.shipping_postal_code or "").strip(),
            "shipping_street": (address.shipping_street or "").strip(),
            "shipping_building_number": (address.shipping_building_number or "").strip(),
            "shipping_apartment_number": (address.shipping_apartment_number or "").strip(),
        }
    )
    set_checkout_active_details(request, checkout_details, mode=CHECKOUT_MODE_USER_DEFAULT)

    # Recalculate cart
    cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")
    if cart_id:
        cart = _get_cart_from_request(request, cart_id)
        if cart:
            cart.recalculate()

    # Support both fetch (JSON) and classic form POST (redirect) usage.
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"success": True})
    return redirect("cart:checkout_page")


@require_POST
@login_required
def set_checkout_address_choice(request):
    """Switch between using the user's default saved address vs the address entered in this order."""
    choice = (request.POST.get("choice") or "").strip()
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    state = get_checkout_state(request)
    order_details = state.order_details

    if choice == CHECKOUT_MODE_ORDER_SESSION:
        if order_details:
            set_checkout_active_details(request, order_details, mode=CHECKOUT_MODE_ORDER_SESSION)
        else:
            touch_checkout_session(request, set_mode=CHECKOUT_MODE_ORDER_SESSION)
        if wants_json:
            return JsonResponse({"success": True, "mode": CHECKOUT_MODE_ORDER_SESSION})
        return redirect("cart:checkout_page")

    # Default to user_default.
    default_addr = (
        ShippingAddress.objects.filter(user=request.user, is_default=True).order_by("-updated_at", "-id").first()
    ) or (ShippingAddress.objects.filter(user=request.user).order_by("-updated_at", "-id").first())
    if not default_addr:
        if wants_json:
            return JsonResponse({"success": False, "message": _("No saved address found.")}, status=400)
        messages.error(request, _("No saved address found."))
        return redirect("cart:checkout_page")

    full_name = (default_addr.full_name or "").strip()
    parts = full_name.split(None, 1)
    first_name = parts[0] if parts else ""
    last_name = parts[1] if len(parts) > 1 else ""

    active = {
        "first_name": first_name,
        "last_name": last_name,
        "phone_country_code": (default_addr.phone_country_code or "+48").strip() or "+48",
        "phone_number": (default_addr.phone_number or "").strip(),
        "email": request.user.email,
        "shipping_city": (default_addr.shipping_city or "").strip(),
        "shipping_postal_code": (default_addr.shipping_postal_code or "").strip(),
        "shipping_street": (default_addr.shipping_street or "").strip(),
        "shipping_building_number": (default_addr.shipping_building_number or "").strip(),
        "shipping_apartment_number": (default_addr.shipping_apartment_number or "").strip(),
    }
    set_checkout_active_details(request, active, mode=CHECKOUT_MODE_USER_DEFAULT)

    if wants_json:
        return JsonResponse({"success": True, "mode": CHECKOUT_MODE_USER_DEFAULT})
    return redirect("cart:checkout_page")


@require_POST
def apply_coupon(request):
    cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")
    response = redirect("cart:cart_page")
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    def _json_payload(cart, *, success: bool, message: str, message_type: str = "success", status: int = 200):
        payload = {
            "success": success,
            "message": message,
            "message_type": message_type,
            "coupon_code": (getattr(cart, "coupon_code", "") or ""),
            "discount_total": str(getattr(cart, "discount_total", Decimal("0.00"))),
            "cart_total": str(getattr(cart, "total", Decimal("0.00"))),
            "cart_subtotal": str(getattr(cart, "subtotal", Decimal("0.00"))),
        }

        if cart and getattr(cart, "delivery_method_id", None):
            try:
                payload["delivery_cost"] = str(cart.delivery_method.get_cost_for_cart(cart.subtotal))
            except Exception:
                payload["delivery_cost"] = "0.00"
        else:
            payload["delivery_cost"] = "0.00"

        return JsonResponse(payload, status=status)

    code = (request.POST.get("coupon_code") or "").strip()
    # Hard cap to the model field length to avoid pointless DB work on very long inputs.
    code = code[:50]
    if not code:
        if wants_json:
            return _json_payload(
                None, success=False, message=str(_("Please enter a promo code.")), message_type="error"
            )
        messages.error(request, _("Please enter a promo code."))
        return response

    cart = _get_cart_from_request(request, cart_id)
    if not cart:
        if wants_json:
            return _clear_cart_id(
                request,
                response=_json_payload(
                    None, success=False, message=str(_("Your cart is empty.")), message_type="error"
                ),
            )
        messages.error(request, _("Your cart is empty."))
        return _clear_cart_id(request, response=response)

    if not cart.lines.exists():
        cart.discount_total = Decimal("0.00")
        cart.coupon_code = ""
        cart.recalculate()
        if wants_json:
            return _json_payload(cart, success=False, message=str(_("Your cart is empty.")), message_type="error")
        messages.error(request, _("Your cart is empty."))
        return response

    # Ensure subtotal is computed from current Product.price before validating/applying coupon.
    # This prevents applying a coupon against stale line prices.
    refresh_cart_totals_from_db(cart)

    now = timezone.now()
    coupon = Coupon.objects.filter(is_active=True, code__iexact=code).order_by("-updated_at").first()

    if not coupon:
        cart.discount_total = Decimal("0.00")
        cart.coupon_code = ""
        cart.recalculate()
        if wants_json:
            return _json_payload(cart, success=False, message=str(_("Invalid promo code.")), message_type="error")
        messages.error(request, _("Invalid promo code."))
        return response

    if coupon.valid_from and now < coupon.valid_from:
        if wants_json:
            return _json_payload(
                cart,
                success=False,
                message=str(_("This promo code is not active yet.")),
                message_type="error",
            )
        messages.error(request, _("This promo code is not active yet."))
        return response
    if coupon.valid_to and now > coupon.valid_to:
        if wants_json:
            return _json_payload(
                cart, success=False, message=str(_("This promo code has expired.")), message_type="error"
            )
        messages.error(request, _("This promo code has expired."))
        return response
    if coupon.usage_limit is not None and coupon.used_count >= coupon.usage_limit:
        if wants_json:
            return _json_payload(
                cart,
                success=False,
                message=str(_("This promo code is no longer available.")),
                message_type="error",
            )
        messages.error(request, _("This promo code is no longer available."))
        return response

    cart.recalculate()
    if coupon.min_subtotal is not None and cart.subtotal < coupon.min_subtotal:
        msg = _("This promo code requires a minimum total of %(amount)s.") % {"amount": coupon.min_subtotal}
        if wants_json:
            return _json_payload(cart, success=False, message=str(msg), message_type="error")
        messages.error(request, msg)
        return response

    discount_total = Decimal("0.00")
    if coupon.kind == CouponKind.PERCENT:
        try:
            discount_total = (cart.subtotal * Decimal(coupon.value) / Decimal("100.00")).quantize(Decimal("0.01"))
        except Exception:
            discount_total = Decimal("0.00")
    elif coupon.kind == CouponKind.FIXED:
        try:
            discount_total = Decimal(coupon.value).quantize(Decimal("0.01"))
        except Exception:
            discount_total = Decimal("0.00")

    if discount_total < 0:
        discount_total = Decimal("0.00")
    if discount_total > cart.subtotal:
        discount_total = cart.subtotal

    cart.coupon_code = coupon.code
    cart.discount_total = discount_total
    cart.recalculate()

    if wants_json:
        return _json_payload(cart, success=True, message=str(_("Promo code applied.")), message_type="success")

    messages.success(request, _("Promo code applied."))
    return response


@require_POST
def remove_coupon(request):
    cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")
    response = redirect("cart:cart_page")
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    def _json_payload(cart, *, success: bool, message: str, message_type: str = "success", status: int = 200):
        payload = {
            "success": success,
            "message": message,
            "message_type": message_type,
            "coupon_code": (getattr(cart, "coupon_code", "") or ""),
            "discount_total": str(getattr(cart, "discount_total", Decimal("0.00"))),
            "cart_total": str(getattr(cart, "total", Decimal("0.00"))),
            "cart_subtotal": str(getattr(cart, "subtotal", Decimal("0.00"))),
        }

        if cart and getattr(cart, "delivery_method_id", None):
            try:
                payload["delivery_cost"] = str(cart.delivery_method.get_cost_for_cart(cart.subtotal))
            except Exception:
                payload["delivery_cost"] = "0.00"
        else:
            payload["delivery_cost"] = "0.00"

        return JsonResponse(payload, status=status)

    cart = _get_cart_from_request(request, cart_id)
    if not cart:
        if wants_json:
            return _clear_cart_id(
                request,
                response=_json_payload(
                    None, success=True, message=str(_("Promo code removed.")), message_type="success"
                ),
            )
        return _clear_cart_id(request, response=response)

    cart.discount_total = Decimal("0.00")
    cart.coupon_code = ""
    cart.recalculate()
    if wants_json:
        return _json_payload(cart, success=True, message=str(_("Promo code removed.")), message_type="success")
    messages.success(request, _("Promo code removed."))
    return response


@require_POST
def clear_cart(request):
    cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")

    # Clearing the cart should also reset the checkout session cache.
    clear_checkout_session(request)

    response = redirect("cart:cart_page")

    if not cart_id:
        return _clear_cart_id(request, response=response)

    cart = _get_cart_from_request(request, cart_id)
    if not cart:
        return _clear_cart_id(request, response=response)

    cart.delete()
    messages.success(request, _("Cart cleared."))
    return _clear_cart_id(request, response=response)


@require_POST
def save_as_list(request):
    cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")
    wants_htmx = bool(request.headers.get("HX-Request"))

    def _htmx_error(message: str) -> HttpResponse:
        return HttpResponse(
            f'<p class="text-sm text-red-600 dark:text-red-400">{message}</p>',
            status=400,
        )

    if not cart_id:
        if wants_htmx:
            return _htmx_error(str(_("Your cart is empty.")))
        messages.error(request, _("Your cart is empty."))
        return redirect("cart:cart_page")

    cart = _get_cart_from_request(request, cart_id)
    if not cart:
        if wants_htmx:
            return _htmx_error(str(_("Your cart is empty.")))
        messages.error(request, _("Your cart is empty."))
        return _clear_cart_id(request, response=redirect("cart:cart_page"))

    lines = list(cart.lines.select_related("product").all())
    if not lines:
        if wants_htmx:
            return _htmx_error(str(_("Your cart is empty.")))
        messages.error(request, _("Your cart is empty."))
        return redirect("cart:cart_page")

    name = (request.POST.get("name") or "").strip()
    if not name:
        if wants_htmx:
            return _htmx_error(str(_("Please enter a name for the list.")))
        messages.error(request, _("Please enter a name for the list."))
        return redirect("cart:cart_page")

    if len(name) > 64:
        if wants_htmx:
            return _htmx_error(str(_("Name is too long (max 64 characters).")))
        messages.error(request, _("Name is too long (max 64 characters)."))
        return redirect("cart:cart_page")

    session_key = None
    if not request.user.is_authenticated:
        if not request.session.session_key:
            request.session.create()
        session_key = request.session.session_key

    owner_qs = (
        WishList.objects.filter(user=request.user)
        if request.user.is_authenticated
        else WishList.objects.filter(session_key=session_key, user__isnull=True)
    )
    if owner_qs.filter(name__iexact=name).exists():
        if wants_htmx:
            return _htmx_error(str(_("A list with this name already exists.")))
        messages.error(request, _("A list with this name already exists."))
        return redirect("cart:cart_page")

    with transaction.atomic():
        wishlist = (
            WishList.objects.create(name=name, user=request.user)
            if request.user.is_authenticated
            else WishList.objects.create(name=name, session_key=session_key)
        )

        for line in lines:
            if not line.product_id:
                continue
            WishListItem.objects.get_or_create(
                wishlist=wishlist,
                product=line.product,
                defaults={"price_when_added": line.product.price},
            )

    if wants_htmx:
        messages.success(request, _("List created successfully."))
        response = HttpResponse("")
        response["HX-Redirect"] = wishlist.get_absolute_url()
        return response

    messages.success(request, _("List created successfully."))
    return redirect(wishlist.get_absolute_url())


@require_POST
def add_to_cart(request):
    product_id = request.POST.get("product_id")
    try:
        quantity = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 1
    cart_id = request.POST.get("cart_id")
    if not cart_id:
        cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")

    mode = (request.POST.get("mode") or "set").strip().lower()
    if mode not in {"set", "increment"}:
        mode = "set"

    product = get_object_or_404(Product, id=product_id)

    if quantity <= 0:
        return JsonResponse({"success": False, "message": _("Invalid quantity.")}, status=400)

    # Hard guard: hidden/disabled/out-of-stock products cannot be added
    if product.status != ProductStatus.ACTIVE or product.stock <= 0:
        return JsonResponse(
            {"success": False, "message": _("Product is currently unavailable.")},
            status=409,
        )

    requested_quantity = quantity

    cart = None
    if cart_id:
        cart = Cart.objects.filter(id=cart_id).first()

    # Self-heal: after logout, clients may still send a cart_id from cookie/localStorage
    # that points to a user-bound cart. Anonymous users must never mutate that cart;
    # instead, we ignore it and create a fresh anonymous cart.
    if cart and cart.customer_id:
        if request.user.is_authenticated and cart.customer_id == request.user.id:
            pass
        elif request.user.is_authenticated:
            # Different user -> ignore stale/tampered cart_id and fall back to the current user's cart.
            cart = Cart.objects.filter(customer=request.user).order_by("-id").first()
        else:
            cart = None

    if not cart and request.user.is_authenticated:
        cart = Cart.objects.filter(customer=request.user).order_by("-id").first()

    if not cart:
        cart = Cart.objects.create(customer=request.user if request.user.is_authenticated else None)

    # Lock the cart line row to avoid race conditions that could exceed stock
    # when the user clicks quickly (or has multiple tabs).
    with transaction.atomic():
        line = CartLine.objects.select_for_update().filter(cart=cart, product=product).first()
        current_quantity = line.quantity if line else 0

        if mode == "increment":
            remaining = max(product.stock - current_quantity, 0)
            to_add = min(requested_quantity, remaining)
            if to_add <= 0:
                return JsonResponse(
                    {
                        "success": False,
                        "message": _("No more stock available for this product."),
                        "available_stock": product.stock,
                    },
                    status=409,
                )

            applied_quantity = to_add
            quantity_adjusted = applied_quantity != requested_quantity
            new_quantity = current_quantity + applied_quantity
        else:
            new_quantity = min(requested_quantity, product.stock)
            applied_quantity = new_quantity
            quantity_adjusted = applied_quantity != requested_quantity

        if line is None:
            line = CartLine.objects.create(
                cart=cart,
                product=product,
                quantity=new_quantity,
                price=product.price,
            )
        else:
            line.quantity = new_quantity
            line.price = product.price
            line.save(update_fields=["quantity", "price"])

    # Refresh totals/discounts from the current DB state so percent coupons stay accurate
    # when the cart subtotal changes, and so coupon validity changes are picked up.
    refresh_cart_totals_from_db(cart)

    # Re-fetch the line to reflect any refreshed price.
    line = CartLine.objects.select_related("product").get(pk=line.pk)

    request.session["cart_id"] = cart.id

    line_html = render_to_string("Cart/nav_cart_line.html", {"line": line}, request=request)

    delivery_cost = cart.delivery_method.get_cost_for_cart(cart.subtotal) if cart.delivery_method else Decimal("0.00")

    response = JsonResponse(
        {
            "success": True,
            "cart_id": cart.id,
            "cart_total": str(cart.total),
            "cart_subtotal": str(cart.subtotal),
            "discount_total": str(cart.discount_total),
            "product_quantity": line.quantity,
            # Total quantity of all products in cart (not number of distinct lines)
            "lines_count": _get_cart_items_count(cart),
            "updated_line_html": line_html,
            "product_name": product.name,
            "line_subtotal": str(line.subtotal),
            "line_id": line.id,
            "delivery_cost": delivery_cost,
            "quantity_adjusted": quantity_adjusted,
            "requested_quantity": requested_quantity,
            "applied_quantity": applied_quantity,
            "available_stock": product.stock,
            "mode": mode,
        }
    )

    response.set_cookie("cart_id", cart.id, max_age=60 * 60 * 24 * 10)
    return response


@require_POST
def remove_from_cart(request):
    product_id = request.POST.get("product_id")
    cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")

    if not product_id or not cart_id:
        return JsonResponse({"success": False}, status=400)

    cart = Cart.objects.filter(id=cart_id).first()
    if not cart:
        response = JsonResponse(
            {
                "success": True,
                "cart_total": "0.00",
                "cart_subtotal": "0.00",
                "discount_total": "0.00",
                "lines_count": 0,
                "delivery_cost": "0.00",
            }
        )
        return _clear_cart_id(request, response=response)

    if cart.customer_id:
        if not request.user.is_authenticated or cart.customer_id != request.user.id:
            response = JsonResponse(
                {
                    "success": True,
                    "cart_total": "0.00",
                    "cart_subtotal": "0.00",
                    "discount_total": "0.00",
                    "lines_count": 0,
                    "delivery_cost": "0.00",
                }
            )
            return _clear_cart_id(request, response=response)

    line = CartLine.objects.filter(cart=cart, product_id=product_id).first()

    if not line:
        return JsonResponse({"success": False}, status=404)

    cart = line.cart

    line_id = line.id
    product_name = line.product.name

    line.delete()
    refresh_cart_totals_from_db(cart)

    delivery_cost = cart.delivery_method.get_cost_for_cart(cart.subtotal) if cart.delivery_method else Decimal("0.00")

    return JsonResponse(
        {
            "success": True,
            "cart_total": str(cart.total),
            "cart_subtotal": str(cart.subtotal),
            "discount_total": str(cart.discount_total),
            # Total quantity of all products in cart (not number of distinct lines)
            "lines_count": _get_cart_items_count(cart),
            "removed_line_id": line_id,
            "product_name": product_name,
            "delivery_cost": delivery_cost,
        }
    )


def checkout_page(request):
    cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")
    if not cart_id:
        return redirect("cart:cart_page")

    cart = _get_cart_from_request(request, cart_id)
    if not cart:
        response = redirect("cart:cart_page")
        return _clear_cart_id(request, response=response)

    methods_changed = ensure_cart_methods_active(cart)
    if methods_changed.get("delivery_method_cleared") or methods_changed.get("payment_method_cleared"):
        messages.info(request, _("Your previously selected delivery or payment method is no longer available."))

    # Re-price lines and re-calc totals from DB (prices/coupons can change after the cart was created).
    refresh_cart_totals_from_db(cart)

    lines = list(cart.lines.select_related("product").all())
    stock_issues = _annotate_lines_with_stock_issues(lines)
    if stock_issues:
        return redirect("cart:cart_page")

    state = get_checkout_state(request)
    if state.expired:
        messages.info(request, _("Your checkout session expired. Please enter your delivery details again."))

    checkout_details = state.active_details
    order_details = state.order_details
    checkout_meta = state.meta
    checkout_mode = get_checkout_mode(checkout_meta)

    def _has_checkout_identity(details: dict) -> bool:
        keys = [
            "first_name",
            "last_name",
            "shipping_street",
            "shipping_city",
            "shipping_postal_code",
            "shipping_building_number",
        ]
        return any((details.get(k) or "").strip() for k in keys)

    # If we have active details but no order snapshot yet, initialize it.
    if checkout_details and not order_details:
        set_checkout_order_details(request, checkout_details)
        order_details = dict(checkout_details)

    default_phone_country_code = _get_default_phone_country_code(request)
    if not (checkout_details.get("phone_country_code") or "").strip():
        checkout_details["phone_country_code"] = default_phone_country_code
        set_checkout_active_details(request, checkout_details, mode=checkout_mode)
    if order_details and not (order_details.get("phone_country_code") or "").strip():
        order_details["phone_country_code"] = default_phone_country_code
        set_checkout_order_details(request, order_details)

    user_default_address = None
    user_has_addresses = False
    user_default_address_is_complete = False
    if request.user.is_authenticated:
        try:
            user_has_addresses = ShippingAddress.objects.filter(user=request.user).exists()
            user_default_address = (
                ShippingAddress.objects.filter(user=request.user, is_default=True)
                .order_by("-updated_at", "-id")
                .first()
            ) or (ShippingAddress.objects.filter(user=request.user).order_by("-updated_at", "-id").first())

            if user_default_address:
                user_default_address_is_complete = all(
                    (getattr(user_default_address, attr, "") or "").strip()
                    for attr in [
                        "full_name",
                        "phone_country_code",
                        "phone_number",
                        "shipping_city",
                        "shipping_postal_code",
                        "shipping_street",
                        "shipping_building_number",
                    ]
                )
        except Exception:
            user_has_addresses = False
            user_default_address = None
            user_default_address_is_complete = False

    # If session is effectively empty and user has a default address, default to using it.
    # (Do not overwrite the order-entered snapshot if it exists.)
    if (
        request.user.is_authenticated
        and not order_details
        and user_default_address
        and user_default_address_is_complete
        and checkout_mode == CHECKOUT_MODE_ORDER_SESSION
        and not _has_checkout_identity(checkout_details)
    ):
        checkout_mode = CHECKOUT_MODE_USER_DEFAULT
        touch_checkout_session(request, set_mode=CHECKOUT_MODE_USER_DEFAULT)

    # Decide which details should be active for the order.
    if request.user.is_authenticated:
        if checkout_mode == CHECKOUT_MODE_USER_DEFAULT:
            # If default address exists but is incomplete, do not let the user proceed in this mode.
            if user_default_address and not user_default_address_is_complete:
                checkout_mode = CHECKOUT_MODE_ORDER_SESSION
                touch_checkout_session(request, set_mode=CHECKOUT_MODE_ORDER_SESSION)
            elif user_default_address:
                full_name = (user_default_address.full_name or "").strip()
                parts = full_name.split(None, 1)
                first_name = parts[0] if parts else ""
                last_name = parts[1] if len(parts) > 1 else ""
                checkout_details = {
                    "first_name": first_name,
                    "last_name": last_name,
                    "phone_country_code": (user_default_address.phone_country_code or "+48").strip() or "+48",
                    "phone_number": (user_default_address.phone_number or "").strip(),
                    "email": request.user.email,
                    "shipping_city": (user_default_address.shipping_city or "").strip(),
                    "shipping_postal_code": (user_default_address.shipping_postal_code or "").strip(),
                    "shipping_street": (user_default_address.shipping_street or "").strip(),
                    "shipping_building_number": (user_default_address.shipping_building_number or "").strip(),
                    "shipping_apartment_number": (user_default_address.shipping_apartment_number or "").strip(),
                }
                set_checkout_active_details(request, checkout_details, mode=CHECKOUT_MODE_USER_DEFAULT)
        else:
            # order_session
            if order_details and checkout_details != order_details:
                checkout_details = dict(order_details)
                set_checkout_active_details(request, checkout_details, mode=CHECKOUT_MODE_ORDER_SESSION)

    # Keep authenticated email in active details if missing.
    if request.user.is_authenticated and request.user.email:
        if checkout_details and not (checkout_details.get("email") or "").strip():
            checkout_details["email"] = request.user.email
            set_checkout_active_details(request, checkout_details, mode=checkout_mode)
        if order_details and not (order_details.get("email") or "").strip():
            order_details["email"] = request.user.email
            set_checkout_order_details(request, order_details)

    # Prefill first/last name from the user's account settings when missing.
    if request.user.is_authenticated:
        user_first_name = (getattr(request.user, "first_name", "") or "").strip()
        user_last_name = (getattr(request.user, "last_name", "") or "").strip()

        if checkout_details:
            changed = False
            if user_first_name and not (checkout_details.get("first_name") or "").strip():
                checkout_details["first_name"] = user_first_name
                changed = True
            if user_last_name and not (checkout_details.get("last_name") or "").strip():
                checkout_details["last_name"] = user_last_name
                changed = True
            if changed:
                set_checkout_active_details(request, checkout_details, mode=checkout_mode)

        if order_details:
            changed = False
            if user_first_name and not (order_details.get("first_name") or "").strip():
                order_details["first_name"] = user_first_name
                changed = True
            if user_last_name and not (order_details.get("last_name") or "").strip():
                order_details["last_name"] = user_last_name
                changed = True
            if changed:
                set_checkout_order_details(request, order_details)

    # Ensure the country code is always present for validation / storage.
    if not (checkout_details.get("phone_country_code") or "").strip():
        checkout_details["phone_country_code"] = default_phone_country_code
        set_checkout_active_details(request, checkout_details, mode=checkout_mode)

    cart.recalculate()

    delivery_methods = DeliveryMethod.objects.filter(is_active=True)
    payment_methods = PaymentMethod.objects.filter(is_active=True)
    delivery_methods = delivery_methods.order_by("name")
    payment_methods = payment_methods.order_by("name")

    delivery_cost = cart.delivery_method.get_cost_for_cart(cart.subtotal) if cart.delivery_method else Decimal("0.00")

    if request.method == "POST":
        method_id = request.POST.get("delivery-method")
        payment_id = request.POST.get("payment-method")
        if method_id:
            method = get_object_or_404(DeliveryMethod, id=method_id, is_active=True)
            cart.delivery_method = method

        if payment_id:
            payment = get_object_or_404(
                PaymentMethod,
                id=payment_id,
                is_active=True,
            )
            cart.payment_method = payment

        cart.save()
        refresh_cart_totals_from_db(cart)

        delivery_cost = (
            cart.delivery_method.get_cost_for_cart(cart.subtotal) if cart.delivery_method else Decimal("0.00")
        )

        return JsonResponse(
            {
                "success": True,
                "delivery_method_id": cart.delivery_method.id if cart.delivery_method else None,
                "payment_method_id": cart.payment_method.id if cart.payment_method else None,
                "total": str(cart.total),
                "subtotal": str(cart.subtotal),
                "discount_total": str(cart.discount_total),
                "delivery_cost": str(delivery_cost),
            }
        )
    # Form is used only when the user chooses the "address entered in this order".
    details_form = CheckoutDetailsForm(initial=(order_details or checkout_details))

    return render(
        request,
        "Cart/checkout_page.html",
        {
            "cart": cart,
            "subtotal": cart.subtotal,
            "discount_total": cart.discount_total,
            "total": cart.total,
            "disable_cart_dropdown": True,
            "delivery_methods": delivery_methods,
            "selected_delivery": cart.delivery_method,
            "delivery_cost": str(delivery_cost),
            "payment_methods": payment_methods,
            "selected_payment": cart.payment_method,
            "details_form": details_form,
            "checkout_details": checkout_details,
            "checkout_order_details": order_details,
            "checkout_mode": checkout_mode,
            "user_default_address": user_default_address,
            "user_default_address_is_complete": user_default_address_is_complete,
            "user_has_addresses": user_has_addresses,
            "phone_country_code": checkout_details.get("phone_country_code") or default_phone_country_code,
        },
    )


@require_POST
def checkout_save_details(request):
    cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")
    if not cart_id:
        return redirect("cart:cart_page")

    cart = _get_cart_from_request(request, cart_id)
    if not cart:
        response = redirect("cart:cart_page")
        return _clear_cart_id(request, response=response)

    # Keep totals/discounts current (prices/coupons can change while user is in checkout).
    refresh_result = refresh_cart_totals_from_db(cart)
    if refresh_result.get("coupon_cleared"):
        messages.error(request, _("Your promo code is no longer available."))

    lines = list(cart.lines.select_related("product").all())
    stock_issues = _annotate_lines_with_stock_issues(lines)
    if stock_issues:
        return redirect("cart:cart_page")

    state = get_checkout_state(request)
    if state.expired:
        messages.info(request, _("Your checkout session expired. Please enter your delivery details again."))
        return redirect("cart:checkout_page")

    checkout_action = (request.POST.get("checkout_action") or "").strip()

    checkout_mode = (request.POST.get("checkout_mode") or "").strip() or get_checkout_mode(state.meta)
    if checkout_mode not in {CHECKOUT_MODE_ORDER_SESSION, CHECKOUT_MODE_USER_DEFAULT}:
        checkout_mode = CHECKOUT_MODE_ORDER_SESSION

    # Address-only save (from the modal "Done" button):
    # - validates and stores delivery details in session
    # - does NOT require delivery/payment method selection
    # - redirects back to checkout page so the address summary updates
    if checkout_action == "save_only":
        mutable = request.POST.copy()
        expected_code = (state.order_details or state.active_details or {}).get(
            "phone_country_code"
        ) or _get_default_phone_country_code(request)
        mutable["phone_country_code"] = expected_code
        form = CheckoutDetailsForm(mutable)
        if not form.is_valid():
            delivery_methods = DeliveryMethod.objects.filter(is_active=True).order_by("name")
            payment_methods = PaymentMethod.objects.filter(is_active=True).order_by("name")
            delivery_cost = (
                cart.delivery_method.get_cost_for_cart(cart.subtotal) if cart.delivery_method else Decimal("0.00")
            )
            return render(
                request,
                "Cart/checkout_page.html",
                {
                    "cart": cart,
                    "subtotal": cart.subtotal,
                    "discount_total": cart.discount_total,
                    "total": cart.total,
                    "disable_cart_dropdown": True,
                    "delivery_methods": delivery_methods,
                    "selected_delivery": cart.delivery_method,
                    "delivery_cost": str(delivery_cost),
                    "payment_methods": payment_methods,
                    "selected_payment": cart.payment_method,
                    "details_form": form,
                    "checkout_details": get_checkout_state(request, touch=False).active_details,
                    "checkout_order_details": get_checkout_state(request, touch=False).order_details,
                    "checkout_mode": CHECKOUT_MODE_ORDER_SESSION,
                    "user_default_address": None,
                    "user_has_addresses": request.user.is_authenticated
                    and ShippingAddress.objects.filter(user=request.user).exists(),
                    "phone_country_code": expected_code,
                },
                status=400,
            )

        cart.recalculate()
        set_checkout_order_details(request, form.cleaned_data)
        set_checkout_active_details(request, form.cleaned_data, mode=CHECKOUT_MODE_ORDER_SESSION)
        touch_checkout_session(request, set_mode=CHECKOUT_MODE_ORDER_SESSION)
        return redirect("cart:checkout_page")

    # Persist delivery/payment selection if provided.
    # This makes the flow robust when JS fails (the radios are still submitted with the details form).
    delivery_method_id = (request.POST.get("delivery-method") or "").strip()
    payment_method_id = (request.POST.get("payment-method") or "").strip()

    if delivery_method_id:
        delivery_method = DeliveryMethod.objects.filter(id=delivery_method_id, is_active=True).first()
        if not delivery_method:
            messages.error(request, _("Please select a valid delivery method."))
            return redirect("cart:checkout_page")
        cart.delivery_method = delivery_method

    if payment_method_id:
        payment_method = PaymentMethod.objects.filter(id=payment_method_id, is_active=True).first()
        if not payment_method:
            messages.error(request, _("Please select a valid payment method."))
            return redirect("cart:checkout_page")
        cart.payment_method = payment_method

    if delivery_method_id or payment_method_id:
        cart.save(update_fields=["delivery_method", "payment_method"])
        cart.recalculate()

    # Enforce that delivery/payment are selected.
    if not cart.delivery_method:
        messages.error(request, _("Please select a delivery method."))
        return redirect("cart:checkout_page")
    if not cart.payment_method:
        messages.error(request, _("Please select a payment method."))
        return redirect("cart:checkout_page")

    # user_default mode: validate current session active details and proceed.
    if checkout_mode == CHECKOUT_MODE_USER_DEFAULT:
        touch_checkout_session(request, set_mode=CHECKOUT_MODE_USER_DEFAULT)
        active = get_checkout_state(request).active_details
        # If user_default is selected but we don't have a snapshot in session,
        # do not attempt to read dynamically from DB here. Force user to revisit checkout.
        if not active or any(
            not (active.get(k) or "").strip()
            for k in [
                "first_name",
                "last_name",
                "email",
                "phone_country_code",
                "phone_number",
                "shipping_city",
                "shipping_postal_code",
                "shipping_street",
                "shipping_building_number",
            ]
        ):
            # Prefer using the address entered in this order if available.
            order_details = get_checkout_state(request, touch=False).order_details
            if order_details:
                set_checkout_active_details(request, order_details, mode=CHECKOUT_MODE_ORDER_SESSION)
                touch_checkout_session(request, set_mode=CHECKOUT_MODE_ORDER_SESSION)
            messages.error(request, _("Please select a valid delivery address."))
            return redirect("cart:checkout_page")

        expected_code = (active.get("phone_country_code") or "").strip() or _get_default_phone_country_code(request)
        active["phone_country_code"] = expected_code
        form = CheckoutDetailsForm(active)
        if not form.is_valid():
            messages.error(request, _("Please complete your delivery details."))
            return redirect("cart:checkout_page")
        # Normalize stored active details.
        set_checkout_active_details(request, form.cleaned_data, mode=CHECKOUT_MODE_USER_DEFAULT)
        cart.recalculate()
        return redirect("cart:summary_page")

    # order_session mode: validate posted details.
    mutable = request.POST.copy()
    expected_code = (state.order_details or state.active_details or {}).get(
        "phone_country_code"
    ) or _get_default_phone_country_code(request)
    mutable["phone_country_code"] = expected_code
    form = CheckoutDetailsForm(mutable)
    if not form.is_valid():
        # Re-render checkout with errors
        checkout_details = get_checkout_state(request, touch=False).active_details

        delivery_methods = DeliveryMethod.objects.filter(is_active=True)
        payment_methods = PaymentMethod.objects.filter(is_active=True)
        delivery_methods = delivery_methods.order_by("name")
        payment_methods = payment_methods.order_by("name")

        delivery_cost = (
            cart.delivery_method.get_cost_for_cart(cart.subtotal) if cart.delivery_method else Decimal("0.00")
        )

        return render(
            request,
            "Cart/checkout_page.html",
            {
                "cart": cart,
                "subtotal": cart.subtotal,
                "discount_total": cart.discount_total,
                "total": cart.total,
                "disable_cart_dropdown": True,
                "delivery_methods": delivery_methods,
                "selected_delivery": cart.delivery_method,
                "delivery_cost": str(delivery_cost),
                "payment_methods": payment_methods,
                "selected_payment": cart.payment_method,
                "details_form": form,
                "checkout_details": checkout_details,
                "checkout_order_details": get_checkout_state(request, touch=False).order_details,
                "checkout_mode": CHECKOUT_MODE_ORDER_SESSION,
                "user_default_address": None,
                "user_has_addresses": request.user.is_authenticated
                and ShippingAddress.objects.filter(user=request.user).exists(),
                "phone_country_code": expected_code,
            },
            status=400,
        )

    cart.recalculate()

    # Persist the "address entered in this order" snapshot.
    set_checkout_order_details(request, form.cleaned_data)
    set_checkout_active_details(request, form.cleaned_data, mode=CHECKOUT_MODE_ORDER_SESSION)

    # Save to user's address book:
    # - If the user has no addresses -> save as default automatically.
    # - If the user already has addresses -> only if explicit checkbox is checked.
    if request.user.is_authenticated:
        wants_save = str(request.POST.get("save_address_to_account") or "").strip() in {"1", "true", "on", "yes"}
        try:
            existing_qs = ShippingAddress.objects.filter(user=request.user)
            has_any = existing_qs.exists()

            should_save = (not has_any) or wants_save
            if should_save:

                def _norm(value: str) -> str:
                    return " ".join(str(value or "").strip().split()).lower()

                street = _norm(form.cleaned_data.get("shipping_street"))
                postal = _norm(form.cleaned_data.get("shipping_postal_code"))
                city = _norm(form.cleaned_data.get("shipping_city"))
                building = _norm(form.cleaned_data.get("shipping_building_number"))
                apt = _norm(form.cleaned_data.get("shipping_apartment_number"))

                match = (
                    existing_qs.filter(
                        shipping_street__iexact=street,
                        shipping_postal_code__iexact=postal,
                        shipping_city__iexact=city,
                        shipping_building_number__iexact=building,
                        shipping_apartment_number__iexact=apt,
                    )
                    .order_by("-is_default", "-updated_at", "-id")
                    .first()
                )

                defaults = {
                    "full_name": form.get_full_name(),
                    "phone_country_code": form.cleaned_data.get("phone_country_code", expected_code),
                    "phone_number": form.cleaned_data.get("phone_number", ""),
                    "shipping_city": form.cleaned_data.get("shipping_city", ""),
                    "shipping_postal_code": form.cleaned_data.get("shipping_postal_code", ""),
                    "shipping_street": form.cleaned_data.get("shipping_street", ""),
                    "shipping_building_number": form.cleaned_data.get("shipping_building_number", ""),
                    "shipping_apartment_number": form.cleaned_data.get("shipping_apartment_number", ""),
                }

                if match:
                    # Do not create duplicates; promote existing to default.
                    for k, v in defaults.items():
                        setattr(match, k, v)
                    match.is_default = True
                    match.save()
                    ShippingAddress.objects.filter(user=request.user).exclude(pk=match.pk).update(is_default=False)
                else:
                    ShippingAddress.objects.filter(user=request.user).update(is_default=False)
                    ShippingAddress.objects.create(user=request.user, is_default=True, **defaults)
        except Exception:
            pass

    return redirect("cart:summary_page")


def summary_page(request):
    cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")
    if not cart_id:
        return redirect("cart:cart_page")

    cart = _get_cart_from_request(request, cart_id)
    if not cart:
        response = redirect("cart:cart_page")
        return _clear_cart_id(request, response=response)

    # Do not trust stale selections (admin can disable methods while user is in checkout).
    methods_changed = ensure_cart_methods_active(cart)
    if methods_changed.get("delivery_method_cleared") or methods_changed.get("payment_method_cleared"):
        messages.error(request, _("Please re-select your delivery and payment methods."))
        return redirect("cart:checkout_page")

    # Re-price lines and re-calc totals from DB (prices/coupons can change after the cart was created).
    refresh_cart_totals_from_db(cart)

    lines = list(cart.lines.select_related("product").all())
    stock_issues = _annotate_lines_with_stock_issues(lines)
    if stock_issues:
        return redirect("cart:cart_page")

    state = get_checkout_state(request)
    if state.expired:
        messages.info(request, _("Your checkout session expired. Please enter your delivery details again."))
        return redirect("cart:checkout_page")

    checkout_details = state.active_details
    if not checkout_details:
        return redirect("cart:checkout_page")

    # Keep checkout session alive while user reviews the order.
    touch_checkout_session(request)

    # At this point totals are already refreshed; compute delivery/payment costs from the fresh subtotal.
    delivery_cost = cart.delivery_method.get_cost_for_cart(cart.subtotal) if cart.delivery_method else Decimal("0.00")
    delivery_name = cart.delivery_method.name if cart.delivery_method else ""

    payment_name = cart.payment_method.name if cart.payment_method else ""

    return render(
        request,
        "Cart/summary_page.html",
        {
            "cart": cart,
            "lines": lines,
            "subtotal": cart.subtotal,
            "total": cart.total,
            "discount_total": cart.discount_total,
            "disable_cart_dropdown": True,
            "selected_delivery": cart.delivery_method,
            "delivery_cost": delivery_cost,
            "delivery_name": delivery_name,
            "selected_payment": cart.payment_method,
            "payment_name": payment_name,
            "checkout_details": checkout_details,
            "now": timezone.now(),
        },
    )
