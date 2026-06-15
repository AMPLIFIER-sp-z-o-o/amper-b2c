import json
import logging
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)
_delivery_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="las-events")

# Event delivery runs off the request path in `_delivery_executor`, so a generous timeout never
# slows the shopper down. The previous 0.8s was tight enough that a healthy LAS backend taking ~1s
# (cold start, load, network latency) would have its events dropped with "dispatch failed: timed out".
EVENT_DISPATCH_TIMEOUT = 5.0


class LiveAssistedSalesClient:
    def __init__(self, base_url, api_key, timeout=1.5):
        self.base_url = (base_url or "").rstrip("/") + "/"
        self.api_key = api_key or ""
        self.timeout = timeout

    def _request(self, path, method="GET", payload=None):
        body = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(urljoin(self.base_url, path.lstrip("/")), data=body, headers=headers, method=method)
        with urlopen(request, timeout=self.timeout) as response:
            raw_body = response.read().decode("utf-8") or "{}"
            return response.status, json.loads(raw_body)

    def test_connection(self):
        return self._request("/api/ingest/store-events/test/")

    # The connection test reaches a possibly cold-starting LAS backend, so it gets a generous
    # timeout. A previously-fetched site_public_key must NOT be wiped just because one probe was
    # slow — that would hide the storefront chat widget until someone manually re-ran the test.
    CONNECTION_TEST_TIMEOUT = 8.0

    def disconnect(self):
        return self._request("/api/ingest/store-events/disconnect/", method="POST", payload={})

    def send_event(self, payload):
        return self._request("/api/ingest/store-events/", method="POST", payload=payload)


def run_settings_connection_test(settings_obj):
    if not settings_obj.las_base_url or not settings_obj.store_api_key:
        # Genuinely unconfigured — there is nothing to authenticate, so drop any stale key.
        settings_obj.site_public_key = ""
        settings_obj.record_test_result("failed", _("LAS base URL and store API key are required."))
        return False, settings_obj.last_test_message

    try:
        _status, data = LiveAssistedSalesClient(
            settings_obj.las_base_url,
            settings_obj.store_api_key,
            timeout=LiveAssistedSalesClient.CONNECTION_TEST_TIMEOUT,
        ).test_connection()
    except HTTPError as exc:
        detail = ""
        try:
            error_data = json.loads(exc.read().decode("utf-8") or "{}")
            detail = str(error_data.get("detail") or "").strip()
        except Exception:
            detail = ""
        key_rejected = exc.code in (401, 403) or detail == "Invalid store API key."
        if detail == "Invalid store API key.":
            detail = _("Invalid store API key.")
        message = _("LAS rejected the API key (HTTP %(code)s).") % {"code": exc.code}
        if detail:
            message = f"{message} {detail}"
        # Only forget the public key when LAS explicitly rejects the credentials. A 5xx is a
        # transient backend fault and must not hide an otherwise working chat widget.
        if key_rejected:
            settings_obj.site_public_key = ""
        settings_obj.record_test_result("failed", message)
        return False, message
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        # Network blip / timeout / cold start — keep the last-known-good public key so the
        # storefront widget stays visible instead of vanishing until the next manual test.
        message = _("LAS connection failed: %(error)s") % {"error": exc}
        settings_obj.record_test_result("failed", message)
        return False, message

    store_data = data.get("store") or {}
    store_name = store_data.get("display_name") or "store"
    public_key = str(store_data.get("public_key") or "").strip()
    settings_obj.site_public_key = public_key
    message = _("Connection to %(store)s works correctly.") % {"store": store_name}
    settings_obj.record_test_result("success", message)
    return True, message


def send_event(settings_obj, payload):
    if not settings_obj.is_configured:
        return False
    try:
        LiveAssistedSalesClient(
            settings_obj.las_base_url, settings_obj.store_api_key, timeout=EVENT_DISPATCH_TIMEOUT
        ).send_event(payload)
        return True
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        logger.warning("Live Assisted Sales event dispatch failed: %s", exc)
        return False
    except Exception:
        logger.exception("Live Assisted Sales event dispatch failed unexpectedly.")
        return False


def notify_disconnected(base_url, api_key):
    if not base_url or not api_key:
        return False
    try:
        LiveAssistedSalesClient(base_url, api_key, timeout=EVENT_DISPATCH_TIMEOUT).disconnect()
        return True
    except Exception:
        logger.exception("Live Assisted Sales disconnect notification failed.")
        return False


def enqueue_event(settings_obj, payload):
    if not settings_obj.is_configured:
        return False
    try:
        _delivery_executor.submit(send_event, settings_obj, payload)
        return True
    except Exception:
        logger.exception("Live Assisted Sales event enqueue failed.")
        return False
