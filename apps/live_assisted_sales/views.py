import json
from urllib.parse import urlparse
from uuid import uuid4

from django.http import JsonResponse
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .client import enqueue_event
from .events import SUPPORTED_EVENT_TYPES, build_event_payload
from .models import LiveAssistedSalesSettings

MAX_BROWSER_PAYLOAD_BYTES = 32 * 1024


def _is_same_origin(request):
    origin = request.headers.get("Origin") or request.headers.get("Referer")
    if not origin:
        return True
    parsed = urlparse(origin)
    return parsed.netloc == request.get_host()


def _valid_event(data):
    event_type = str(data.get("event_type") or "").strip()
    return event_type in SUPPORTED_EVENT_TYPES


def _dispatch_browser_event(request, data):
    if not _valid_event(data):
        return False, _("Unsupported event type.")
    payload = build_event_payload(
        request,
        data["event_type"],
        event_id=data.get("event_id") or str(uuid4()),
        visitor_id=data.get("visitor_id") or None,
        session_id=data.get("session_id") or None,
        occurred_at=data.get("occurred_at") or None,
        url=data.get("url") or request.build_absolute_uri("/"),
        page=data.get("page") or {},
        product=data.get("product") or {},
        category=data.get("category") or {},
        search=data.get("search") or {},
        cart=data["cart"] if "cart" in data else None,
        cursor=data.get("cursor") or {},
        metadata=data.get("metadata") or {},
    )
    settings_obj = LiveAssistedSalesSettings.get_solo()
    if enqueue_event(settings_obj, payload):
        return True, ""
    return False, _("Event could not be queued for Live Assisted Sales.")


@csrf_exempt
@require_POST
def browser_events(request):
    if not _is_same_origin(request):
        return JsonResponse({"ok": False, "detail": _("Cross-origin event requests are not allowed.")}, status=403)

    if int(request.headers.get("Content-Length") or 0) > MAX_BROWSER_PAYLOAD_BYTES:
        return JsonResponse({"ok": False, "detail": _("Payload too large.")}, status=413)

    settings_obj = LiveAssistedSalesSettings.get_solo()
    if not settings_obj.enabled or not settings_obj.is_configured:
        return JsonResponse({"ok": True, "sent": 0})

    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"ok": False, "detail": _("Invalid JSON.")}, status=400)

    events = data if isinstance(data, list) else data.get("events") if isinstance(data, dict) else None
    if events is None:
        events = [data]
    if not isinstance(events, list):
        return JsonResponse({"ok": False, "detail": _("Invalid events payload.")}, status=400)

    sent = 0
    errors = []
    for item in events[:25]:
        if not isinstance(item, dict):
            errors.append(_("Invalid event object."))
            continue
        ok, error = _dispatch_browser_event(request, item)
        if ok:
            sent += 1
        elif error:
            errors.append(error)

    status = 200 if not errors else 400
    return JsonResponse({"ok": not errors, "sent": sent, "errors": errors}, status=status)
