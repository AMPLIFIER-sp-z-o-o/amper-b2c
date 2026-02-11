from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404
from apps.catalog.models import Product
from .models import Cart, CartLine
from django.template.loader import render_to_string

# Create your views here.
def cart_page(request):
    cart_id = request.session.get("cart_id") or request.COOKIES.get("cart_id")

    if not cart_id:
        return render(request, "Cart/cart_page.html", {"lines": [], "total": 0})

    cart = get_object_or_404(Cart, id=cart_id)
    lines = cart.lines.select_related("product").all()

    request.session["cart_id"] = cart.id

    return render(request, "Cart/cart_page.html", {
        "cart": cart,
        "lines": lines,
        "total": cart.total,
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

    response = JsonResponse({
        "success": True,
        "cart_id": cart.id,
        "cart_total": str(cart.total),
        "product_quantity": line.quantity,
        "lines_count": cart.lines.count(),
        "updated_line_html": line_html,
        "product_name": product.name,
        "line_subtotal": line.subtotal,
        "line_id": line.id
    })

    response.set_cookie("cart_id", cart.id, max_age=60*60*24*10)
    return response


@require_POST
def remove_from_cart(request):
    product_id = request.POST.get("product_id")
    cart_id = request.session.get("cart_id")

    if not product_id:
        return JsonResponse({"success": False}, status=400)

    line = CartLine.objects.filter(
        cart_id=cart_id,
        product_id=product_id
    ).first()

    lineId = line.id
    productName = line.product.name

    if not line:
        return JsonResponse({"success": False}, status=404)

    cart = line.cart

    if request.user.is_authenticated:
        if cart.customer != request.user:
            return JsonResponse({"success": False}, status=403)
    else:
        if request.session.get("cart_id") != cart.id:
            return JsonResponse({"success": False}, status=403)

    line.delete()
    cart.recalculate()

    return JsonResponse({
        "success": True,
        "cart_total": str(cart.total),
        "lines_count": cart.lines.count(),
        "removed_line_id": lineId,
        "product_name": productName
    })



