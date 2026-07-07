import hashlib
import hmac
import json
import time
from decimal import Decimal
from io import BytesIO
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings

from apps.web.models import SiteSettings

from .admin import LiveAssistedSalesSettingsForm
from .client import run_settings_connection_test, send_event
from .context_processors import _consent_region, _country_code_from_request, live_assisted_sales
from .events import (
    build_event_payload,
    cart_payload,
    category_payload,
    dispatch_event,
    order_cart_payload,
    order_metadata,
    product_payload,
    track_begin_checkout,
    track_purchase,
)
from .models import LiveAssistedSalesSettings


class LiveAssistedSalesSettingsAdminFormTests(SimpleTestCase):
    def test_admin_settings_form_prevents_credential_autofill(self):
        form = LiveAssistedSalesSettingsForm()

        self.assertEqual(form.fields["store_api_key"].widget.attrs["autocomplete"], "new-password")
        self.assertEqual(form.fields["store_api_key"].widget.attrs["data-lpignore"], "true")
        self.assertEqual(form.fields["store_api_key"].widget.attrs["data-1p-ignore"], "true")

    def test_admin_form_shows_only_owner_relevant_fields(self):
        # The owner deals only with the API key (+ optional accent colour / enable toggle). The server
        # address (deployment constant) and the auto-fetched public key are internal, so neither
        # appears on the form — the store API key does.
        fields = LiveAssistedSalesSettingsForm().fields
        self.assertNotIn("las_base_url", fields)
        self.assertNotIn("site_public_key", fields)
        self.assertIn("store_api_key", fields)

    def test_las_base_url_requires_https_except_localhost(self):
        from django.core.exceptions import ValidationError

        # http to a public host would send the Bearer key + PII in cleartext -> rejected.
        with self.assertRaises(ValidationError):
            LiveAssistedSalesSettings(las_base_url="http://las.example.com", store_api_key="k").clean()
        # https public host and http localhost (dev) are both allowed.
        LiveAssistedSalesSettings(las_base_url="https://las.example.com").clean()
        LiveAssistedSalesSettings(las_base_url="http://localhost:8001").clean()


class LiveAssistedSalesEffectiveBaseUrlTests(SimpleTestCase):
    @override_settings(LAS_BASE_URL="https://las.ampliapps.com")
    def test_effective_base_url_comes_from_deployment_setting(self):
        # Owner never enters a URL; it comes from the deployment setting, and the store still counts
        # as configured with just the API key.
        obj = LiveAssistedSalesSettings(enabled=True, store_api_key="k")
        self.assertEqual(obj.effective_base_url, "https://las.ampliapps.com")
        self.assertTrue(obj.is_configured)

    @override_settings(LAS_BASE_URL="")
    def test_effective_base_url_falls_back_to_legacy_field(self):
        obj = LiveAssistedSalesSettings(enabled=True, store_api_key="k", las_base_url="http://localhost:8001")
        self.assertEqual(obj.effective_base_url, "http://localhost:8001")

    @override_settings(LAS_BASE_URL="")
    def test_not_configured_without_any_base_url(self):
        obj = LiveAssistedSalesSettings(enabled=True, store_api_key="k")
        self.assertFalse(obj.is_configured)


class LiveAssistedSalesGetSoloTests(TestCase):
    def setUp(self):
        LiveAssistedSalesSettings.objects.all().delete()

    def test_get_solo_defaults_enabled_so_only_the_key_is_needed(self):
        # A fresh singleton is created already enabled, so the owner's single required step is pasting
        # the API key (still inert until a key is present, so this sends nothing on its own).
        obj = LiveAssistedSalesSettings.get_solo()
        self.assertTrue(obj.enabled)
        self.assertFalse(obj.is_configured)  # no key yet -> nothing happens


class LiveAssistedSalesSettingsAdminDeleteTests(TestCase):
    """Deleting the settings must tell LAS to drop this store's live/verified status, otherwise the
    backend stores list keeps showing "Live connected" forever (nothing else ever un-verifies it)."""

    def setUp(self):
        from django.contrib.admin.sites import AdminSite

        from .admin import LiveAssistedSalesSettingsAdmin

        LiveAssistedSalesSettings.objects.all().delete()
        self.admin = LiveAssistedSalesSettingsAdmin(LiveAssistedSalesSettings, AdminSite())
        self.request = RequestFactory().post("/admin/")

    @patch("apps.live_assisted_sales.admin.notify_disconnected")
    def test_delete_model_notifies_las_then_removes_row(self, notify_mock):
        settings_obj = LiveAssistedSalesSettings.objects.create(
            enabled=True,
            las_base_url="http://localhost:8001",
            store_api_key="site_sk_secret",
        )

        self.admin.delete_model(self.request, settings_obj)

        notify_mock.assert_called_once_with("http://localhost:8001", "site_sk_secret")
        self.assertFalse(LiveAssistedSalesSettings.objects.exists())

    @patch("apps.live_assisted_sales.admin.notify_disconnected")
    def test_delete_model_notifies_even_when_disabled(self, notify_mock):
        # A store disabled but still holding credentials may have been verified before it was turned
        # off; disconnect is idempotent, so notify whenever we still hold a base URL + key.
        settings_obj = LiveAssistedSalesSettings.objects.create(
            enabled=False,
            las_base_url="http://localhost:8001",
            store_api_key="site_sk_secret",
        )

        self.admin.delete_model(self.request, settings_obj)

        notify_mock.assert_called_once_with("http://localhost:8001", "site_sk_secret")

    @patch("apps.live_assisted_sales.admin.notify_disconnected")
    def test_delete_model_skips_notify_when_never_configured(self, notify_mock):
        settings_obj = LiveAssistedSalesSettings.objects.create(enabled=False)

        self.admin.delete_model(self.request, settings_obj)

        notify_mock.assert_not_called()
        self.assertFalse(LiveAssistedSalesSettings.objects.exists())

    @patch("apps.live_assisted_sales.admin.notify_disconnected")
    def test_bulk_delete_notifies_per_configured_row(self, notify_mock):
        LiveAssistedSalesSettings.objects.create(
            enabled=True, las_base_url="http://localhost:8001", store_api_key="site_sk_secret"
        )

        self.admin.delete_queryset(self.request, LiveAssistedSalesSettings.objects.all())

        notify_mock.assert_called_once_with("http://localhost:8001", "site_sk_secret")
        self.assertFalse(LiveAssistedSalesSettings.objects.exists())


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
    def test_dns_failure_returns_plain_language_not_socket_jargon(self, test_connection_mock):
        # The #1 setup mistake is pasting the store's OWN website into the base URL, which fails DNS
        # with "getaddrinfo failed". The admin must see guidance, not raw socket errno jargon.
        test_connection_mock.side_effect = URLError("[Errno 11001] getaddrinfo failed")
        settings_obj = LiveAssistedSalesSettings.objects.create(
            enabled=True, las_base_url="https://demo-sklep.example.com", store_api_key="site_sk_secret"
        )

        ok, message = run_settings_connection_test(settings_obj)

        self.assertFalse(ok)
        self.assertNotIn("getaddrinfo", message)
        self.assertNotIn("11001", message)
        self.assertIn("server address", message.lower())

    @patch("apps.live_assisted_sales.client.LiveAssistedSalesClient.test_connection")
    def test_connection_refused_returns_plain_language(self, test_connection_mock):
        test_connection_mock.side_effect = URLError("[Errno 10061] Connection refused")
        settings_obj = LiveAssistedSalesSettings.objects.create(
            enabled=True, las_base_url="http://localhost:8001", store_api_key="site_sk_secret"
        )

        ok, message = run_settings_connection_test(settings_obj)

        self.assertFalse(ok)
        self.assertNotIn("10061", message)
        self.assertIn("refused", message.lower())

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
            data=json.dumps({"event_type": "view_item", "product": {"id": "p1", "name": "Chemex"}}),
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

        payload = build_event_payload(request, "view_item", page={"title": "Demo"})

        self.assertEqual(payload["event_type"], "view_item")
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

        payload = build_event_payload(request, "view_item")

        self.assertEqual(payload["metadata"]["client_ip"], "198.51.100.7")

    def _authed_request(self, **meta):
        user = get_user_model().objects.create_user(
            username="pii@example.com", email="pii@example.com", password="x"
        )
        request = RequestFactory().get("/products/demo/", REMOTE_ADDR="198.51.100.9", **meta)
        request.session = Mock()
        request.session.session_key = "session-pii"
        request.user = user
        return request

    def test_eu_visitor_without_consent_has_pii_withheld(self):
        # EU regime (CF country header) + no consent cookie -> raw email + IP must NOT be forwarded.
        request = self._authed_request(HTTP_CF_IPCOUNTRY="PL")
        payload = build_event_payload(request, "view_item")
        user_meta = payload["metadata"]["user"]
        self.assertTrue(user_meta["authenticated"])
        self.assertNotIn("email", user_meta)
        self.assertNotIn("client_ip", payload["metadata"])
        self.assertNotIn("pii@example.com", str(payload))

    def test_eu_visitor_with_consent_forwards_pii(self):
        request = self._authed_request(HTTP_CF_IPCOUNTRY="PL", HTTP_COOKIE="las_consent=true")
        payload = build_event_payload(request, "view_item")
        self.assertEqual(payload["metadata"]["user"]["email"], "pii@example.com")
        self.assertEqual(payload["metadata"]["client_ip"], "198.51.100.9")

    def test_explicit_opt_out_withholds_pii_anywhere(self):
        # consent=false (US opt-out) -> withhold email + IP even outside the EU.
        request = self._authed_request(HTTP_CF_IPCOUNTRY="US", HTTP_COOKIE="las_consent=false")
        payload = build_event_payload(request, "view_item")
        self.assertNotIn("email", payload["metadata"]["user"])
        self.assertNotIn("client_ip", payload["metadata"])

    def test_non_eu_default_forwards_pii(self):
        # Non-EU, no explicit choice -> opt-out model, PII allowed (unchanged behaviour).
        request = self._authed_request(HTTP_CF_IPCOUNTRY="US")
        payload = build_event_payload(request, "view_item")
        self.assertEqual(payload["metadata"]["user"]["email"], "pii@example.com")

    def test_build_event_payload_uses_tracker_cookies_for_anonymous_identity(self):
        request = RequestFactory().get(
            "/products/demo/",
            HTTP_COOKIE="las_visitor_id=visitor-cookie; las_session_id=session-cookie",
        )
        request.session = Mock()
        request.session.session_key = None

        payload = build_event_payload(request, "view_item")

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
        view = build_event_payload(request, "view_item")
        self.assertNotIn("widget", view["metadata"])

    def test_build_event_payload_does_not_trust_browser_user_metadata(self):
        request = RequestFactory().get("/")
        request.session = Mock()
        request.session.session_key = "session-1"

        payload = build_event_payload(
            request,
            "view_item",
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

        payload = build_event_payload(request, "view_item")

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

    def test_product_payload_includes_primary_image_and_price(self):
        # LAS renders a product card from these; the image must be the lowest sort_order, absolute.
        request = RequestFactory().get("/")
        primary = Mock()
        primary.image.url = "/media/product-images/sink.jpg"
        product = Mock(id=42, name="Sink", sku="SINK-1", price=Decimal("199.00"))
        product.get_absolute_url.return_value = "/products/42-sink/"
        product.images.all.return_value.order_by.return_value.first.return_value = primary

        payload = product_payload(product, request=request)
        self.assertEqual(payload["image"], "http://testserver/media/product-images/sink.jpg")
        self.assertEqual(payload["price"], "199.00")
        self.assertTrue(payload["price_display"])  # currency-formatted, non-empty

    def test_product_payload_image_empty_when_no_images(self):
        request = RequestFactory().get("/")
        product = Mock(id=43, name="No image", sku="NI-1", price=Decimal("10.00"))
        product.get_absolute_url.return_value = "/products/43-no-image/"
        product.images.all.return_value.order_by.return_value.first.return_value = None

        self.assertEqual(product_payload(product, request=request)["image"], "")

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


class ConversionEventTests(TestCase):
    """LAS-6 conversion events: checkout_started + order_completed built from Order/OrderLine, with
    the LAS visitor/session attribution carried explicitly (delivery is off the request path)."""

    def setUp(self):
        LiveAssistedSalesSettings.objects.all().delete()
        LiveAssistedSalesSettings.objects.create(
            pk=1, enabled=True, las_base_url="http://localhost:8001", store_api_key="site_sk_secret"
        )
        self.rf = RequestFactory()

    def _mock_order(self):
        product = Mock(id=42, name="Chemex", sku="CHEMEX-1")
        product.get_absolute_url.return_value = "/products/42-chemex/"
        line = Mock(product_id=42, product=product, quantity=2, unit_price="50.00", line_total="100.00")
        order = Mock(
            pk=55,
            tracking_token="tok-abc",
            status="pending",
            subtotal="100.00",
            discount_total="0.00",
            delivery_cost="10.00",
            total="110.00",
            currency="PLN",
            coupon_code="",
        )
        order.lines.select_related.return_value.all.return_value = [line]
        return order

    def test_order_cart_payload_preserves_value_invariant(self):
        payload = order_cart_payload(self._mock_order(), request=self.rf.get("/"))

        self.assertEqual(payload["items_count"], 2)
        self.assertEqual(payload["total"], "110.00")
        self.assertEqual(payload["currency"], "PLN")
        item = payload["items"][0]
        self.assertEqual(item["sku"], "CHEMEX-1")
        self.assertEqual(item["url"], "http://testserver/products/42-chemex/")
        # value invariant: line_total == unit_price * quantity
        self.assertEqual(Decimal(item["line_total"]), Decimal(item["price"]) * item["quantity"])

    def test_order_metadata_carries_label_fields(self):
        meta = order_metadata(self._mock_order())["order"]

        self.assertEqual(meta["order_id"], "55")
        self.assertEqual(meta["total"], "110.00")
        self.assertEqual(meta["delivery_cost"], "10.00")
        self.assertEqual(meta["currency"], "PLN")

    @patch("apps.live_assisted_sales.events.enqueue_event")
    def test_track_purchase_attributes_to_explicit_session(self, enqueue_mock):
        enqueue_mock.return_value = True

        ok = track_purchase(
            self.rf.get("/orders/summary/"), self._mock_order(), visitor_id="vis-1", session_id="ses-1"
        )

        self.assertTrue(ok)
        payload = enqueue_mock.call_args.args[1]
        self.assertEqual(payload["event_type"], "purchase")
        # Attribution carried explicitly, not derived from the (cookie-less) request.
        self.assertEqual(payload["visitor_id"], "vis-1")
        self.assertEqual(payload["session_id"], "ses-1")
        self.assertEqual(payload["cart"]["items_count"], 2)
        self.assertEqual(payload["metadata"]["order"]["order_id"], "55")
        self.assertEqual(payload["metadata"]["order"]["total"], "110.00")

    @patch("apps.live_assisted_sales.events.enqueue_event")
    def test_track_begin_checkout_carries_cart_snapshot(self, enqueue_mock):
        enqueue_mock.return_value = True
        product = Mock(id=42, name="Chemex", sku="CHEMEX-1")
        product.get_absolute_url.return_value = "/products/42-chemex/"
        line = Mock(product_id=42, product=product, quantity=2, price="50.00")
        line.subtotal = "100.00"
        cart = Mock(total="110.00")
        cart.lines.select_related.return_value.all.return_value = [line]

        ok = track_begin_checkout(self.rf.get("/cart/"), cart, visitor_id="vis-1", session_id="ses-1")

        self.assertTrue(ok)
        payload = enqueue_mock.call_args.args[1]
        self.assertEqual(payload["event_type"], "begin_checkout")
        self.assertEqual(payload["visitor_id"], "vis-1")
        self.assertEqual(payload["cart"]["items_count"], 2)

    def test_conversion_event_types_are_supported(self):
        from .events import SUPPORTED_EVENT_TYPES

        self.assertIn("begin_checkout", SUPPORTED_EVENT_TYPES)
        self.assertIn("purchase", SUPPORTED_EVENT_TYPES)


class TelemetryEventTests(TestCase):
    """LAS-6 client-side coverage: clicks, scroll depth, engaged-time pings, cursor hover."""

    def setUp(self):
        LiveAssistedSalesSettings.objects.all().delete()
        LiveAssistedSalesSettings.objects.create(
            pk=1, enabled=True, las_base_url="http://localhost:8001", store_api_key="site_sk_secret"
        )
        self.client = Client()

    def test_telemetry_event_types_are_supported(self):
        from .events import SUPPORTED_EVENT_TYPES

        for t in ("scroll_depth", "page_ping"):
            self.assertIn(t, SUPPORTED_EVENT_TYPES)
        # Generic click + cursor-hover were dropped from the taxonomy as non-standard noise.
        for t in ("click", "cursor_hover"):
            self.assertNotIn(t, SUPPORTED_EVENT_TYPES)

    @patch("apps.live_assisted_sales.views.enqueue_event")
    def test_browser_endpoint_accepts_telemetry_batch(self, enqueue_mock):
        enqueue_mock.return_value = True

        response = self.client.post(
            "/live-assisted-sales/events/",
            data=json.dumps(
                {
                    "events": [
                        {"event_type": "select_item", "product": {"id": "p1", "name": "Chemex"}},
                        {"event_type": "scroll_depth", "metadata": {"pct": 50}},
                        {"event_type": "page_ping", "metadata": {"engaged_ms": 15000}},
                        {"event_type": "view_cart", "cart": {"items_count": 1}},
                    ]
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sent"], 4)
        self.assertEqual(enqueue_mock.call_count, 4)

    def test_telemetry_event_skips_server_cart_lookup(self):
        # A page_ping must not run a cart DB query on every heartbeat.
        request = RequestFactory().get("/products/demo/")
        request.session = Mock()
        request.session.session_key = "session-1"

        payload = build_event_payload(request, "page_ping", metadata={"engaged_ms": 15000})

        self.assertEqual(payload["event_type"], "page_ping")
        self.assertEqual(payload["cart"], {})

    def test_tracker_renders_telemetry_listeners(self):
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

        for token in ('"select_item"', '"scroll_depth"', '"page_ping"', "engaged_ms", "sendBeacon"):
            self.assertIn(token, html)
        # Dropped from the tracker: generic click + cursor-hover emission.
        for token in ('"cursor_hover"', "onMouseOver"):
            self.assertNotIn(token, html)


class OutboxTests(TestCase):
    """LAS-6 reliability: money/truth events (cart + conversion) are delivered through a durable
    outbox with retry + dead-letter; high-frequency telemetry keeps the fire-and-forget fast path."""

    def setUp(self):
        LiveAssistedSalesSettings.objects.all().delete()
        LiveAssistedSalesSettings.objects.create(
            pk=1, enabled=True, las_base_url="http://localhost:8001", store_api_key="k"
        )

    @patch("apps.live_assisted_sales.client._delivery_executor")
    def test_durable_event_writes_outbox_row(self, executor):
        from apps.live_assisted_sales.client import enqueue_event
        from apps.live_assisted_sales.models import OutboxEvent

        ok = enqueue_event(LiveAssistedSalesSettings.get_solo(), {"event_type": "purchase", "event_id": "e1"})

        self.assertTrue(ok)
        self.assertEqual(OutboxEvent.objects.filter(event_type="purchase", status="pending").count(), 1)
        executor.submit.assert_called()

    @patch("apps.live_assisted_sales.client._delivery_executor")
    def test_telemetry_event_uses_fast_path_not_outbox(self, executor):
        from apps.live_assisted_sales.client import enqueue_event
        from apps.live_assisted_sales.models import OutboxEvent

        ok = enqueue_event(LiveAssistedSalesSettings.get_solo(), {"event_type": "page_ping", "event_id": "e2"})

        self.assertTrue(ok)
        self.assertEqual(OutboxEvent.objects.count(), 0)
        executor.submit.assert_called()

    @patch("apps.live_assisted_sales.client.send_event")
    def test_deliver_outbox_row_marks_sent(self, send_mock):
        from apps.live_assisted_sales.client import deliver_outbox_row
        from apps.live_assisted_sales.models import OutboxEvent

        send_mock.return_value = True
        row = OutboxEvent.objects.create(payload={"event_type": "purchase"}, event_type="purchase")

        self.assertTrue(deliver_outbox_row(row.id))
        row.refresh_from_db()
        self.assertEqual(row.status, "sent")
        self.assertEqual(row.attempts, 1)
        self.assertIsNotNone(row.sent_at)

    @patch("apps.live_assisted_sales.client.send_event")
    def test_deliver_outbox_row_dead_letters_after_max_attempts(self, send_mock):
        from apps.live_assisted_sales.client import OUTBOX_MAX_ATTEMPTS, deliver_outbox_row
        from apps.live_assisted_sales.models import OutboxEvent

        send_mock.return_value = False
        row = OutboxEvent.objects.create(payload={"event_type": "purchase"}, event_type="purchase")
        for _ in range(OUTBOX_MAX_ATTEMPTS):
            deliver_outbox_row(row.id)

        row.refresh_from_db()
        self.assertEqual(row.status, "failed")
        self.assertGreaterEqual(row.attempts, OUTBOX_MAX_ATTEMPTS)

    @patch("apps.live_assisted_sales.client.send_event")
    def test_relay_pending_outbox_delivers_all(self, send_mock):
        from apps.live_assisted_sales.client import relay_pending_outbox
        from apps.live_assisted_sales.models import OutboxEvent

        send_mock.return_value = True
        OutboxEvent.objects.create(payload={"event_type": "add_to_cart"}, event_type="add_to_cart")
        OutboxEvent.objects.create(payload={"event_type": "purchase"}, event_type="purchase")

        self.assertEqual(relay_pending_outbox(), 2)
        self.assertEqual(OutboxEvent.objects.filter(status="sent").count(), 2)


class ConsentRegionTests(TestCase):
    """Server-side consent regime from the visitor's IP/country: EU/EEA/UK/CH need a prior-consent
    banner ("eu"); elsewhere is opt-out ("noneu"); unknown ("") lets the client fall back to timezone."""

    def _req(self, **headers):
        return RequestFactory().get("/", **headers)

    def test_cdn_country_headers_map_to_eu(self):
        for header, code in [
            ("HTTP_CF_IPCOUNTRY", "PL"),
            ("HTTP_CLOUDFRONT_VIEWER_COUNTRY", "DE"),
            ("HTTP_X_VERCEL_IP_COUNTRY", "GB"),
            ("HTTP_X_APPENGINE_COUNTRY", "FR"),
            ("HTTP_X_GEO_COUNTRY", "IE"),
            ("HTTP_X_COUNTRY_CODE", "CH"),
        ]:
            with self.subTest(header=header, code=code):
                self.assertEqual(_consent_region(self._req(**{header: code})), "eu")

    def test_non_eu_countries_map_to_noneu(self):
        for code in ["US", "JP", "BR", "AU", "CA", "IN"]:
            with self.subTest(code=code):
                self.assertEqual(_consent_region(self._req(HTTP_CF_IPCOUNTRY=code)), "noneu")

    def test_lowercase_and_whitespace_country_is_normalised(self):
        self.assertEqual(_country_code_from_request(self._req(HTTP_CF_IPCOUNTRY=" pl ")), "PL")
        self.assertEqual(_consent_region(self._req(HTTP_CF_IPCOUNTRY=" us ")), "noneu")

    def test_unknown_or_missing_country_is_blank(self):
        # XX/T1 are CDN placeholders for unknown/Tor; a missing or malformed header is also unknown.
        self.assertEqual(_consent_region(self._req(HTTP_CF_IPCOUNTRY="XX")), "")
        self.assertEqual(_consent_region(self._req(HTTP_CF_IPCOUNTRY="T1")), "")
        self.assertEqual(_consent_region(self._req(HTTP_CF_IPCOUNTRY="ZZZ")), "")
        self.assertEqual(_consent_region(self._req()), "")

    def test_first_present_header_wins(self):
        # Cloudflare header takes precedence over the generic one in the lookup order.
        req = self._req(HTTP_CF_IPCOUNTRY="US", HTTP_X_COUNTRY_CODE="PL")
        self.assertEqual(_consent_region(req), "noneu")

    @patch("apps.live_assisted_sales.context_processors.client_ip_from_request", return_value="8.8.8.8")
    def test_geoip2_fallback_used_when_no_header(self, _ip):
        # No CDN header → fall back to GeoIP2; here we stub GeoIP2 to report the US.
        geoip = Mock()
        geoip.return_value.country_code.return_value = "US"
        with patch.dict("sys.modules", {"django.contrib.gis.geoip2": Mock(GeoIP2=geoip)}):
            self.assertEqual(_consent_region(self._req()), "noneu")
        geoip.return_value.country_code.assert_called_once_with("8.8.8.8")

    def test_context_processor_exposes_consent_region(self):
        LiveAssistedSalesSettings.objects.all().delete()
        LiveAssistedSalesSettings.objects.create(
            pk=1, enabled=True, las_base_url="http://localhost:8001/", store_api_key="k", site_public_key="pk"
        )
        request = self._req(HTTP_CF_IPCOUNTRY="PL")
        request.session = {}
        request.user = Mock(is_authenticated=False)
        self.assertEqual(live_assisted_sales(request)["live_assisted_sales"]["consent_region"], "eu")
