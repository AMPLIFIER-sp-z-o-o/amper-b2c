import json
from io import BytesIO
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, SimpleTestCase, TestCase

from apps.web.models import SiteSettings

from .admin import LiveAssistedSalesSettingsForm
from .client import run_settings_connection_test, send_event
from .events import build_event_payload, cart_payload, category_payload, dispatch_event, product_payload
from .models import LiveAssistedSalesSettings


class LiveAssistedSalesSettingsAdminFormTests(SimpleTestCase):
    def test_admin_settings_form_prevents_credential_autofill(self):
        form = LiveAssistedSalesSettingsForm()

        self.assertEqual(form.fields["las_base_url"].widget.attrs["autocomplete"], "off")
        self.assertEqual(form.fields["las_base_url"].widget.attrs["data-lpignore"], "true")
        self.assertEqual(form.fields["las_base_url"].widget.attrs["data-1p-ignore"], "true")
        self.assertEqual(form.fields["store_api_key"].widget.attrs["autocomplete"], "new-password")
        self.assertEqual(form.fields["store_api_key"].widget.attrs["data-lpignore"], "true")
        self.assertEqual(form.fields["store_api_key"].widget.attrs["data-1p-ignore"], "true")


class LiveAssistedSalesSettingsTests(TestCase):
    def setUp(self):
        LiveAssistedSalesSettings.objects.all().delete()

    @patch("apps.live_assisted_sales.client.LiveAssistedSalesClient.test_connection")
    def test_connection_success_updates_settings_without_exposing_key(self, test_connection_mock):
        test_connection_mock.return_value = (200, {"store": {"display_name": "Zielony Koszyk"}})
        settings_obj = LiveAssistedSalesSettings.objects.create(
            enabled=True,
            las_base_url="http://localhost:8001",
            store_api_key="site_sk_secret",
        )

        ok, message = run_settings_connection_test(settings_obj)

        settings_obj.refresh_from_db()
        self.assertTrue(ok)
        self.assertEqual(settings_obj.last_test_status, "success")
        self.assertIn("Zielony Koszyk", message)
        self.assertIn("works correctly", message)
        self.assertNotIn("site_sk_secret", message)

    @patch("apps.live_assisted_sales.client.LiveAssistedSalesClient.test_connection")
    def test_connection_failure_updates_settings(self, test_connection_mock):
        test_connection_mock.side_effect = OSError("network down")
        settings_obj = LiveAssistedSalesSettings.objects.create(
            enabled=True,
            las_base_url="http://localhost:8001",
            store_api_key="site_sk_secret",
        )

        ok, message = run_settings_connection_test(settings_obj)

        settings_obj.refresh_from_db()
        self.assertFalse(ok)
        self.assertEqual(settings_obj.last_test_status, "failed")
        self.assertIn("LAS connection failed", message)

    @patch("apps.live_assisted_sales.client.LiveAssistedSalesClient.test_connection")
    def test_connection_rejected_key_uses_las_error_detail_without_exposing_key(self, test_connection_mock):
        test_connection_mock.side_effect = HTTPError(
            url="http://localhost:8001/api/ingest/store-events/test/",
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=BytesIO(b'{"detail":"Invalid store API key."}'),
        )
        settings_obj = LiveAssistedSalesSettings.objects.create(
            enabled=True,
            las_base_url="http://localhost:8001",
            store_api_key="site_sk_secret",
        )

        ok, message = run_settings_connection_test(settings_obj)

        settings_obj.refresh_from_db()
        self.assertFalse(ok)
        self.assertEqual(settings_obj.last_test_status, "failed")
        self.assertIn("API key (HTTP 403)", message)
        self.assertIn("Invalid store API key", message)
        self.assertNotIn("site_sk_secret", message)

    @patch("apps.live_assisted_sales.client.LiveAssistedSalesClient.send_event")
    def test_send_event_logs_timeout_without_traceback(self, send_event_mock):
        send_event_mock.side_effect = TimeoutError("timed out")
        settings_obj = LiveAssistedSalesSettings.objects.create(
            enabled=True,
            las_base_url="http://localhost:8001",
            store_api_key="site_sk_secret",
        )

        with self.assertLogs("apps.live_assisted_sales.client", level="WARNING") as logs:
            result = send_event(settings_obj, {"event_type": "search"})

        self.assertFalse(result)
        self.assertIn("Live Assisted Sales event dispatch failed: timed out", logs.output[0])
        self.assertNotIn("Traceback", "\n".join(logs.output))


class BrowserEventEndpointTests(TestCase):
    def setUp(self):
        LiveAssistedSalesSettings.objects.all().delete()
        self.client = Client()

    def configure(self, **kwargs):
        settings_obj = LiveAssistedSalesSettings.get_solo()
        for field, value in kwargs.items():
            setattr(settings_obj, field, value)
        settings_obj.save()
        return settings_obj

    def test_disabled_adapter_accepts_event_without_sending(self):
        self.configure(enabled=False)

        with patch("apps.live_assisted_sales.views.enqueue_event") as enqueue_mock:
            response = self.client.post(
                "/live-assisted-sales/events/",
                data=json.dumps({"event_type": "search", "search": {"query": "demo"}}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sent"], 0)
        enqueue_mock.assert_not_called()

    @patch("apps.live_assisted_sales.views.enqueue_event")
    def test_browser_endpoint_accepts_single_event_and_does_not_return_api_key(self, enqueue_mock):
        enqueue_mock.return_value = True
        self.configure(
            enabled=True,
            las_base_url="http://localhost:8001",
            store_api_key="site_sk_secret",
        )

        response = self.client.post(
            "/live-assisted-sales/events/",
            data=json.dumps(
                {
                    "event_type": "search",
                    "visitor_id": "visitor-1",
                    "session_id": "session-1",
                    "search": {"query": "chemex"},
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sent"], 1)
        self.assertNotIn("site_sk_secret", response.content.decode())
        payload = enqueue_mock.call_args.args[1]
        self.assertEqual(payload["event_type"], "search")
        self.assertNotIn("store_api_key", payload)
        self.assertEqual(payload["metadata"]["user"]["status"], "anonymous")

    @patch("apps.live_assisted_sales.views.enqueue_event")
    def test_browser_endpoint_rejects_cart_snapshot_events(self, enqueue_mock):
        enqueue_mock.return_value = True
        self.configure(
            enabled=True,
            las_base_url="http://localhost:8001",
            store_api_key="site_sk_secret",
        )

        response = self.client.post(
            "/live-assisted-sales/events/",
            data=json.dumps(
                {
                    "events": [
                        {"event_type": "cart_snapshot", "cart": {"items_count": 2, "total": "99.00"}},
                    ]
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["sent"], 0)
        enqueue_mock.assert_not_called()

    @patch("apps.live_assisted_sales.views.enqueue_event")
    def test_browser_endpoint_accepts_session_end_event(self, enqueue_mock):
        enqueue_mock.return_value = True
        self.configure(
            enabled=True,
            las_base_url="http://localhost:8001",
            store_api_key="site_sk_secret",
        )

        response = self.client.post(
            "/live-assisted-sales/events/",
            data=json.dumps(
                {
                    "event_type": "session_end",
                    "visitor_id": "visitor-1",
                    "session_id": "session-1",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sent"], 1)
        payload = enqueue_mock.call_args.args[1]
        self.assertEqual(payload["event_type"], "session_end")
        self.assertEqual(payload["visitor_id"], "visitor-1")
        self.assertEqual(payload["session_id"], "session-1")

    @patch("apps.live_assisted_sales.views.enqueue_event")
    def test_browser_endpoint_accepts_session_start_event(self, enqueue_mock):
        enqueue_mock.return_value = True
        self.configure(
            enabled=True,
            las_base_url="http://localhost:8001",
            store_api_key="site_sk_secret",
        )

        response = self.client.post(
            "/live-assisted-sales/events/",
            data=json.dumps(
                {
                    "event_type": "session_start",
                    "visitor_id": "visitor-1",
                    "session_id": "session-1",
                    "page": {"title": "Homepage", "path": "/"},
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sent"], 1)
        payload = enqueue_mock.call_args.args[1]
        self.assertEqual(payload["event_type"], "session_start")
        self.assertEqual(payload["page"]["title"], "Homepage")

    @patch("apps.live_assisted_sales.views.enqueue_event")
    def test_browser_endpoint_marks_logged_in_user_without_returning_api_key(self, enqueue_mock):
        enqueue_mock.return_value = True
        self.configure(
            enabled=True,
            las_base_url="http://localhost:8001",
            store_api_key="site_sk_secret",
        )
        user = get_user_model().objects.create_user(username="shopper@example.com", password="pass")
        self.client.force_login(user)

        response = self.client.post(
            "/live-assisted-sales/events/",
            data=json.dumps({"event_type": "product_view", "product": {"id": "p1", "name": "Chemex"}}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = enqueue_mock.call_args.args[1]
        self.assertEqual(payload["metadata"]["user"]["status"], "authenticated")
        self.assertEqual(payload["metadata"]["user"]["display"], "shopper@example.com")
        self.assertEqual(payload["metadata"]["user"]["email"], "shopper@example.com")
        self.assertNotIn("site_sk_secret", response.content.decode())

    @patch("apps.live_assisted_sales.views.enqueue_event")
    def test_browser_endpoint_accepts_batch_and_rejects_invalid_event(self, enqueue_mock):
        enqueue_mock.return_value = True
        self.configure(enabled=True, las_base_url="http://localhost:8001", store_api_key="key")

        response = self.client.post(
            "/live-assisted-sales/events/",
            data=json.dumps(
                {"events": [{"event_type": "search", "search": {"query": "tea"}}, {"event_type": "page_view"}]}
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["sent"], 1)
        self.assertEqual(enqueue_mock.call_count, 1)

    @patch("apps.live_assisted_sales.views.enqueue_event")
    def test_browser_endpoint_enabled_but_not_configured_is_noop(self, enqueue_mock):
        self.configure(enabled=True, las_base_url="", store_api_key="")

        response = self.client.post(
            "/live-assisted-sales/events/",
            data=json.dumps({"event_type": "search", "search": {"query": "tea"}}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sent"], 0)
        enqueue_mock.assert_not_called()

    @patch("apps.live_assisted_sales.views.enqueue_event")
    def test_browser_endpoint_reports_queue_failure(self, enqueue_mock):
        enqueue_mock.return_value = False
        self.configure(enabled=True, las_base_url="http://localhost:8001", store_api_key="key")

        response = self.client.post(
            "/live-assisted-sales/events/",
            data=json.dumps({"event_type": "search", "search": {"query": "tea"}}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["sent"], 0)
        self.assertIn("could not be queued", response.json()["errors"][0])

    def test_browser_endpoint_rejects_bad_json(self):
        self.configure(enabled=True, las_base_url="http://localhost:8001", store_api_key="key")

        response = self.client.post(
            "/live-assisted-sales/events/",
            data="{",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_browser_endpoint_rejects_cross_origin_request(self):
        self.configure(enabled=True, las_base_url="http://localhost:8001", store_api_key="key")

        response = self.client.post(
            "/live-assisted-sales/events/",
            data=json.dumps({"event_type": "search", "search": {"query": "tea"}}),
            content_type="application/json",
            HTTP_ORIGIN="https://attacker.example",
            HTTP_HOST="testserver",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["ok"])

    def test_browser_endpoint_rejects_oversized_payload(self):
        self.configure(enabled=True, las_base_url="http://localhost:8001", store_api_key="key")

        response = self.client.post(
            "/live-assisted-sales/events/",
            data=b'{"metadata":"' + (b"x" * (33 * 1024)) + b'"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 413)
        self.assertFalse(response.json()["ok"])


class EventBuilderTests(TestCase):
    def setUp(self):
        LiveAssistedSalesSettings.objects.all().delete()

    def configure(self, **kwargs):
        settings_obj = LiveAssistedSalesSettings.get_solo()
        for field, value in kwargs.items():
            setattr(settings_obj, field, value)
        settings_obj.save()
        return settings_obj

    def test_build_event_payload_generates_required_ids(self):
        request = RequestFactory().get("/products/demo/")
        request.session = Mock()
        request.session.session_key = "session-1"

        payload = build_event_payload(request, "product_view", page={"title": "Demo"})

        self.assertEqual(payload["event_type"], "product_view")
        self.assertEqual(payload["session_id"], "session-1")
        self.assertEqual(payload["page"]["title"], "Demo")
        self.assertNotIn("store_api_key", payload)

    def test_build_event_payload_uses_tracker_cookies_for_anonymous_identity(self):
        request = RequestFactory().get(
            "/products/demo/",
            HTTP_COOKIE="las_visitor_id=visitor-cookie; las_session_id=session-cookie",
        )
        request.session = Mock()
        request.session.session_key = None

        payload = build_event_payload(request, "product_view")

        self.assertEqual(payload["visitor_id"], "visitor-cookie")
        self.assertEqual(payload["session_id"], "session-cookie")

    def test_build_event_payload_does_not_trust_browser_user_metadata(self):
        request = RequestFactory().get("/")
        request.session = Mock()
        request.session.session_key = "session-1"

        payload = build_event_payload(
            request,
            "product_view",
            metadata={"user": {"status": "authenticated", "display": "forged@example.com"}},
        )

        self.assertEqual(payload["metadata"]["user"]["status"], "anonymous")
        self.assertNotIn("forged@example.com", str(payload))

    @patch("apps.live_assisted_sales.events.enqueue_event")
    def test_las_dispatch_errors_do_not_escape_business_flow(self, enqueue_mock):
        enqueue_mock.side_effect = RuntimeError("LAS down")
        self.configure(
            enabled=True,
            las_base_url="http://localhost:8001",
            store_api_key="key",
        )
        request = RequestFactory().get("/")
        request.session = Mock()
        request.session.session_key = "session-1"

        self.assertFalse(dispatch_event(request, "search"))

    def test_server_tracking_does_not_create_session(self):
        request = RequestFactory().get("/")
        request.session = Mock()
        request.session.session_key = None

        payload = build_event_payload(request, "product_view")

        request.session.save.assert_not_called()
        self.assertTrue(payload["visitor_id"].startswith("visitor-"))
        self.assertTrue(payload["session_id"].startswith("session-"))

    def test_cart_payload_uses_site_settings_currency(self):
        settings_obj = SiteSettings.get_settings()
        settings_obj.currency = SiteSettings.Currency.EUR
        settings_obj.save(update_fields=["currency"])

        cart = Mock()
        cart.total = "123.45"
        cart.lines.select_related.return_value.all.return_value = []

        payload = cart_payload(cart)

        self.assertEqual(payload["currency"], "EUR")
        self.assertEqual(payload["total"], "123.45")
        self.assertEqual(payload["total_display"], "123,45 €")

    def test_product_and_category_payloads_use_absolute_business_urls(self):
        request = RequestFactory().get("/")
        product = Mock(id=42, name="Chemex", sku="CHEMEX-1")
        product.get_absolute_url.return_value = "/products/42-chemex/"
        category = Mock(id=7, name="Brewers", slug="brewers")
        category.get_absolute_url.return_value = "/category/7-brewers/"

        self.assertEqual(product_payload(product, request=request)["url"], "http://testserver/products/42-chemex/")
        self.assertEqual(category_payload(category, request=request)["url"], "http://testserver/category/7-brewers/")

    def test_cart_payload_includes_product_business_identifiers_and_links(self):
        request = RequestFactory().get("/")
        product = Mock(id=42, name="Chemex", sku="CHEMEX-1")
        product.get_absolute_url.return_value = "/products/42-chemex/"
        line = Mock(product_id=42, product=product, quantity=2, price="12.50")
        line.subtotal = "25.00"
        cart = Mock(total="25.00")
        cart.lines.select_related.return_value.all.return_value = [line]

        payload = cart_payload(cart, request=request)

        self.assertEqual(payload["items_count"], 2)
        self.assertEqual(payload["items"][0]["sku"], "CHEMEX-1")
        self.assertEqual(payload["items"][0]["url"], "http://testserver/products/42-chemex/")
        self.assertEqual(payload["items"][0]["line_total"], "25.00")
