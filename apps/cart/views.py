from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404
from apps.catalog.models import Product
from .models import Cart, CartLine, DeliveryMethod
from django.template.loader import render_to_string
from decimal import Decimal

# Create your views here.
def cart_page(request):
    cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")

    if not cart_id:
        return render(request, "Cart/cart_page.html", {"lines": [], "total": 0})

    cart = get_object_or_404(Cart, id=cart_id)
    lines = cart.lines.select_related("product").all()

    request.session["cart_id"] = cart.id

    delivery_cost = cart.delivery_method.get_cost_for_cart(cart.subtotal) if cart.delivery_method else Decimal("0.00")

    return render(request, "Cart/cart_page.html", {
        "cart": cart,
        "lines": lines,
        "total": cart.total,
        "subtotal": cart.subtotal,
        "delivery_cost": delivery_cost
    })


@require_POST
def add_to_cart(request):
    product_id = request.POST.get("product_id")
    quantity = int(request.POST.get("quantity", 1))
    cart_id = request.POST.get("cart_id")

    product = get_object_or_404(Product, id=product_id)

    cart = None
    if cart_id:
        cart = Cart.objects.filter(id=cart_id).first()

    if not cart:
        cart = Cart.objects.create(
            customer=request.user if request.user.is_authenticated else None
        )

    line, created = CartLine.objects.get_or_create(
        cart=cart,
        product=product,
        defaults={
            "quantity": quantity,
            "price": product.price,
        }
    )

    if not created:
        line.quantity = quantity
        line.save(update_fields=["quantity"])

    cart.recalculate()
    request.session["cart_id"] = cart.id

    line_html = render_to_string("Cart/nav_cart_line.html", {"line": line})

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
        "line_subtotal": line.subtotal,
        "line_id": line.id,
        "delivery_cost": delivery_cost
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

    cart = get_object_or_404(Cart, id=cart_id)
    delivery_methods = DeliveryMethod.objects.filter(is_active=True).order_by("name")

    delivery_cost = cart.delivery_method.get_cost_for_cart(cart.subtotal) if cart.delivery_method else Decimal("0.00")

    if request.method == "POST":
        method_id = request.POST.get("delivery-method")
        if method_id:
            method = get_object_or_404(DeliveryMethod, id=method_id)
            cart.delivery_method = method
            cart.recalculate()
            cart.save(update_fields=["delivery_method", "subtotal", "total"])
            delivery_cost = cart.delivery_method.get_cost_for_cart(cart.subtotal) if cart.delivery_method else Decimal("0.00")

        return JsonResponse({
            "success": True,
            "delivery_method_id": cart.delivery_method.id if cart.delivery_method else None,
            "total": str(cart.total),
            "subtotal": str(cart.subtotal),
            "delivery_cost": str(delivery_cost)
        })

    return render(request, "Cart/checkout_page.html", {
        "cart": cart,
        "subtotal": cart.subtotal,
        "total": cart.total,
        "disable_cart_dropdown": True,
        "delivery_methods": delivery_methods,
        "selected_delivery": cart.delivery_method,
        "delivery_cost": str(delivery_cost)
    })

def summary_page(request):
    if not request.META.get("HTTP_REFERER"):
        return redirect("cart:cart_page")

    cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")
    if not cart_id:
        return redirect("cart:cart_page")

    cart = get_object_or_404(Cart, id=cart_id)
    lines = cart.lines.select_related("product").all()

    delivery_cost = cart.delivery_method.get_cost_for_cart(cart.subtotal) if cart.delivery_method else Decimal("0.00")
    delivery_name = cart.delivery_method.name

    return render(request, "Cart/summary_page.html", {
        "cart": cart,
        "lines": lines,
        "subtotal": cart.subtotal,
        "total": cart.total,
        "disable_cart_dropdown": True,
        "selected_delivery": cart.delivery_method,
        "delivery_cost": delivery_cost,
        "delivery_name": delivery_name
    })


