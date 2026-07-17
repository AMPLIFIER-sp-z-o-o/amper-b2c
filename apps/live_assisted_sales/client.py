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
    base_url = settings_obj.effective_base_url
    if not base_url or not settings_obj.store_api_key:
        # Genuinely unconfigured — there is nothing to authenticate, so drop any stale key. The base
        # URL comes from the deployment (settings.LAS_BASE_URL); if it's missing that's an install
        # problem for AMPER, not something the store owner can fix, so word each case for its owner.
        settings_obj.site_public_key = ""
        if not base_url:
            message = _("The AMPER LAS platform address isn't set up on the server. Please contact AMPER support.")
        else:
            message = _("A store API key is required. Paste the key from your store's page in the AMPER LAS console.")
        settings_obj.record_test_result("failed", message)
        return False, message

    try:
        _status, data = LiveAssistedSalesClient(
            base_url,
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
        # Translate the two common misconfigurations into plain language for a non-technical admin
        # instead of surfacing raw socket jargon like "getaddrinfo failed" / errno numbers.
        reason = str(getattr(exc, "reason", "") or exc).lower()
        if any(token in reason for token in ("getaddrinfo", "name or service not known", "nodename nor servname", "11001")):
            message = _(
                "We couldn't find that server. Check the AMPER LAS server address — it's the AMPER "
                "platform address (e.g. https://las.ampliapps.com, or http://localhost:8001 in "
                "development), not your store's own website."
            )
        elif any(token in reason for token in ("refused", "10061", "connection reset", "10054")):
            message = _(
                "The AMPER LAS server address was reached but refused the connection. Confirm the "
                "address and port are correct and that the LAS platform is running."
            )
        else:
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


TARGET_PRIMARY = "primary"
TARGET_MIRROR = "mirror"


def _target_credentials(settings_obj, target):
    """(base_url, api_key) for a delivery target, or (None, None) when that target is unconfigured."""
    if target == TARGET_MIRROR:
        if not settings_obj.is_mirror_configured:
            return None, None
        return settings_obj.effective_mirror_base_url, settings_obj.mirror_api_key
    if not settings_obj.is_configured:
        return None, None
    return settings_obj.effective_base_url, settings_obj.store_api_key


def send_event(settings_obj, payload, target=TARGET_PRIMARY):
    base_url, api_key = _target_credentials(settings_obj, target)
    if not base_url:
        return False
    try:
        LiveAssistedSalesClient(base_url, api_key, timeout=EVENT_DISPATCH_TIMEOUT).send_event(payload)
        return True
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        logger.warning("Live Assisted Sales event dispatch failed (%s): %s", target, exc)
        return False
    except Exception:
        logger.exception("Live Assisted Sales event dispatch failed unexpectedly (%s).", target)
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


# Money/truth events whose loss would corrupt analytics or ML labels are delivered durably via the
# transactional outbox; everything else (session lifecycle, views, searches, high-frequency
# telemetry) keeps the cheap fire-and-forget fast path.
DURABLE_EVENT_TYPES = {"add_to_cart", "remove_from_cart", "begin_checkout", "purchase"}
OUTBOX_MAX_ATTEMPTS = 8


def _delivery_targets(settings_obj):
    targets = [TARGET_PRIMARY]
    if settings_obj.is_mirror_configured:
        targets.append(TARGET_MIRROR)
    return targets


def enqueue_event(settings_obj, payload):
    if not settings_obj.is_configured:
        return False
    targets = _delivery_targets(settings_obj)
    if str(payload.get("event_type", "")) in DURABLE_EVENT_TYPES:
        return _enqueue_durable(settings_obj, payload, targets)
    ok = False
    for target in targets:
        try:
            _delivery_executor.submit(send_event, settings_obj, payload, target)
            ok = ok or target == TARGET_PRIMARY
        except Exception:
            logger.exception("Live Assisted Sales event enqueue failed (%s).", target)
    return ok


def _enqueue_durable(settings_obj, payload, targets):
    """Persist an outbox row per target (durable), then attempt immediate delivery off the request
    thread. The periodic relay retries anything the fast path doesn't confirm. Each target keeps its
    own row so e.g. a mirror outage never blocks or double-sends the primary stream."""
    from .models import OutboxEvent

    ok = False
    for target in targets:
        try:
            row = OutboxEvent.objects.create(
                payload=payload, event_type=str(payload.get("event_type", ""))[:64], target=target
            )
        except Exception:
            # If the outbox write itself fails, degrade to fire-and-forget rather than dropping silently.
            logger.exception("Live Assisted Sales outbox write failed (%s); falling back to fire-and-forget.", target)
            try:
                _delivery_executor.submit(send_event, settings_obj, payload, target)
                ok = ok or target == TARGET_PRIMARY
            except Exception:
                pass
            continue
        ok = ok or target == TARGET_PRIMARY
        try:
            _delivery_executor.submit(deliver_outbox_row, row.id)
        except Exception:
            logger.exception("Outbox fast-path submit failed; the relay will retry row %s.", row.id)
    return ok


def deliver_outbox_row(outbox_id):
    """Attempt delivery of one PENDING outbox row and update its state. Safe to call from the thread
    pool, the Celery relay task, or the management command. Returns True on a confirmed send."""
    from django.utils import timezone

    from .models import LiveAssistedSalesSettings, OutboxEvent

    row = OutboxEvent.objects.filter(id=outbox_id, status=OutboxEvent.Status.PENDING).first()
    if row is None:
        return False
    settings_obj = LiveAssistedSalesSettings.get_solo()
    # An unconfigured target keeps its rows PENDING without burning attempts: re-adding the key
    # later (or re-enabling the mirror) still delivers the backlog instead of dead-lettering it.
    if _target_credentials(settings_obj, row.target)[0] is None:
        return False

    sent = send_event(settings_obj, row.payload, row.target)
    row.attempts = (row.attempts or 0) + 1
    if sent:
        row.status = OutboxEvent.Status.SENT
        row.sent_at = timezone.now()
        row.last_error = ""
    else:
        row.last_error = "delivery failed"
        if row.attempts >= OUTBOX_MAX_ATTEMPTS:
            row.status = OutboxEvent.Status.FAILED
    row.save(update_fields=["attempts", "status", "sent_at", "last_error", "updated_at"])
    return sent


def relay_pending_outbox(limit=200):
    """Deliver outbox rows the fast path didn't confirm (worker restart, LAS downtime). Called by the
    periodic Celery task / management command. Returns the number delivered this pass."""
    from .models import OutboxEvent

    pending_ids = list(
        OutboxEvent.objects.filter(status=OutboxEvent.Status.PENDING)
        .order_by("created_at")
        .values_list("id", flat=True)[:limit]
    )
    return sum(1 for outbox_id in pending_ids if deliver_outbox_row(outbox_id))
