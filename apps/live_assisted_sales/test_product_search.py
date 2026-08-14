"""Product search this storefront answers for the LAS agent picker (2026-08-13).

The endpoint is reachable from the internet and reads the catalogue, so the tests concentrate on
who is allowed to ask (signature, freshness, integration switch) and on what may come back (only
storefront-visible products, correct availability).
"""

import hashlib
import hmac
import json
import time
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.catalog.models import Category, Product, ProductStatus

from .models import LiveAssistedSalesSettings
from .search import search_endpoint_url

API_KEY = "test-store-api-key"


def sign(body, timestamp, secret=API_KEY):
    payload = f"{timestamp}.".encode() + body
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


class ProductSearchEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="Napoje", slug="napoje")
        cls.visible = Product.objects.create(
            name="Pepsi 24x0,5L",
            slug="pepsi-24x05l",
            category=cls.category,
            status=ProductStatus.ACTIVE,
            price=119,
            stock=12,
        )
        cls.sold_out = Product.objects.create(
            name="Pepsi Max 1,5L",
            slug="pepsi-max-15l",
            category=cls.category,
            status=ProductStatus.ACTIVE,
            price=7,
            stock=0,
        )
        cls.hidden = Product.objects.create(
            name="Pepsi tajna edycja",
            slug="pepsi-tajna",
            category=cls.category,
            status=ProductStatus.HIDDEN,
            price=9,
            stock=5,
        )

    def setUp(self):
        self.client = Client()
        self.url = reverse("live_assisted_sales:product-search")
        settings_obj = LiveAssistedSalesSettings.get_solo()
        settings_obj.enabled = True
        settings_obj.store_api_key = API_KEY
        settings_obj.save()

    def post(self, payload, *, secret=API_KEY, timestamp=None, signature=None, omit_headers=False):
        body = json.dumps(payload).encode("utf-8")
        timestamp = timestamp if timestamp is not None else str(int(time.time()))
        headers = {}
        if not omit_headers:
            headers = {
                "HTTP_X_AMPER_TIMESTAMP": timestamp,
                "HTTP_X_AMPER_SIGNATURE": signature or sign(body, timestamp, secret),
            }
        return self.client.post(self.url, data=body, content_type="application/json", **headers)

    def test_signed_request_returns_visible_products(self):
        response = self.post({"query": "pepsi", "limit": 10})
        self.assertEqual(response.status_code, 200)
        names = [row["name"] for row in response.json()["results"]]
        self.assertIn("Pepsi 24x0,5L", names)
        self.assertIn("Pepsi Max 1,5L", names)
        # A hidden product must never reach an agent's picker - they could send it into a chat.
        self.assertNotIn("Pepsi tajna edycja", names)

    def test_availability_reflects_stock(self):
        results = {row["name"]: row for row in self.post({"query": "pepsi"}).json()["results"]}
        self.assertEqual(results["Pepsi 24x0,5L"]["availability"], "in_stock")
        self.assertEqual(results["Pepsi Max 1,5L"]["availability"], "out_of_stock")

    def test_card_carries_what_the_shopper_card_needs(self):
        row = next(r for r in self.post({"query": "24x0,5"}).json()["results"] if r["name"].startswith("Pepsi 24"))
        self.assertTrue(row["id"])
        self.assertTrue(row["url"].startswith("http"))
        # A formatted price, not a bare number - the card shows it verbatim.
        self.assertTrue(row["price"])

    def test_unsigned_request_is_refused(self):
        self.assertEqual(self.post({"query": "pepsi"}, omit_headers=True).status_code, 403)

    def test_wrong_key_is_refused(self):
        self.assertEqual(self.post({"query": "pepsi"}, secret="not-the-key").status_code, 403)

    def test_tampered_body_is_refused(self):
        # Sign one body, send another: the signature covers the payload, so this must not pass.
        body = json.dumps({"query": "pepsi"}).encode("utf-8")
        timestamp = str(int(time.time()))
        response = self.client.post(
            self.url,
            data=json.dumps({"query": "whisky"}).encode("utf-8"),
            content_type="application/json",
            HTTP_X_AMPER_TIMESTAMP=timestamp,
            HTTP_X_AMPER_SIGNATURE=sign(body, timestamp),
        )
        self.assertEqual(response.status_code, 403)

    def test_replayed_old_request_is_refused(self):
        stale = str(int(time.time()) - 3600)
        self.assertEqual(self.post({"query": "pepsi"}, timestamp=stale).status_code, 403)

    def test_future_timestamp_is_refused(self):
        ahead = str(int(time.time()) + 3600)
        self.assertEqual(self.post({"query": "pepsi"}, timestamp=ahead).status_code, 403)

    def test_non_numeric_timestamp_is_refused(self):
        self.assertEqual(self.post({"query": "pepsi"}, timestamp="not-a-number").status_code, 403)

    def test_disabled_integration_answers_nothing(self):
        settings_obj = LiveAssistedSalesSettings.get_solo()
        settings_obj.enabled = False
        settings_obj.save()
        self.assertEqual(self.post({"query": "pepsi"}).status_code, 403)

    def test_unconfigured_store_key_refuses_even_a_signed_request(self):
        # Without a shared secret there is nothing to verify against; the catalogue must stay shut.
        settings_obj = LiveAssistedSalesSettings.get_solo()
        settings_obj.store_api_key = ""
        settings_obj.save()
        self.assertEqual(self.post({"query": "pepsi"}, secret="").status_code, 403)

    def test_invalid_json_is_a_bad_request(self):
        timestamp = str(int(time.time()))
        body = b"{not json"
        response = self.client.post(
            self.url,
            data=body,
            content_type="application/json",
            HTTP_X_AMPER_TIMESTAMP=timestamp,
            HTTP_X_AMPER_SIGNATURE=sign(body, timestamp),
        )
        self.assertEqual(response.status_code, 400)

    def test_blank_query_returns_no_results_rather_than_the_whole_catalogue(self):
        self.assertEqual(self.post({"query": "   "}).json()["results"], [])

    def test_limit_is_capped(self):
        for index in range(30):
            Product.objects.create(
                name=f"Pepsi wariant {index}",
                slug=f"pepsi-wariant-{index}",
                category=self.category,
                status=ProductStatus.ACTIVE,
                price=5,
                stock=1,
            )
        self.assertLessEqual(len(self.post({"query": "pepsi", "limit": 500}).json()["results"]), 24)

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)


class SearchEndpointUrlTests(TestCase):
    @override_settings(FRONTEND_ADDRESS="https://sklep.example.test")
    def test_falls_back_to_the_deployment_address(self):
        self.assertEqual(
            search_endpoint_url(),
            "https://sklep.example.test/live-assisted-sales/product-search/",
        )

    @override_settings(FRONTEND_ADDRESS="")
    def test_without_any_address_nothing_is_announced(self):
        # Announcing a relative or empty URL would have LAS store an address it can never call.
        self.assertEqual(search_endpoint_url(), "")


class AnnounceCapabilitiesTests(TestCase):
    def test_a_failed_announcement_never_fails_the_connection_test(self):
        from .client import _announce_product_search

        settings_obj = LiveAssistedSalesSettings.get_solo()
        settings_obj.store_api_key = API_KEY
        settings_obj.save()
        with patch(
            "apps.live_assisted_sales.client.LiveAssistedSalesClient.announce_capabilities",
            side_effect=OSError("LAS is down"),
        ):
            # Must not raise: the picker degrades to its observed catalogue instead.
            _announce_product_search(settings_obj, "http://las.example.test/")
