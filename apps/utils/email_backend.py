"""
Database-driven SMTP email backend.

Reads SMTP configuration from ``SystemSettings`` instead of Django settings,
allowing runtime changes via the admin panel.
"""

import logging
import time

from django.core.mail.backends.console import EmailBackend as ConsoleEmailBackend
from django.core.mail.backends.smtp import EmailBackend as SmtpEmailBackend

logger = logging.getLogger(__name__)

# Simple module-level cache for SystemSettings
_settings_cache: dict = {}
_CACHE_TTL = 60  # seconds


def _get_system_settings():
    """Return cached SystemSettings, refreshing every ``_CACHE_TTL`` seconds."""
    now = time.monotonic()
    cached = _settings_cache.get("obj")
    ts = _settings_cache.get("ts", 0)

    if cached is not None and (now - ts) < _CACHE_TTL:
        return cached

    from apps.web.models import SystemSettings

    try:
        obj = SystemSettings.get_settings()
    except Exception:
        logger.exception("Failed to load SystemSettings – falling back to defaults.")
        obj = None

    _settings_cache["obj"] = obj
    _settings_cache["ts"] = now
    return obj


class DatabaseSmtpBackend(SmtpEmailBackend):
    """
    SMTP backend that reads connection parameters from ``SystemSettings``.

    When ``smtp_enabled`` is *False* (or ``SystemSettings`` cannot be loaded)
    the backend silently delegates to Django's ``ConsoleEmailBackend``.
    """

    def __init__(self, **kwargs):
        # Do NOT call the parent __init__ which reads from django.conf.settings;
        # instead just store defaults so we can configure in open().
        import threading

        self.host = ""
        self.port = 587
        self.username = ""
        self.password = ""
        self.use_tls = True
        self.use_ssl = False
        self.timeout = 30
        self.ssl_keyfile = None
        self.ssl_certfile = None
        self.connection = None
        self._fallback = None
        self._lock = threading.RLock()
        # Accept fail_silently the Django way
        self.fail_silently = kwargs.get("fail_silently", False)

    def _load_settings(self):
        """Populate connection params from the DB singleton."""
        system_settings = _get_system_settings()
        if system_settings is None or not system_settings.smtp_enabled:
            return False  # signal: use console fallback

        params = system_settings.get_connection_params()
        self.host = params["host"]
        self.port = params["port"]
        self.username = params["username"]
        self.password = params["password"]
        self.use_tls = params["use_tls"]
        self.use_ssl = params["use_ssl"]
        self.ssl_certfile = params.get("ssl_certfile")
        self.timeout = params["timeout"]
        logger.debug("Loaded SMTP settings for host: %s", self.host)
        return True

    def open(self):
        if not self._load_settings():
            # SMTP disabled → delegate everything to console
            self._fallback = ConsoleEmailBackend()
            self._fallback.open()
            return True

        try:
            logger.debug("Opening SMTP connection to %s:%s", self.host, self.port)
            return super().open()
        except Exception:
            logger.exception("Failed to open SMTP connection – falling back to console.")
            self._fallback = ConsoleEmailBackend()
            self._fallback.open()
            return True

    def close(self):
        if self._fallback:
            self._fallback.close()
            self._fallback = None
        else:
            try:
                super().close()
            except Exception:
                pass

    def send_messages(self, email_messages):
        if self._fallback:
            logger.debug("Delegating send_messages to fallback backend: %s", type(self._fallback).__name__)
            return self._fallback.send_messages(email_messages)

        logger.debug("Dispatching %d message(s) via SMTP", len(email_messages))

        # If we haven't opened yet, open now
        if self.connection is None:
            self.open()
            if self._fallback:
                return self._fallback.send_messages(email_messages)

        try:
            return super().send_messages(email_messages)
        except Exception:
            logger.exception("SMTP send_messages failed – falling back to console.")
            fallback = ConsoleEmailBackend()
            return fallback.send_messages(email_messages)
