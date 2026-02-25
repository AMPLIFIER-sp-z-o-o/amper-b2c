from django.shortcuts import get_object_or_404, render

from apps.web.views import _build_breadcrumb

from .models import Product


def product_detail(request, slug, id):
    product = get_object_or_404(
        Product,
        id=id,
        slug=slug,
    )
    attributes = product.display_attributes
    breadcrumb = _build_breadcrumb(product.category) if product.category else []

    return render(
        request,
        "Catalogs/ProductDetails/product_details.html",
        {"product": product, "attributes": attributes, "breadcrumb": breadcrumb},
    )
