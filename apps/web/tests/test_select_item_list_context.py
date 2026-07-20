"""A product listing must name itself for the LAS tracker's select_item.

GA4 pairs select_item with the list it was picked from, but the tracker's tile-click handler is
global and cannot know which list rendered the card. The listing container carries the identity in
data-las-list-* and the tracker reads it off the clicked tile, so the agent console can answer
"picked from WHICH list?" instead of just naming the product.

The attributes live on the HTMX-swapped container (never a page-level global): switching category
re-renders the partial, so a stale list can never ride along on the next click.
"""

from decimal import Decimal

from django.test import TestCase

from apps.catalog.models import Category, Product, ProductStatus


class TestSelectItemListContext(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="Furniture", slug="furniture")
        cls.product = Product.objects.create(
            name="Colombo Bed",
            slug="colombo-bed",
            price=Decimal("1899.99"),
            category=cls.category,
            status=ProductStatus.ACTIVE,
        )

    def test_category_listing_names_its_list_for_the_tracker(self):
        response = self.client.get(f"/category/{self.category.id}/{self.category.slug}/")

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('data-las-list-name="Furniture"', html)
        self.assertIn('data-las-list-slug="furniture"', html)
        self.assertIn(f'data-las-list-id="{self.category.id}"', html)

    def test_search_results_carry_no_category_list_identity(self):
        # Mirrors track_view_item_list: a category page sends the category payload, while search
        # results are a list without one. Sending the last-browsed category here would misattribute
        # the pick to a category the shopper is not looking at.
        response = self.client.get("/search/", {"q": "bed"})

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("data-las-list-name", response.content.decode())
