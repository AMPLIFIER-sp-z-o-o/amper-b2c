"""LAS-7 B2 — agent-ready storefront tests (llms.txt, UCP manifest, read-only MCP server)."""

import json

from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product, ProductStatus


class AgentEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="Plecaki", slug="plecaki")
        cls.active = Product.objects.create(
            name="Plecak trekkingowy 40L",
            slug="plecak-trekkingowy-40l",
            category=cls.category,
            status=ProductStatus.ACTIVE,
            price=299,
            stock=5,
            sales_total=20,
            description="<p>Wytrzymały plecak na górskie wyprawy.</p>",
        )
        cls.related = Product.objects.create(
            name="Pokrowiec przeciwdeszczowy",
            slug="pokrowiec-przeciwdeszczowy",
            category=cls.category,
            status=ProductStatus.ACTIVE,
            price=49,
            stock=10,
            sales_total=50,
        )
        cls.hidden = Product.objects.create(
            name="Plecak ukryty",
            slug="plecak-ukryty",
            category=cls.category,
            status=ProductStatus.HIDDEN,
            price=10,
            stock=3,
        )

    def _mcp(self, method, params=None, request_id=1):
        return self.client.post(
            reverse("agent_mcp"),
            data=json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}),
            content_type="application/json",
        )

    # --- discovery surfaces -------------------------------------------------------------------
    def test_llms_txt(self):
        response = self.client.get(reverse("agent_llms_txt"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/plain"))
        body = response.content.decode()
        self.assertIn("/.well-known/ucp.json", body)
        self.assertIn("/api/agent/mcp/", body)

    def test_ucp_manifest(self):
        response = self.client.get(reverse("agent_ucp_manifest"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["capabilities"]["search"])
        # Human-in-the-loop posture: discovery yes, agentic checkout NO.
        self.assertFalse(data["capabilities"]["agentic_checkout"])
        self.assertTrue(data["capabilities"]["human_assisted_checkout"])
        self.assertIn("mcp", data["endpoints"])

    def test_mcp_get_descriptor(self):
        response = self.client.get(reverse("agent_mcp"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["readOnly"])
        self.assertIn("search_products", data["tools"])

    # --- MCP JSON-RPC -------------------------------------------------------------------------
    def test_mcp_initialize(self):
        data = self._mcp("initialize").json()
        self.assertEqual(data["result"]["serverInfo"]["name"], "amper-storefront-mcp")
        self.assertIn("protocolVersion", data["result"])

    def test_mcp_tools_list(self):
        data = self._mcp("tools/list").json()
        names = {tool["name"] for tool in data["result"]["tools"]}
        self.assertEqual(names, {"search_products", "get_product", "related_products"})

    def test_mcp_search_products_returns_visible_only(self):
        data = self._mcp("tools/call", {"name": "search_products", "arguments": {"query": "plecak"}}).json()
        results = data["result"]["structuredContent"]["results"]
        names = {item["name"] for item in results}
        self.assertIn("Plecak trekkingowy 40L", names)
        self.assertNotIn("Plecak ukryty", names)  # hidden products never exposed to agents

    def test_mcp_get_product_by_slug(self):
        data = self._mcp(
            "tools/call", {"name": "get_product", "arguments": {"slug": "plecak-trekkingowy-40l"}}
        ).json()
        product = data["result"]["structuredContent"]["product"]
        self.assertEqual(product["name"], "Plecak trekkingowy 40L")
        self.assertTrue(product["in_stock"])
        self.assertIn("Wytrzymały", product["description"])  # CKEditor HTML stripped to text

    def test_mcp_get_product_missing_is_error(self):
        data = self._mcp("tools/call", {"name": "get_product", "arguments": {"slug": "nope"}}).json()
        self.assertTrue(data["result"]["isError"])

    def test_mcp_related_products_same_category(self):
        data = self._mcp(
            "tools/call", {"name": "related_products", "arguments": {"slug": "plecak-trekkingowy-40l"}}
        ).json()
        names = {item["name"] for item in data["result"]["structuredContent"]["results"]}
        self.assertIn("Pokrowiec przeciwdeszczowy", names)
        self.assertNotIn("Plecak trekkingowy 40L", names)  # never recommends the product itself
        self.assertNotIn("Plecak ukryty", names)

    def test_mcp_unknown_tool(self):
        response = self._mcp("tools/call", {"name": "delete_everything", "arguments": {}})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Unknown tool", response.json()["error"]["message"])

    def test_mcp_unknown_method(self):
        response = self._mcp("catalog/wipe")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], -32601)

    # --- REST search --------------------------------------------------------------------------
    def test_rest_catalog_search(self):
        response = self.client.get(reverse("agent_catalog_search"), {"q": "pokrowiec"})
        self.assertEqual(response.status_code, 200)
        names = {item["name"] for item in response.json()["results"]}
        self.assertIn("Pokrowiec przeciwdeszczowy", names)
