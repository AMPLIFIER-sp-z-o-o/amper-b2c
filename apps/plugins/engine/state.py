from __future__ import annotations

import time
from contextvars import ContextVar, Token

_request_deadline_monotonic: ContextVar[float | None] = ContextVar("plugin_request_deadline_monotonic", default=None)


def set_request_budget_ms(total_ms: int) -> Token:
    deadline = time.monotonic() + max(total_ms, 0) / 1000.0
    return _request_deadline_monotonic.set(deadline)


def reset_request_budget(token: Token) -> None:
    _request_deadline_monotonic.reset(token)


def get_remaining_budget_seconds() -> float | None:
    deadline = _request_deadline_monotonic.get()
    if deadline is None:
        return None
    return max(deadline - time.monotonic(), 0.0)
