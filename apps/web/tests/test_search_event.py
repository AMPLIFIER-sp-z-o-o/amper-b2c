"""The search event must carry results_count so LAS can spot catalog gaps.

LAS classifies a search as "no results" ("Braki w ofercie" / zero-searches) strictly by
``search.results_count == 0``; a payload without the count silently drops real storefront
searches from that report while seeded data still shows up.
"""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from apps.catalog.models import Category, Product, ProductStatus


class TestSearchEventResultsCount(TestCase):
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

    def _search_payloads(self, enqueue_mock):
        return [call.args[1] for call in enqueue_mock.call_args_list if call.args[1]["event_type"] == "search"]

    @patch("apps.live_assisted_sales.events.enqueue_event")
    def test_search_with_hits_carries_results_count(self, enqueue_mock):
        response = self.client.get("/search/", {"q": "bed"})

        self.assertEqual(response.status_code, 200)
        payloads = self._search_payloads(enqueue_mock)
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["search"]["query"], "bed")
        self.assertEqual(payloads[0]["search"]["results_count"], 1)

    @patch("apps.live_assisted_sales.events.enqueue_event")
    def test_zero_result_search_carries_results_count_zero(self, enqueue_mock):
        response = self.client.get("/search/", {"q": "łóżko piętrowe dla dzieci"})

        self.assertEqual(response.status_code, 200)
        payloads = self._search_payloads(enqueue_mock)
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["search"]["results_count"], 0)
