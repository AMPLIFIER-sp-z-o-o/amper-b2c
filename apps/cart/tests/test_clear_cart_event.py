"""Clearing the whole cart must signal LAS that the basket is gone.

Per-item removal already emits cart_item_removed; the "clear cart" path used to delete the cart
silently, so the LAS agent console kept showing the last non-empty basket and a stale intent score.
"""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.cart.models import Cart, CartLine
from apps.catalog.models import Category, Product


class TestClearCartEmitsRemovalEvent(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="Home", slug="home")
        cls.product = Product.objects.create(
            name="Lamp", slug="lamp", price=Decimal("24.00"), category=cls.category
        )

    def _cart_with_item(self):
        cart = Cart.objects.create()
        CartLine.objects.create(cart=cart, product=self.product, quantity=2, price=Decimal("24.00"))
        cart.recalculate()
        session = self.client.session
        session["cart_id"] = cart.id
        session.save()
        return cart

    @patch("apps.live_assisted_sales.events.enqueue_event")
    def test_clear_cart_dispatches_empty_cart_removal(self, enqueue_mock):
        cart = self._cart_with_item()

        response = self.client.post(reverse("cart:clear_cart"))

        # The cart is gone and the shopper is bounced back to the (now empty) cart page.
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Cart.objects.filter(id=cart.id).exists())

        # LAS was told the basket emptied: a cart_item_removed carrying total 0 / no items.
        self.assertTrue(enqueue_mock.called)
        _settings, payload = enqueue_mock.call_args.args
        self.assertEqual(payload["event_type"], "cart_item_removed")
        self.assertEqual(str(payload["cart"].get("total")), "0.00")
        self.assertEqual(payload["cart"].get("items_count"), 0)
        self.assertEqual(payload["cart"].get("items"), [])

    @patch("apps.live_assisted_sales.events.enqueue_event")
    def test_clear_cart_without_cart_does_not_dispatch(self, enqueue_mock):
        # No cart in session → nothing to clear, nothing to signal.
        response = self.client.post(reverse("cart:clear_cart"))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(enqueue_mock.called)
