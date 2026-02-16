from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Product, ProductStatus
from .models import Cart, CartLine, DeliveryMethod, PaymentMethod
from django.template.loader import render_to_string
from decimal import Decimal

from apps.orders.forms import CheckoutDetailsForm


CHECKOUT_SESSION_KEY = "checkout_details"


def _clear_cart_id(request, response=None):
    request.session.pop("cart_id", None)
    if response is not None:
        response.delete_cookie("cart_id")
    return response


def _get_cart_from_request(request, cart_id: str | None):
    if not cart_id:
        return None

    cart = Cart.objects.filter(id=cart_id).first()
    if not cart:
        return None

    # If the cart is bound to a user, it must only be accessible by that user.
    if cart.customer_id:
        if not request.user.is_authenticated:
            return None
        if cart.customer_id != request.user.id:
            return None

    return cart


def _annotate_lines_with_stock_issues(lines) -> list[dict]:
    """Annotate cart lines with stock/availability issues for checkout UX.

    Important: this function is read-only and MUST NOT mutate the cart.

    Adds dynamic attributes to each line:
    - line.checkout_stock_issue (bool)
    - line.checkout_stock_available (int)

    Returns a list of issue dicts for optional UI summaries.
    """

    issues: list[dict] = []

    for line in lines:
        product = line.product
        available = int(product.stock or 0)
        is_purchasable = product.status == ProductStatus.ACTIVE and available > 0

        line.checkout_stock_issue = False
        line.checkout_stock_available = available

        if not is_purchasable:
            line.checkout_stock_issue = True
            line.checkout_stock_available = 0
            issues.append(
                {
                    "type": "unavailable",
                    "product_name": product.name,
                    "old_quantity": line.quantity,
                    "available": 0,
                }
            )
            continue

        if line.quantity > available:
            line.checkout_stock_issue = True
            line.checkout_stock_available = available
            issues.append(
                {
                    "type": "exceeds_stock",
                    "product_name": product.name,
                    "old_quantity": line.quantity,
                    "available": available,
                }
            )

    return issues

# Create your views here.
def cart_page(request):
    cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")

    if not cart_id:
        return render(request, "Cart/cart_page.html", {
            "lines": [],
            "total": Decimal("0.00"),
            "subtotal": Decimal("0.00"),
            "delivery_cost": Decimal("0.00"),
            "payment_cost": Decimal("0.00"),
        })

    cart = _get_cart_from_request(request, cart_id)
    if not cart:
        response = render(
            request,
            "Cart/cart_page.html",
            {
                "lines": [],
                "requires_cart_fix": False,
                "total": Decimal("0.00"),
                "subtotal": Decimal("0.00"),
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
                "requires_cart_fix": False,
                "total": Decimal("0.00"),
                "subtotal": Decimal("0.00"),
                "delivery_cost": Decimal("0.00"),
                "payment_cost": Decimal("0.00"),
            },
        )

    stock_issues = _annotate_lines_with_stock_issues(lines)
    requires_cart_fix = bool(stock_issues)

    request.session["cart_id"] = cart.id

    delivery_cost = cart.delivery_method.get_cost_for_cart(cart.subtotal) if cart.delivery_method else Decimal("0.00")
    payment_cost = (
        cart.payment_method.additional_fees
        if cart.payment_method and cart.payment_method.additional_fees
        else Decimal("0.00")
    )

    return render(request, "Cart/cart_page.html", {
        "cart": cart,
        "lines": lines,
        "requires_cart_fix": requires_cart_fix,
        "total": cart.total,
        "subtotal": cart.subtotal,
        "delivery_cost": delivery_cost,
        "payment_cost": payment_cost
    })


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

    # Prevent cross-user cart tampering when a cart is already bound to a user.
    if cart and cart.customer_id:
        if not request.user.is_authenticated:
            return JsonResponse({"success": False, "message": _("Cart not found.")}, status=403)
        if cart.customer_id != request.user.id:
            return JsonResponse({"success": False, "message": _("Cart not found.")}, status=403)

    if not cart:
        cart = Cart.objects.create(
            customer=request.user if request.user.is_authenticated else None
        )

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
        "product_quantity": line.quantity,
        "lines_count": cart.lines.count(),
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

    line = CartLine.objects.filter(
        cart_id=cart_id,
        product_id=product_id
    ).first()

    if not line:
        return JsonResponse({"success": False}, status=404)

    cart = line.cart

    if request.user.is_authenticated:
        if cart.customer_id and cart.customer_id != request.user.id:
            return JsonResponse({"success": False}, status=403)
    elif cart.customer_id:
        return JsonResponse({"success": False}, status=403)

    line_id = line.id
    product_name = line.product.name

    line.delete()
    cart.recalculate()

    delivery_cost = cart.delivery_method.get_cost_for_cart(cart.subtotal) if cart.delivery_method else Decimal("0.00")


    return JsonResponse({
        "success": True,
        "cart_total": str(cart.total),
        "cart_subtotal": str(cart.subtotal),
        "lines_count": cart.lines.count(),
        "removed_line_id": line_id,
        "product_name": product_name,
        "delivery_cost": delivery_cost
    })

def checkout_page(request):
    if not request.META.get("HTTP_REFERER"):
        return redirect("cart:cart_page")
        
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

    delivery_methods = DeliveryMethod.objects.filter(is_active=True).order_by("name")
    delivery_cost = cart.delivery_method.get_cost_for_cart(cart.subtotal) if cart.delivery_method else Decimal("0.00")

    payment_methods = PaymentMethod.objects.filter(is_active=True).order_by("name")
    payment_cost = (
        cart.payment_method.additional_fees
        if cart.payment_method and cart.payment_method.additional_fees
        else Decimal("0.00")
    )

    if request.method == "POST":
        method_id = request.POST.get("delivery-method")
        payment_id = request.POST.get("payment-method")
        if method_id:
            method = get_object_or_404(DeliveryMethod, id=method_id)
            cart.delivery_method = method

        if payment_id:
            payment = get_object_or_404(PaymentMethod, id=payment_id)
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
            "delivery_cost": str(delivery_cost),
            "payment_cost": str(payment_cost)
        })

    checkout_details = request.session.get(CHECKOUT_SESSION_KEY) or {}
    details_form = CheckoutDetailsForm(initial=checkout_details)

    return render(request, "Cart/checkout_page.html", {
        "cart": cart,
        "subtotal": cart.subtotal,
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

    form = CheckoutDetailsForm(request.POST)
    if not form.is_valid():
        # Re-render checkout with errors
        delivery_methods = DeliveryMethod.objects.filter(is_active=True).order_by("name")
        payment_methods = PaymentMethod.objects.filter(is_active=True).order_by("name")

        delivery_cost = cart.delivery_method.get_cost_for_cart(cart.subtotal) if cart.delivery_method else Decimal("0.00")
        payment_cost = (
            cart.payment_method.additional_fees
            if cart.payment_method and cart.payment_method.additional_fees
            else Decimal("0.00")
        )

        return render(request, "Cart/checkout_page.html", {
            "cart": cart,
            "subtotal": cart.subtotal,
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

    request.session[CHECKOUT_SESSION_KEY] = form.cleaned_data
    return redirect("cart:summary_page")

def summary_page(request):
    if not request.META.get("HTTP_REFERER"):
        return redirect("cart:cart_page")

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

    return render(request, "Cart/summary_page.html", {
        "cart": cart,
        "lines": lines,
        "subtotal": cart.subtotal,
        "total": cart.total,
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


