from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404
from django.contrib import messages
from django.utils.translation import gettext as _
from django.db import transaction
from django.utils import timezone
from django.db.models import Q, Sum
from django.contrib.auth.decorators import login_required

from apps.catalog.models import Product, ProductStatus
from apps.users.models import ShippingAddress
from .checkout import CHECKOUT_SESSION_KEY
from .models import Cart, CartLine, DeliveryMethod, PaymentMethod
from .services import _annotate_lines_with_stock_issues, _clear_cart_id, _get_cart_from_request
from django.template.loader import render_to_string
from decimal import Decimal

from apps.orders.forms import CheckoutDetailsForm
from apps.web.models import SiteSettings
from apps.orders.models import Coupon, CouponKind

from apps.favourites.models import WishList, WishListItem


def _get_cart_items_count(cart: Cart) -> int:
    """Total quantity of all products in the cart (sum of line.quantity)."""
    try:
        total = cart.lines.aggregate(total=Sum("quantity")).get("total")
    except Exception:
        total = None
    return int(total or 0)


def _get_vat_rate_percent() -> Decimal:
    try:
        settings_obj = SiteSettings.get_settings()
        return Decimal(settings_obj.vat_rate_percent or 0).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")


# Create your views here.
def cart_page(request):
    cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")

    checkout_details = request.session.get(CHECKOUT_SESSION_KEY) or {}
    # Single-country storefront: no country selection. VAT is store-wide.

    shipping_addresses = []
    if request.user.is_authenticated:
        shipping_addresses = request.user.shipping_addresses.all()

    if not cart_id:
        return render(request, "Cart/cart_page.html", {
            "lines": [],
            "products_count": 0,
            "shipping_addresses": shipping_addresses,
            "checkout_details": checkout_details,
            "total": Decimal("0.00"),
            "subtotal": Decimal("0.00"),
            "tax_total": Decimal("0.00"),
            "discount_total": Decimal("0.00"),
            "delivery_cost": Decimal("0.00"),
            "payment_cost": Decimal("0.00"),
        })

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
                "tax_total": Decimal("0.00"),
                "discount_total": Decimal("0.00"),
                "delivery_cost": Decimal("0.00"),
                "payment_cost": Decimal("0.00"),
            },
        )
        return _clear_cart_id(request, response=response)

    lines = list(cart.lines.select_related("product").all())
    if not lines:
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
                "tax_total": Decimal("0.00"),
                "discount_total": Decimal("0.00"),
                "delivery_cost": Decimal("0.00"),
                "payment_cost": Decimal("0.00"),
            },
        )

    stock_issues = _annotate_lines_with_stock_issues(lines)
    requires_cart_fix = bool(stock_issues)

    request.session["cart_id"] = cart.id

    # Single-country store: always apply store tax rate.
    cart.tax_rate_percent = _get_vat_rate_percent()
    cart.recalculate()

    delivery_cost = cart.delivery_method.get_cost_for_cart(cart.subtotal) if cart.delivery_method else Decimal("0.00")
    payment_cost = (
        cart.payment_method.additional_fees
        if cart.payment_method and cart.payment_method.additional_fees
        else Decimal("0.00")
    )

    shipping_addresses = []
    if request.user.is_authenticated:
        shipping_addresses = request.user.shipping_addresses.all()

    return render(request, "Cart/cart_page.html", {
        "cart": cart,
        "lines": lines,
        "products_count": sum(int(line.quantity or 0) for line in lines),
        "requires_cart_fix": requires_cart_fix,
        "shipping_addresses": shipping_addresses,
        "checkout_details": checkout_details,
        "total": cart.total,
        "subtotal": cart.subtotal,
        "tax_total": cart.tax_total,
        "discount_total": cart.discount_total,
        "delivery_cost": delivery_cost,
        "payment_cost": payment_cost
    })


@require_POST
@login_required
def set_cart_address(request):
    address_id = request.POST.get("address_id")
    if not address_id:
        return JsonResponse({"success": False, "message": _("Address ID required")}, status=400)

    address = get_object_or_404(ShippingAddress, id=address_id, user=request.user)


    # Store in session
    checkout_details = request.session.get(CHECKOUT_SESSION_KEY) or {}
    full_name = (address.full_name or "").strip()
    parts = full_name.split(None, 1)
    first_name = parts[0] if parts else ""
    last_name = parts[1] if len(parts) > 1 else ""
    checkout_details.update({
        "first_name": first_name,
        "last_name": last_name,
        "company": (address.company or "").strip(),
        "phone_country_code": (address.phone_country_code or "+48").strip() or "+48",
        "phone_number": (address.phone_number or "").strip(),
        "email": request.user.email,
        "shipping_city": (address.shipping_city or "").strip(),
        "shipping_postal_code": (address.shipping_postal_code or "").strip(),
        "shipping_street": (address.shipping_street or "").strip(),
        "shipping_building_number": (address.shipping_building_number or "").strip(),
        "shipping_apartment_number": (address.shipping_apartment_number or "").strip(),
    })
    request.session[CHECKOUT_SESSION_KEY] = checkout_details

    # Recalculate cart
    cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")
    if cart_id:
        cart = _get_cart_from_request(request, cart_id)
        if cart:
            cart.tax_rate_percent = _get_vat_rate_percent()
            cart.recalculate()

    return JsonResponse({"success": True})


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
            "tax_total": str(getattr(cart, "tax_total", Decimal("0.00"))),
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
    if not code:
        if wants_json:
            return _json_payload(None, success=False, message=str(_("Please enter a promo code.")), message_type="error", status=400)
        messages.error(request, _("Please enter a promo code."))
        return response

    cart = _get_cart_from_request(request, cart_id)
    if not cart:
        if wants_json:
            return _clear_cart_id(
                request,
                response=_json_payload(None, success=False, message=str(_("Your cart is empty.")), message_type="error", status=400),
            )
        messages.error(request, _("Your cart is empty."))
        return _clear_cart_id(request, response=response)

    if not cart.lines.exists():
        cart.discount_total = Decimal("0.00")
        cart.coupon_code = ""
        cart.recalculate()
        if wants_json:
            return _json_payload(cart, success=False, message=str(_("Your cart is empty.")), message_type="error", status=400)
        messages.error(request, _("Your cart is empty."))
        return response

    now = timezone.now()
    coupon = (
        Coupon.objects.filter(is_active=True, code__iexact=code)
        .order_by("-updated_at")
        .first()
    )

    if not coupon:
        cart.discount_total = Decimal("0.00")
        cart.coupon_code = ""
        cart.recalculate()
        if wants_json:
            return _json_payload(cart, success=False, message=str(_("Invalid promo code.")), message_type="error", status=400)
        messages.error(request, _("Invalid promo code."))
        return response

    if coupon.valid_from and now < coupon.valid_from:
        if wants_json:
            return _json_payload(cart, success=False, message=str(_("This promo code is not active yet.")), message_type="error", status=400)
        messages.error(request, _("This promo code is not active yet."))
        return response
    if coupon.valid_to and now > coupon.valid_to:
        if wants_json:
            return _json_payload(cart, success=False, message=str(_("This promo code has expired.")), message_type="error", status=400)
        messages.error(request, _("This promo code has expired."))
        return response
    if coupon.usage_limit is not None and coupon.used_count >= coupon.usage_limit:
        if wants_json:
            return _json_payload(cart, success=False, message=str(_("This promo code is no longer available.")), message_type="error", status=400)
        messages.error(request, _("This promo code is no longer available."))
        return response

    cart.recalculate()
    if coupon.min_subtotal is not None and cart.subtotal < coupon.min_subtotal:
        msg = _("This promo code requires a minimum subtotal of %(amount)s.") % {"amount": coupon.min_subtotal}
        if wants_json:
            return _json_payload(cart, success=False, message=str(msg), message_type="error", status=400)
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
            "tax_total": str(getattr(cart, "tax_total", Decimal("0.00"))),
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
                response=_json_payload(None, success=True, message=str(_("Promo code removed.")), message_type="success"),
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
    request.session.pop(CHECKOUT_SESSION_KEY, None)

    response = redirect("cart:cart_page")

    if not cart_id:
        return _clear_cart_id(request, response=response)

    cart = _get_cart_from_request(request, cart_id)
    if not cart:
        return _clear_cart_id(request, response=response)

    cart.delete()
    return _clear_cart_id(request, response=response)


@require_POST
def save_as_list(request):
    cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")
    response = redirect("cart:cart_page")

    if not cart_id:
        messages.error(request, "Twój koszyk jest pusty.")
        return response

    cart = _get_cart_from_request(request, cart_id)
    if not cart:
        messages.error(request, "Twój koszyk jest pusty.")
        return _clear_cart_id(request, response=response)

    lines = list(cart.lines.select_related("product").all())
    if not lines:
        messages.error(request, "Twój koszyk jest pusty.")
        return response

    # Ensure anonymous users have a session key for wishlist ownership.
    session_key = request.session.session_key
    if not session_key:
        request.session.save()
        session_key = request.session.session_key

    with transaction.atomic():
        wishlist = WishList.get_or_create_default(
            user=request.user if request.user.is_authenticated else None,
            session_key=None if request.user.is_authenticated else session_key,
        )

        created_count = 0
        for line in lines:
            if not line.product_id:
                continue
            _, created = WishListItem.objects.get_or_create(
                wishlist=wishlist,
                product=line.product,
                defaults={"price_when_added": line.product.price},
            )
            if created:
                created_count += 1

    messages.success(request, f"Dodano {created_count} produktów do ulubionych.")
    return response


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
        line = (
            CartLine.objects.select_for_update()
            .filter(cart=cart, product=product)
            .first()
        )
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

        cart.recalculate()

    request.session["cart_id"] = cart.id

    line_html = render_to_string("Cart/nav_cart_line.html", {"line": line}, request=request)

    delivery_cost = cart.delivery_method.get_cost_for_cart(cart.subtotal) if cart.delivery_method else Decimal("0.00")

    response = JsonResponse({
        "success": True,
        "cart_id": cart.id,
        "cart_total": str(cart.total),
        "cart_subtotal": str(cart.subtotal),
        "tax_total": str(cart.tax_total),
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
    })

    response.set_cookie("cart_id", cart.id, max_age=60*60*24*10)
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
                "tax_total": "0.00",
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
                    "tax_total": "0.00",
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
    cart.recalculate()

    delivery_cost = cart.delivery_method.get_cost_for_cart(cart.subtotal) if cart.delivery_method else Decimal("0.00")


    return JsonResponse({
        "success": True,
        "cart_total": str(cart.total),
        "cart_subtotal": str(cart.subtotal),
        "tax_total": str(cart.tax_total),
        "discount_total": str(cart.discount_total),
        # Total quantity of all products in cart (not number of distinct lines)
        "lines_count": _get_cart_items_count(cart),
        "removed_line_id": line_id,
        "product_name": product_name,
        "delivery_cost": delivery_cost
    })

def checkout_page(request):
    cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")
    if not cart_id:
        return redirect("cart:cart_page")

    cart = _get_cart_from_request(request, cart_id)
    if not cart:
        response = redirect("cart:cart_page")
        return _clear_cart_id(request, response=response)

    lines = list(cart.lines.select_related("product").all())
    stock_issues = _annotate_lines_with_stock_issues(lines)
    if stock_issues:
        return redirect("cart:cart_page")

    checkout_details = request.session.get(CHECKOUT_SESSION_KEY) or {}

    if request.user.is_authenticated and not checkout_details:
        try:
            from apps.users.models import ShippingAddress

            saved = (
                ShippingAddress.objects.filter(user=request.user, is_default=True)
                .order_by("-updated_at", "-id")
                .first()
            ) or (
                ShippingAddress.objects.filter(user=request.user)
                .order_by("-updated_at", "-id")
                .first()
            )
        except Exception:
            saved = None

        if saved:
            full_name = (saved.full_name or "").strip()
            parts = full_name.split(None, 1)
            first_name = parts[0] if parts else ""
            last_name = parts[1] if len(parts) > 1 else ""
            checkout_details = {
                "first_name": first_name,
                "last_name": last_name,
                "company": (saved.company or "").strip(),
                "phone_country_code": (saved.phone_country_code or "+48").strip() or "+48",
                "phone_number": (saved.phone_number or "").strip(),
                "email": request.user.email,
                "shipping_city": (saved.shipping_city or "").strip(),
                "shipping_postal_code": (saved.shipping_postal_code or "").strip(),
                "shipping_street": (saved.shipping_street or "").strip(),
                "shipping_building_number": (saved.shipping_building_number or "").strip(),
                "shipping_apartment_number": (saved.shipping_apartment_number or "").strip(),
            }
            request.session[CHECKOUT_SESSION_KEY] = checkout_details

    cart.tax_rate_percent = _get_vat_rate_percent()
    cart.recalculate()

    delivery_methods = DeliveryMethod.objects.filter(is_active=True)
    payment_methods = PaymentMethod.objects.filter(is_active=True)
    delivery_methods = delivery_methods.order_by("name")
    payment_methods = payment_methods.order_by("name")

    delivery_cost = cart.delivery_method.get_cost_for_cart(cart.subtotal) if cart.delivery_method else Decimal("0.00")
    payment_cost = (
        cart.payment_method.additional_fees
        if cart.payment_method and cart.payment_method.additional_fees
        else Decimal("0.00")
    )

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
        cart.recalculate()

        delivery_cost = cart.delivery_method.get_cost_for_cart(cart.subtotal) if cart.delivery_method else Decimal("0.00")
        payment_cost = (
            cart.payment_method.additional_fees
            if cart.payment_method and cart.payment_method.additional_fees
            else Decimal("0.00")
        )
        
        return JsonResponse({
            "success": True,
            "delivery_method_id": cart.delivery_method.id if cart.delivery_method else None,
            "payment_method_id": cart.payment_method.id if cart.payment_method else None,
            "total": str(cart.total),
            "subtotal": str(cart.subtotal),
            "tax_total": str(cart.tax_total),
            "discount_total": str(cart.discount_total),
            "delivery_cost": str(delivery_cost),
            "payment_cost": str(payment_cost)
        })
    details_form = CheckoutDetailsForm(initial=checkout_details)

    return render(request, "Cart/checkout_page.html", {
        "cart": cart,
        "subtotal": cart.subtotal,
        "tax_total": cart.tax_total,
        "discount_total": cart.discount_total,
        "total": cart.total,
        "disable_cart_dropdown": True,
        "delivery_methods": delivery_methods,
        "selected_delivery": cart.delivery_method,
        "delivery_cost": str(delivery_cost),
        "payment_methods": payment_methods,
        "payment_cost": str(payment_cost),
        "selected_payment": cart.payment_method,
        "details_form": details_form,
        "checkout_details": checkout_details,
    })


@require_POST
def checkout_save_details(request):
    cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")
    if not cart_id:
        return redirect("cart:cart_page")

    cart = _get_cart_from_request(request, cart_id)
    if not cart:
        response = redirect("cart:cart_page")
        return _clear_cart_id(request, response=response)

    lines = list(cart.lines.select_related("product").all())
    stock_issues = _annotate_lines_with_stock_issues(lines)
    if stock_issues:
        return redirect("cart:cart_page")

    mutable = request.POST.copy()
    form = CheckoutDetailsForm(mutable)
    if not form.is_valid():
        # Re-render checkout with errors
        checkout_details = request.session.get(CHECKOUT_SESSION_KEY) or {}

        delivery_methods = DeliveryMethod.objects.filter(is_active=True)
        payment_methods = PaymentMethod.objects.filter(is_active=True)
        delivery_methods = delivery_methods.order_by("name")
        payment_methods = payment_methods.order_by("name")

        delivery_cost = cart.delivery_method.get_cost_for_cart(cart.subtotal) if cart.delivery_method else Decimal("0.00")
        payment_cost = (
            cart.payment_method.additional_fees
            if cart.payment_method and cart.payment_method.additional_fees
            else Decimal("0.00")
        )

        return render(request, "Cart/checkout_page.html", {
            "cart": cart,
            "subtotal": cart.subtotal,
            "tax_total": cart.tax_total,
            "discount_total": cart.discount_total,
            "total": cart.total,
            "disable_cart_dropdown": True,
            "delivery_methods": delivery_methods,
            "selected_delivery": cart.delivery_method,
            "delivery_cost": str(delivery_cost),
            "payment_methods": payment_methods,
            "payment_cost": str(payment_cost),
            "selected_payment": cart.payment_method,
            "details_form": form,
            "checkout_details": request.session.get(CHECKOUT_SESSION_KEY) or {},
        }, status=400)

    # Enforce that delivery/payment are selected.
    if not cart.delivery_method:
        form.add_error(None, _("Please select a delivery method."))

    if not cart.payment_method:
        form.add_error(None, _("Please select a payment method."))

    if form.errors:
        delivery_methods = DeliveryMethod.objects.filter(is_active=True)
        payment_methods = PaymentMethod.objects.filter(is_active=True)
        delivery_methods = delivery_methods.order_by("name")
        payment_methods = payment_methods.order_by("name")

        delivery_cost = cart.delivery_method.get_cost_for_cart(cart.subtotal) if cart.delivery_method else Decimal("0.00")
        payment_cost = (
            cart.payment_method.additional_fees
            if cart.payment_method and cart.payment_method.additional_fees
            else Decimal("0.00")
        )

        return render(request, "Cart/checkout_page.html", {
            "cart": cart,
            "subtotal": cart.subtotal,
            "tax_total": cart.tax_total,
            "discount_total": cart.discount_total,
            "total": cart.total,
            "disable_cart_dropdown": True,
            "delivery_methods": delivery_methods,
            "selected_delivery": cart.delivery_method,
            "delivery_cost": str(delivery_cost),
            "payment_methods": payment_methods,
            "payment_cost": str(payment_cost),
            "selected_payment": cart.payment_method,
            "details_form": form,
            "checkout_details": request.session.get(CHECKOUT_SESSION_KEY) or {},
        }, status=400)

    cart.tax_rate_percent = _get_vat_rate_percent()
    cart.recalculate()

    if request.user.is_authenticated:
        try:
            from apps.users.models import ShippingAddress

            defaults = {
                "full_name": form.get_full_name(),
                "company": form.cleaned_data.get("company", ""),
                "phone_country_code": form.cleaned_data.get("phone_country_code", "+48"),
                "phone_number": form.cleaned_data.get("phone_number", ""),
                "shipping_city": form.cleaned_data.get("shipping_city", ""),
                "shipping_postal_code": form.cleaned_data.get("shipping_postal_code", ""),
                "shipping_street": form.cleaned_data.get("shipping_street", ""),
                "shipping_building_number": form.cleaned_data.get("shipping_building_number", ""),
                "shipping_apartment_number": form.cleaned_data.get("shipping_apartment_number", ""),
            }

            addr = (
                ShippingAddress.objects.filter(user=request.user, is_default=True)
                .order_by("-updated_at", "-id")
                .first()
            )
            if addr:
                for k, v in defaults.items():
                    setattr(addr, k, v)
                addr.is_default = True
                addr.save()
                ShippingAddress.objects.filter(user=request.user).exclude(pk=addr.pk).update(is_default=False)
            else:
                ShippingAddress.objects.filter(user=request.user).update(is_default=False)
                ShippingAddress.objects.create(user=request.user, is_default=True, **defaults)
        except Exception:
            # Best-effort only; checkout must continue.
            pass

    request.session[CHECKOUT_SESSION_KEY] = form.cleaned_data
    return redirect("cart:summary_page")

def summary_page(request):
    cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")
    if not cart_id:
        return redirect("cart:cart_page")

    cart = _get_cart_from_request(request, cart_id)
    if not cart:
        response = redirect("cart:cart_page")
        return _clear_cart_id(request, response=response)

    lines = list(cart.lines.select_related("product").all())
    stock_issues = _annotate_lines_with_stock_issues(lines)
    if stock_issues:
        return redirect("cart:cart_page")

    delivery_cost = cart.delivery_method.get_cost_for_cart(cart.subtotal) if cart.delivery_method else Decimal("0.00")
    delivery_name = cart.delivery_method.name if cart.delivery_method else ""

    payment_cost = (
        cart.payment_method.additional_fees
        if cart.payment_method and cart.payment_method.additional_fees
        else Decimal("0.00")
    )
    payment_name = cart.payment_method.name if cart.payment_method else ""

    checkout_details = request.session.get(CHECKOUT_SESSION_KEY) or {}
    if not checkout_details:
        return redirect("cart:checkout_page")

    cart.tax_rate_percent = _get_vat_rate_percent()
    cart.recalculate()

    return render(request, "Cart/summary_page.html", {
        "cart": cart,
        "lines": lines,
        "subtotal": cart.subtotal,
        "total": cart.total,
        "tax_total": cart.tax_total,
        "discount_total": cart.discount_total,
        "disable_cart_dropdown": True,
        "selected_delivery": cart.delivery_method,
        "delivery_cost": delivery_cost,
        "delivery_name": delivery_name,
        "selected_payment": cart.payment_method,
        "payment_cost": payment_cost,
        "payment_name": payment_name,
        "checkout_details": checkout_details,
        "now": timezone.now(),
    })


