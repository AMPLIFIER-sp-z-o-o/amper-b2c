import logging
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from allauth.account import app_settings
from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.utils import user_email, user_field
from allauth.headless.adapter import DefaultHeadlessAdapter
from allauth.mfa.models import Authenticator
from django.conf import settings
from django.urls import reverse
from django.utils.html import format_html
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class EmailAsUsernameAdapter(DefaultAccountAdapter):
    """
    Adapter that always sets the username equal to the user's email address.
    Dispatches all outgoing emails through Celery for non-blocking delivery.
    """

    def __init__(self, request=None):
        super().__init__(request)
        # Prevent leaking whether someone is already signed up.
        self.error_messages["email_taken"] = format_html(
            _(
                'An account with this email already exists. <a href="{}" class="link font-semibold hover:underline">Sign in</a> or <a href="{}" class="link font-semibold hover:underline">reset your password</a>.'
            ),
            reverse("account_login"),
            reverse("account_reset_password"),
        )

    def populate_username(self, request, user):
        # override the username population to always use the email
        user_field(user, app_settings.USER_MODEL_USERNAME_FIELD, user_email(user))

    def add_message(
        self,
        request,
        level,
        message_template=None,
        message_context=None,
        extra_tags="",
        message=None,
    ):
        """
        Suppress the "Successfully signed in" toast during signup —
        the "Confirmation email sent" message is sufficient on its own.
        """
        if message_template == "account/messages/logged_in.txt" and getattr(request, "_signup_in_progress", False):
            return
        super().add_message(
            request,
            level,
            message_template=message_template,
            message_context=message_context,
            extra_tags=extra_tags,
            message=message,
        )

    def is_safe_url(self, url: str) -> bool:
        """Tighten allauth's redirect safety.

        The upstream implementation includes hosts from `settings.ALLOWED_HOSTS`.
        In development this is often configured as `*`, which would allow
        open-redirects via `?next=https://evil.example`.

        We only allow:
        - relative URLs (e.g. `/cart/`)
        - absolute URLs pointing to the current host
        """

        from allauth.utils import context
        from django.utils.http import url_has_allowed_host_and_scheme

        request = getattr(self, "request", None) or getattr(context, "request", None)
        if not request:
            return False

        return url_has_allowed_host_and_scheme(
            url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        )

    def post_login(
        self,
        request,
        user,
        *,
        email_verification,
        signal_kwargs,
        email,
        signup,
        redirect_url,
    ):
        if signup:
            request._signup_in_progress = True
        response = super().post_login(
            request,
            user,
            email_verification=email_verification,
            signal_kwargs=signal_kwargs,
            email=email,
            signup=signup,
            redirect_url=redirect_url,
        )
        if signup:
            request._signup_in_progress = False
        return response

    def get_login_redirect_url(self, request):
        """Prevent open-redirects.

        Some environments may configure permissive host settings; we still
        only allow relative URLs or same-host absolute URLs.
        """

        redirect_url = super().get_login_redirect_url(request)
        if not redirect_url:
            return redirect_url

        allowed_hosts = {request.get_host()}
        if url_has_allowed_host_and_scheme(
            redirect_url,
            allowed_hosts=allowed_hosts,
            require_https=request.is_secure(),
        ):
            return redirect_url

        # Fall back to a safe in-site redirect.
        return settings.LOGIN_REDIRECT_URL or "/"

    # ── Async email dispatch via Celery ───────────────────────────────────

    @staticmethod
    def _rewrite_url_with_site_url(url: str, site_url: str) -> str:
        """
        Replace the scheme+host portion of an absolute URL with ``site_url``
        so that email links always point to the real site, not
        ``http://testserver/...`` or ``http://localhost:8000/...``.
        """
        if not url or not site_url:
            return url
        from urllib.parse import urlparse

        parsed = urlparse(url)
        # Only rewrite http(s) URLs with a hostname
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return url
        site_url = site_url.rstrip("/")
        return f"{site_url}{parsed.path}"

    @staticmethod
    def _get_site_base_url(site_url: str) -> str:
        """
        Return a usable base URL for building absolute links in emails.
        Prefers ``site_url`` from SiteSettings; falls back to
        ``settings.PROJECT_METADATA["URL"]``, then ``get_server_root()``
        (built from django.contrib.sites.Site).
        """
        if site_url:
            return site_url.rstrip("/")
        project_url = settings.PROJECT_METADATA.get("URL", "")
        if project_url:
            return str(project_url).rstrip("/")
        try:
            from apps.web.meta import get_server_root

            return get_server_root().rstrip("/")
        except Exception:
            return ""

    @staticmethod
    def _is_local_base_url(url: str) -> bool:
        """Return True for loopback/test hosts that should not leak into user emails."""
        if not url:
            return False
        try:
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
        except Exception:
            return False
        return host in {"localhost", "127.0.0.1", "0.0.0.0", "::1", "testserver"}

    def _get_request_base_url(self) -> str:
        """Build absolute root URL from current request when available.

        Reads from allauth's ContextVar-based request context (allauth ≥ 65).
        """
        try:
            from allauth.core import context as allauth_context

            request = allauth_context.request
        except Exception:
            request = None
        if not request:
            return ""
        try:
            return request.build_absolute_uri("/").rstrip("/")
        except Exception:
            return ""

    def _resolve_email_base_url(self, site_url: str) -> str:
        """Pick the best public URL for email links.

        Prefer explicit non-local configuration. If config is local/test and
        the current request host is public (qa/prod), use the request host.
        """
        configured_base_url = self._get_site_base_url(site_url)
        request_base_url = self._get_request_base_url()

        if configured_base_url and not self._is_local_base_url(configured_base_url):
            return configured_base_url

        if request_base_url and not self._is_local_base_url(request_base_url):
            return request_base_url

        return configured_base_url or request_base_url

    @staticmethod
    def _is_absolute_url(url: str) -> bool:
        if not url:
            return False
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)

    @classmethod
    def _make_absolute_url(cls, url: str, base_url: str) -> str:
        if not url:
            return ""
        if cls._is_absolute_url(url):
            return url
        if not base_url:
            return ""
        base_url = base_url.rstrip("/")
        if not url.startswith("/"):
            url = f"/{url}"
        return f"{base_url}{url}"

    def send_mail(self, template_prefix, email, context):
        """
        Render email templates synchronously, then hand off to Celery
        for non-blocking SMTP delivery.
        """
        from apps.utils.tasks import send_email_task
        from apps.web.models import SiteSettings, SystemSettings

        # Inject extra branding context
        try:
            site_settings = SiteSettings.get_settings()
            logo_url = site_settings.logo_url
            site_url = site_settings.site_url or ""
            store_name = site_settings.store_name or ""
        except Exception:
            logo_url = ""
            site_url = ""
            store_name = ""

        # Resolve the base URL (SiteSettings → django.contrib.sites fallback)
        base_url = self._resolve_email_base_url(site_url)

        # Email clients (Gmail, Outlook) do not support SVG images.
        # Fall back to text-only branding when the logo is SVG.
        if logo_url and logo_url.lower().endswith(".svg"):
            logo_url = ""

        # Make logo_url absolute for emails (relative paths don't work in email clients)
        logo_url = self._make_absolute_url(logo_url, base_url)

        context["logo_url"] = logo_url
        context["site_url"] = base_url or site_url
        # store_name must never be empty — it's used in blocktranslate tags
        context["store_name"] = store_name or settings.PROJECT_METADATA.get("NAME", "Store")
        context["current_year"] = datetime.now().year

        # Rewrite allauth-generated URLs so they use the real site domain
        if base_url:
            for key in ("activate_url", "password_reset_url"):
                if key in context:
                    context[key] = self._rewrite_url_with_site_url(context[key], base_url)

        # Render subject and bodies using allauth's built-in rendering
        msg = self.render_mail(template_prefix, email, context)

        # Determine from_email
        from_email = msg.from_email
        try:
            system_settings = SystemSettings.get_settings()
            if system_settings.smtp_default_from_email:
                from_email = system_settings.smtp_default_from_email
        except Exception:
            pass

        # Extract HTML body if present
        html_body = None
        if msg.alternatives:
            for content, mimetype in msg.alternatives:
                if mimetype == "text/html":
                    html_body = content
                    break

        # Update from_email on the message object (for sync fallback path)
        msg.from_email = from_email

        # Dispatch via Celery if a worker is available, else send synchronously
        use_celery = False
        try:
            from amplifier.celery import app as celery_app

            inspect = celery_app.control.inspect(timeout=1.0)
            active = inspect.active_queues()
            if active:
                use_celery = True
        except Exception:
            pass

        if use_celery:
            try:
                send_email_task.apply_async(
                    kwargs={
                        "subject": msg.subject,
                        "body": msg.body,
                        "from_email": from_email,
                        "recipient_list": [email],
                        "html_message": html_body,
                    },
                    retry=False,
                )
                return
            except Exception:
                logger.warning("Celery dispatch failed — sending email synchronously.", exc_info=True)

        # No Celery worker available or dispatch failed — send synchronously
        self._send_sync(msg)

    @staticmethod
    def _send_sync(msg):
        """Send an email synchronously through the configured backend."""
        from django.core.mail import get_connection

        try:
            backend = get_connection()
            backend.send_messages([msg])
        except Exception:
            logger.exception("Synchronous email send via configured backend failed.")


class NoNewUsersAccountAdapter(DefaultAccountAdapter):
    """
    Adapter that can be used to disable public sign-ups for your app.
    """

    def is_open_for_signup(self, request):
        # see https://stackoverflow.com/a/29799664/8207
        return False


class CustomHeadlessAdapter(DefaultHeadlessAdapter):
    def serialize_user(self, user) -> dict[str, Any]:
        data = super().serialize_user(user)
        data["avatar_url"] = user.avatar_url
        return data


def user_has_valid_totp_device(user) -> bool:
    if not user.is_authenticated:
        return False
    return user.authenticator_set.filter(type=Authenticator.Type.TOTP).exists()
