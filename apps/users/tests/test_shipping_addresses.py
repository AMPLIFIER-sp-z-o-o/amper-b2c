from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.cart.models import Cart, DeliveryMethod, PaymentMethod
from apps.catalog.models import Category, Product, ProductStatus
from apps.users.models import ShippingAddress


@pytest.mark.django_db
def test_checkout_save_details_persists_default_shipping_address_for_logged_in_user(client):
    User = get_user_model()
    user = User.objects.create_user(
        username="u1",
        email="u1@example.com",
        first_name="User",
        password="pass",
    )
    client.force_login(user)

    delivery = DeliveryMethod.objects.create(name="D", price=Decimal("0.00"), delivery_time=0, is_active=True)
    payment = PaymentMethod.objects.create(name="P", additional_fees=Decimal("0.00"), is_active=True)

    category = Category.objects.create(name="Test")
    product = Product.objects.create(
        name="P",
        category=category,
        status=ProductStatus.ACTIVE,
        price=Decimal("10.00"),
        stock=10,
    )

    cart = Cart.objects.create(customer=user, delivery_method=delivery, payment_method=payment)
    cart.lines.create(product=product, quantity=1, price=product.price)
    cart.recalculate()

    session = client.session
    session["cart_id"] = cart.id
    session.save()

    res = client.post(
        reverse("cart:checkout_save_details"),
        {
            "first_name": "John",
            "last_name": "Doe",
            "company": "",
            "phone_country_code": "+48",
            "phone_number": "123",
            "email": "john@example.com",
            "shipping_city": "Warsaw",
            "shipping_postal_code": "00-001",
            "shipping_street": "Test",
            "shipping_building_number": "1",
            "shipping_apartment_number": "",
        },
        follow=False,
    )

    assert res.status_code == 302
    addr = ShippingAddress.objects.get(user=user, is_default=True)
    assert addr.full_name == "John Doe"
    assert addr.phone_country_code == "+48"
    assert addr.phone_number == "123"
    assert addr.shipping_postal_code == "00-001"
    assert addr.shipping_city == "Warsaw"
    assert addr.shipping_street == "Test"
    assert addr.shipping_building_number == "1"
    assert addr.shipping_apartment_number == ""


@pytest.mark.django_db
def test_checkout_page_prefills_details_from_default_shipping_address_when_session_empty(client):
    User = get_user_model()
    user = User.objects.create_user(
        username="u2",
        email="u2@example.com",
        first_name="User",
        password="pass",
    )
    client.force_login(user)

    delivery = DeliveryMethod.objects.create(name="D", price=Decimal("0.00"), delivery_time=0, is_active=True)
    payment = PaymentMethod.objects.create(name="P", additional_fees=Decimal("0.00"), is_active=True)

    category = Category.objects.create(name="Test")
    product = Product.objects.create(
        name="P",
        category=category,
        status=ProductStatus.ACTIVE,
        price=Decimal("10.00"),
        stock=10,
    )

    cart = Cart.objects.create(customer=user, delivery_method=delivery, payment_method=payment)
    cart.lines.create(product=product, quantity=1, price=product.price)
    cart.recalculate()

    ShippingAddress.objects.create(
        user=user,
        is_default=True,
        full_name="Jane Doe",
        company="ACME",
        phone_country_code="+48",
        phone_number="999",
        shipping_city="Berlin",
        shipping_postal_code="00-002",
        shipping_street="Street",
        shipping_building_number="1",
        shipping_apartment_number="",
    )

    session = client.session
    session["cart_id"] = cart.id
    session.pop("checkout_details", None)
    session.save()

    res = client.get(reverse("cart:checkout_page"))
    assert res.status_code == 200

    session = client.session
    details = session.get("checkout_details") or {}
    assert details.get("first_name") == "Jane"
    assert details.get("last_name") == "Doe"
    assert details.get("company") == "ACME"
    assert details.get("email") == "u2@example.com"
    assert details.get("phone_country_code") == "+48"
    assert details.get("phone_number") == "999"
    assert details.get("shipping_city") == "Berlin"
    assert details.get("shipping_postal_code") == "00-002"
    assert details.get("shipping_street") == "Street"
    assert details.get("shipping_building_number") == "1"
