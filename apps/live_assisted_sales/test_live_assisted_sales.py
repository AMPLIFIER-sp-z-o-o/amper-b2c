import hashlib
import hmac
import json
import time
from io import BytesIO
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import Client, RequestFactory, SimpleTestCase, TestCase

from apps.web.models import SiteSettings

from .admin import LiveAssistedSalesSettingsForm
from .client import run_settings_connection_test, send_event
from .context_processors import live_assisted_sales
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
        test_connection_mock.return_value = (
            200,
            {"store": {"display_name": "Zielony Koszyk", "public_key": "site_pk_live"}},
        )
        settings_obj = LiveAssistedSalesSettings.objects.create(
            enabled=True,
            las_base_url="http://localhost:8001",
            store_api_key="site_sk_secret",
            site_public_key="site_pk_stale",
        )

        ok, message = run_settings_connection_test(settings_obj)

        settings_obj.refresh_from_db()
        self.assertTrue(ok)
        self.assertEqual(settings_obj.last_test_status, "success")
        self.assertEqual(settings_obj.site_public_key, "site_pk_live")
        self.assertIn("Zielony Koszyk", message)
        self.assertIn("works correctly", message)
        self.assertNotIn("site_sk_secret", message)

    @patch("apps.live_assisted_sales.client.LiveAssistedSalesClient.test_connection")
    def test_connection_success_without_public_key_keeps_widget_disabled(self, test_connection_mock):
        test_connection_mock.return_value = (200, {"store": {"display_name": "Zielony Koszyk"}})
        settings_obj = LiveAssistedSalesSettings.objects.create(
            enabled=True,
            las_base_url="http://localhost:8001",
            store_api_key="site_sk_secret",
            site_public_key="site_pk_stale",
        )

        ok, _message = run_settings_connection_test(settings_obj)

        settings_obj.refresh_from_db()
        self.assertTrue(ok)
        self.assertEqual(settings_obj.site_public_key, "")
        self.assertFalse(settings_obj.is_widget_configured)

    def test_context_processor_requires_public_key_only_for_widget(self):
        LiveAssistedSalesSettings.objects.create(
            pk=1,
            enabled=True,
            las_base_url="http://localhost:8001/",
            store_api_key="site_sk_secret",
            site_public_key="",
        )
        request = RequestFactory().get("/")
        request.session = {}
        request.user = Mock(is_authenticated=False)

        context = live_assisted_sales(request)["live_assisted_sales"]

        self.assertTrue(context["enabled"])
        self.assertFalse(context["widget_enabled"])
        self.assertEqual(context["widget_script_url"], "http://localhost:8001/widget/v1/chat.js")

        settings_obj = LiveAssistedSalesSettings.get_solo()
        settings_obj.site_public_key = "site_pk_live"
        settings_obj.save(update_fields=["site_public_key"])

        context = live_assisted_sales(request)["live_assisted_sales"]
        self.assertTrue(context["widget_enabled"])
        self.assertEqual(context["site_public_key"], "site_pk_live")

    def test_context_processor_exposes_widget_accent_with_brand_default(self):
        settings_obj = LiveAssistedSalesSettings.objects.create(
            pk=1,
            enabled=True,
            las_base_url="http://localhost:8001/",
            store_api_key="site_sk_secret",
            site_public_key="site_pk_live",
        )
        request = RequestFactory().get("/")
        request.session = {}
        request.user = Mock(is_authenticated=False)

        context = live_assisted_sales(request)["live_assisted_sales"]
        self.assertEqual(context["widget_accent"], "#2563eb")

        settings_obj.widget_accent_color = "#16a34a"
        settings_obj.save(update_fields=["widget_accent_color"])
        context = live_assisted_sales(request)["live_assisted_sales"]
        self.assertEqual(context["widget_accent"], "#16a34a")

    def test_tracker_renders_widget_accent_attribute(self):
        html = render_to_string(
            "live_assisted_sales/tracker.html",
            {
                "live_assisted_sales": {
                    "enabled": True,
                    "events_url": "/live-assisted-sales/events/",
                    "initial_cart": {},
                    "customer": {},
                    "widget_enabled": True,
                    "widget_script_url": "https://las.example/widget/v1/chat.js",
                    "site_public_key": "site_pk_live",
                    "widget_accent": "#16a34a",
                }
            },
        )

        self.assertIn('data-las-accent="#16a34a"', html)

    def test_context_processor_exposes_authenticated_customer_for_widget(self):
        LiveAssistedSalesSettings.objects.create(
            pk=1,
            enabled=True,
            las_base_url="http://localhost:8001/",
            store_api_key="site_sk_secret",
            site_public_key="site_pk_live",
        )
        user = get_user_model().objects.create_user(
            username="shopper@example.com",
            email="shopper@example.com",
            first_name="Shopper",
        )
        request = RequestFactory().get("/")
        request.session = {}
        request.user = user

        context = live_assisted_sales(request)["live_assisted_sales"]

        customer = context["customer"]
        self.assertEqual(customer["id"], str(user.pk))
        self.assertEqual(customer["external_id"], str(user.pk))
        self.assertEqual(customer["email"], "shopper@example.com")
        self.assertEqual(customer["name"], "Shopper")
        self.assertEqual(customer["display"], "Shopper")
        # The identity claims are HMAC-signed with the shared store API key so las-backend can
        # verify them; the key itself never reaches the browser.
        self.assertNotIn("site_sk_secret", str(customer))
        self.assertGreater(int(customer["exp"]), int(time.time()))
        expected = hmac.new(
            b"site_sk_secret",
            f"{user.pk}|shopper@example.com|{customer['exp']}".encode(),
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(customer["sig"], expected)

    def test_customer_identity_is_not_signed_without_store_api_key(self):
        LiveAssistedSalesSettings.objects.create(
            pk=1,
            enabled=True,
            las_base_url="http://localhost:8001/",
            store_api_key="",
            site_public_key="site_pk_live",
        )
        user = get_user_model().objects.create_user(
            username="nokey@example.com", email="nokey@example.com"
        )
        request = RequestFactory().get("/")
        request.session = {}
        request.user = user

        context = live_assisted_sales(request)["live_assisted_sales"]

        self.assertNotIn("sig", context["customer"])
        self.assertNotIn("exp", context["customer"])

    def test_tracker_renders_widget_script_only_with_public_key(self):
        html = render_to_string(
            "live_assisted_sales/tracker.html",
            {
                "live_assisted_sales": {
                    "enabled": True,
                    "events_url": "/live-assisted-sales/events/",
                    "initial_cart": {},
                    "customer": {},
                    "widget_enabled": True,
                    "widget_script_url": "https://las.example/widget/v1/chat.js",
                    "site_public_key": "site_pk_live",
                }
            },
        )

        self.assertIn('src="https://las.example/widget/v1/chat.js"', html)
        self.assertIn('data-las-site="site_pk_live"', html)

        html = render_to_string(
            "live_assisted_sales/tracker.html",
            {
                "live_assisted_sales": {
                    "enabled": True,
                    "events_url": "/live-assisted-sales/events/",
                    "initial_cart": {},
                    "customer": {},
                    "widget_enabled": False,
                    "widget_script_url": "",
                    "site_public_key": "",
                }
            },
        )

        self.assertNotIn("/widget/v1/chat.js", html)

    def test_tracker_does_not_render_any_las_scripts_when_disabled(self):
        html = render_to_string(
            "live_assisted_sales/tracker.html",
            {
                "live_assisted_sales": {
                    "enabled": False,
                    "events_url": "/live-assisted-sales/events/",
                    "initial_cart": {},
                    "customer": {},
                    "widget_enabled": True,
                    "widget_script_url": "https://las.example/widget/v1/chat.js",
                    "site_public_key": "site_pk_live",
                }
            },
        )

        self.assertNotIn("/live-assisted-sales/events/", html)
        self.assertNotIn("/widget/v1/chat.js", html)

    def test_tracker_publishes_widget_customer_before_loading_widget(self):
        html = render_to_string(
            "live_assisted_sales/tracker.html",
            {
                "live_assisted_sales": {
                    "enabled": True,
                    "events_url": "/live-assisted-sales/events/",
                    "initial_cart": {},
                    "customer": {
                        "id": "7",
                        "external_id": "7",
                        "email": "shopper@example.com",
                        "name": "Shopper",
                        "display": "Shopper",
                    },
                    "widget_enabled": True,
                    "widget_script_url": "https://las.example/widget/v1/chat.js",
                    "site_public_key": "site_pk_live",
                }
            },
        )

        self.assertIn('id="las-customer"', html)
        self.assertIn("window.LAS_CUSTOMER", html)
        self.assertLess(html.index("window.LAS_CUSTOMER"), html.index('src="https://las.example/widget/v1/chat.js"'))

    @patch("apps.live_assisted_sales.client.LiveAssistedSalesClient.test_connection")
    def test_connection_failure_keeps_last_known_public_key(self, test_connection_mock):
        # A transient network error must NOT wipe a previously fetched public key, otherwise the
        # storefront chat widget disappears until someone manually re-runs the connection check.
        test_connection_mock.side_effect = OSError("network down")
        settings_obj = LiveAssistedSalesSettings.objects.create(
            enabled=True,
            las_base_url="http://localhost:8001",
            store_api_key="site_sk_secret",
            site_public_key="site_pk_live",
        )

        ok, message = run_settings_connection_test(settings_obj)

        settings_obj.refresh_from_db()
        self.assertFalse(ok)
        self.assertEqual(settings_obj.last_test_status, "failed")
        self.assertEqual(settings_obj.site_public_key, "site_pk_live")
        self.assertTrue(settings_obj.is_widget_configured)
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
        self.assertEqual(settings_obj.site_public_key, "")
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

    @patch("apps.live_assisted_sales.client.LiveAssistedSalesClient")
    def test_send_event_uses_generous_dispatch_timeout(self, client_cls_mock):
        # Delivery runs off the request path, so the timeout must be generous enough that a healthy
        # backend taking ~1s does not get its events dropped. Guards against regressing to ~0.8s.
        client_cls_mock.return_value.send_event.return_value = (200, {"ok": True})
        settings_obj = LiveAssistedSalesSettings.objects.create(
            enabled=True,
            las_base_url="http://localhost:8001",
            store_api_key="site_sk_secret",
        )

        result = send_event(settings_obj, {"event_type": "search"})

        self.assertTrue(result)
        _args, kwargs = client_cls_mock.call_args
        self.assertGreaterEqual(kwargs["timeout"], 3.0)


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

    def test_build_event_payload_captures_real_visitor_ip(self):
        # Events are forwarded server-to-server, so LAS only sees this app's server IP. The shopper's
        # real address must be captured from their request and carried in the payload.
        request = RequestFactory().get(
            "/products/demo/",
            HTTP_X_FORWARDED_FOR="198.51.100.7, 172.17.0.5",
            REMOTE_ADDR="172.17.0.5",
        )
        request.session = Mock()
        request.session.session_key = "session-1"

        payload = build_event_payload(request, "product_view")

        self.assertEqual(payload["metadata"]["client_ip"], "198.51.100.7")

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

    @patch("apps.live_assisted_sales.events.SiteSettings.get_settings")
    def test_build_event_payload_sends_store_logo_on_session_start(self, get_settings_mock):
        get_settings_mock.return_value = Mock(logo_url="/media/logo.png")
        request = RequestFactory().get("/", HTTP_HOST="shop.example.test")
        request.session = Mock()
        request.session.session_key = "session-1"

        start = build_event_payload(request, "session_start")
        self.assertEqual(start["metadata"]["widget"]["logo_url"], "http://shop.example.test/media/logo.png")

        # The logo is sent once per session, not on every event.
        view = build_event_payload(request, "product_view")
        self.assertNotIn("widget", view["metadata"])

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
