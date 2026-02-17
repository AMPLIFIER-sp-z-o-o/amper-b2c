"""Checkout-related shared constants/helpers.

Keep these in a single module so cart + orders flows stay consistent.

We keep checkout delivery details in server-side session (never LocalStorage) because
they contain sensitive personal data.

Session layout:
- CHECKOUT_SESSION_KEY: active details used to place the order
- CHECKOUT_ORDER_DETAILS_SESSION_KEY: "address entered in this order" snapshot (kept when user switches to saved address)
- CHECKOUT_META_SESSION_KEY: timestamps + mode for checkout timeout and UX
"""

from __future__ import annotations

from dataclasses import dataclass

from django.utils import timezone


CHECKOUT_SESSION_KEY = "checkout_details"

# Separate snapshot for the "address entered in this order" so it isn't lost when
# a logged-in user switches to one of their saved addresses.
CHECKOUT_ORDER_DETAILS_SESSION_KEY = "checkout_order_details"

# Meta information for timeouts and which address source is currently selected.
CHECKOUT_META_SESSION_KEY = "checkout_meta"


CHECKOUT_MODE_USER_DEFAULT = "user_default"
CHECKOUT_MODE_ORDER_SESSION = "order_session"


# Timeout policy
# - sliding: clear checkout if no activity for 30 minutes
# - absolute: clear checkout after 2 hours from first activity
CHECKOUT_SLIDING_IDLE_SECONDS = 30 * 60
CHECKOUT_MAX_LIFETIME_SECONDS = 2 * 60 * 60


@dataclass(frozen=True)
class CheckoutSessionState:
	active_details: dict
	order_details: dict
	meta: dict
	expired: bool


def _now_ts() -> int:
	return int(timezone.now().timestamp())


def _is_expired(meta: dict) -> bool:
	if not meta:
		return False

	started_ts = int(meta.get("started_ts") or 0)
	last_ts = int(meta.get("last_activity_ts") or 0)
	if not started_ts or not last_ts:
		return False

	now_ts = _now_ts()
	if now_ts - last_ts > CHECKOUT_SLIDING_IDLE_SECONDS:
		return True
	if now_ts - started_ts > CHECKOUT_MAX_LIFETIME_SECONDS:
		return True
	return False


def clear_checkout_session(request) -> None:
	request.session.pop(CHECKOUT_SESSION_KEY, None)
	request.session.pop(CHECKOUT_ORDER_DETAILS_SESSION_KEY, None)
	request.session.pop(CHECKOUT_META_SESSION_KEY, None)


def touch_checkout_session(request, *, set_mode: str | None = None) -> dict:
	"""Update checkout meta timestamps (sliding timeout) and optionally mode."""
	meta = request.session.get(CHECKOUT_META_SESSION_KEY) or {}
	now_ts = _now_ts()
	meta.setdefault("started_ts", now_ts)
	meta["last_activity_ts"] = now_ts
	if set_mode:
		meta["mode"] = set_mode
	request.session[CHECKOUT_META_SESSION_KEY] = meta
	return meta


def get_checkout_state(request, *, touch: bool = True) -> CheckoutSessionState:
	"""Read checkout session state, applying expiration policy.

	If expired, clears checkout keys and returns empty state with expired=True.
	"""
	meta = request.session.get(CHECKOUT_META_SESSION_KEY) or {}
	if _is_expired(meta):
		clear_checkout_session(request)
		return CheckoutSessionState(active_details={}, order_details={}, meta={}, expired=True)

	active = request.session.get(CHECKOUT_SESSION_KEY) or {}
	order = request.session.get(CHECKOUT_ORDER_DETAILS_SESSION_KEY) or {}
	if touch and (active or order or meta):
		meta = touch_checkout_session(request)

	return CheckoutSessionState(active_details=dict(active), order_details=dict(order), meta=dict(meta), expired=False)


def set_checkout_active_details(request, details: dict, *, mode: str | None = None) -> None:
	request.session[CHECKOUT_SESSION_KEY] = details
	touch_checkout_session(request, set_mode=mode)


def set_checkout_order_details(request, details: dict) -> None:
	request.session[CHECKOUT_ORDER_DETAILS_SESSION_KEY] = details
	touch_checkout_session(request)


def get_checkout_mode(meta: dict) -> str:
	mode = (meta or {}).get("mode")
	if mode in {CHECKOUT_MODE_USER_DEFAULT, CHECKOUT_MODE_ORDER_SESSION}:
		return mode
	return CHECKOUT_MODE_ORDER_SESSION
