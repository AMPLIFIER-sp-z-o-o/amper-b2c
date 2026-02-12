from allauth.account.internal.flows import password_reset as password_reset_flow
from allauth.account.models import EmailAddress
from allauth.account.views import ConfirmEmailView, PasswordChangeView, PasswordResetFromKeyView
from allauth.socialaccount.models import SocialAccount
from django.contrib import messages
from django.contrib.messages import get_messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.api.models import UserAPIKey
from apps.utils.timezones import is_valid_timezone

from .adapter import user_has_valid_totp_device
from .forms import AccountDetailsForm, CustomUserChangeForm, DeleteAccountForm, EmailChangeForm, UploadAvatarForm
from .helpers import require_email_confirmation, user_has_confirmed_email_address
from .models import CustomUser, PendingEmailChange

# Cookie name for storing browser timezone
TIMEZONE_COOKIE_NAME = "amplifier_timezone"


@login_required
def profile(request):
    if request.method == "POST":
        form = CustomUserChangeForm(request.POST, instance=request.user)
        if form.is_valid():
            user = form.save(commit=False)
            user_before_update = CustomUser.objects.get(pk=user.pk)
            need_to_confirm_email = (
                user_before_update.email != user.email
                and require_email_confirmation()
                and not user_has_confirmed_email_address(user, user.email)
            )
            if need_to_confirm_email:
                new_email = user.email
                # don't change it but instead rely on allauth to send a confirmation email.
                # email will be changed by signal when confirmed
                EmailAddress.objects.add_email(request, user, new_email, confirm=True)
                # revert the email to the original value until confirmation is completed
                user.email = user_before_update.email
                # recreate the form to avoid populating the previous email in the returned page
                form = CustomUserChangeForm(instance=user)
            user.save()

            user_language = user.language
            if user_language and user_language != translation.get_language():
                translation.activate(user_language)
            if user.timezone != timezone.get_current_timezone():
                if user.timezone:
                    timezone.activate(user.timezone)
                else:
                    timezone.deactivate()
            messages.success(request, _("Profile successfully saved."))
    else:
        form = CustomUserChangeForm(instance=request.user)
    return render(
        request,
        "account/profile.html",
        {
            "form": form,
            "active_tab": "profile",
            "page_title": _("Profile"),
            "api_keys": request.user.api_keys.filter(revoked=False),
            "social_accounts": SocialAccount.objects.filter(user=request.user),
            "user_has_valid_totp_device": user_has_valid_totp_device(request.user),
            "now": timezone.now(),
            "current_tz": timezone.get_current_timezone(),
        },
    )


@login_required
@require_POST
def upload_profile_image(request):
    user = request.user
    form = UploadAvatarForm(request.POST, request.FILES)
    if form.is_valid():
        user.avatar = request.FILES["avatar"]
        user.save()
        return HttpResponse(_("Success!"))
    else:
        readable_errors = ", ".join(str(error) for key, errors in form.errors.items() for error in errors)
        return JsonResponse(status=403, data={"errors": readable_errors})


@login_required
@require_POST
def create_api_key(request):
    api_key, key = UserAPIKey.objects.create_key(
        name=f"{request.user.get_display_name()[:40]} API Key", user=request.user
    )
    messages.success(
        request,
        _("API Key created. Your key is: {key}. Save this somewhere safe - you will only see it once!").format(
            key=key,
        ),
    )
    return HttpResponseRedirect(reverse("users:user_profile"))


@login_required
@require_POST
def revoke_api_key(request):
    key_id = request.POST.get("key_id")
    api_key = request.user.api_keys.get(id=key_id)
    api_key.revoked = True
    api_key.save()
    messages.success(
        request,
        _("API Key {key} has been revoked. It can no longer be used to access the site.").format(
            key=api_key.prefix,
        ),
    )
    return HttpResponseRedirect(reverse("users:user_profile"))


@csrf_exempt
@require_POST
def set_timezone(request):
    """
    Set the user's timezone from browser detection.
    Works for both authenticated and anonymous users via cookie.
    For authenticated users, also saves to their profile if not already set.
    """
    import json

    try:
        data = json.loads(request.body)
        tz_name = data.get("timezone", "")
    except (json.JSONDecodeError, ValueError):
        tz_name = request.POST.get("timezone", "")

    if not tz_name or not is_valid_timezone(tz_name):
        return JsonResponse({"status": "error", "message": "Invalid timezone"}, status=400)

    response = JsonResponse({"status": "ok", "timezone": tz_name})

    # Set cookie for all users (including anonymous)
    response.set_cookie(
        TIMEZONE_COOKIE_NAME,
        tz_name,
        max_age=365 * 24 * 60 * 60,  # 1 year
        httponly=True,
        samesite="Lax",
    )

    # For authenticated users, save to profile if not already set
    if request.user.is_authenticated and not request.user.timezone:
        request.user.timezone = tz_name
        request.user.save(update_fields=["timezone"])

    return response


@login_required
@require_POST
def resend_verification_email(request):
    """Resend email verification to the current user's primary email."""
    try:
        email_address = EmailAddress.objects.get(user=request.user, email=request.user.email)
        if not email_address.verified:
            email_address.send_confirmation(request)
    except EmailAddress.DoesNotExist:
        # Create the EmailAddress record and send confirmation
        email_address = EmailAddress.objects.add_email(request, request.user, request.user.email, confirm=True)
    return JsonResponse({"status": "ok"})


# ── Account Details & Orders Pages ───────────────────────────────────


@login_required
def account_details(request):
    """Account details page — update first name, manage email, security info."""
    if request.method == "POST":
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        form = AccountDetailsForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            if is_ajax:
                request.user.refresh_from_db()
                return JsonResponse({
                    "status": "ok",
                    "message": str(_("Your details have been updated.")),
                    "first_name": request.user.first_name,
                    "display_name": request.user.get_display_name(),
                })
            messages.success(request, _("Your details have been updated."))
            return redirect("users:account_details")
        else:
            if is_ajax:
                errors = {field: [str(e) for e in errs] for field, errs in form.errors.items()}
                return JsonResponse({"status": "error", "errors": errors}, status=400)
    else:
        form = AccountDetailsForm(instance=request.user)

    # Pending email change
    pending_email = None
    try:
        pending = request.user.pending_email_change
        if not pending.is_expired:
            pending_email = pending
    except PendingEmailChange.DoesNotExist:
        pass

    return render(
        request,
        "account/account_details.html",
        {
            "form": form,
            "active_tab": "details",
            "page_title": _("Account Settings"),
            "pending_email": pending_email,
        },
    )


@login_required
def account_orders(request):
    """Orders page — placeholder for future implementation."""
    return render(
        request,
        "account/account_orders.html",
        {
            "active_tab": "orders",
            "page_title": _("Orders"),
        },
    )


@login_required
@require_POST
def account_delete(request):
    """Delete the current user's account permanently after password verification."""
    from django.contrib.auth import logout

    form = DeleteAccountForm(request.POST, user=request.user)
    if not form.is_valid():
        messages.error(request, form.errors["password"][0] if "password" in form.errors else _("Invalid request."))
        return redirect("users:account_details")

    user = request.user
    logout(request)
    user.delete()
    messages.success(request, _("Your account has been permanently deleted."))
    return redirect("web:home")


@login_required
@require_POST
def account_request_email_change(request):
    """Request an email address change — sends verification to new email."""
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    form = EmailChangeForm(request.POST, user=request.user)
    if not form.is_valid():
        error_msg = str(next(iter(form.errors.values()))[0]) if form.errors else str(_("Invalid email."))
        if is_ajax:
            return JsonResponse({"status": "error", "message": error_msg}, status=400)
        messages.error(request, error_msg)
        return redirect("users:account_details")

    new_email = form.cleaned_data["new_email"]
    pending = PendingEmailChange.create_for_user(request.user, new_email)

    # Send verification email to the new address
    _send_email_change_verification(request, pending)
    # Send notification to old address
    _send_email_change_notification(request, request.user.email, new_email)

    pending.notified_old_email = True
    pending.save(update_fields=["notified_old_email"])

    email_html = format_html("<strong>{}</strong>", new_email)
    msg = format_html(_("Verification link sent to {email}."), email=email_html)
    if is_ajax:
        return JsonResponse({"status": "ok", "message": str(msg), "new_email": new_email})
    messages.success(request, msg)
    return redirect("users:account_details")


@login_required
@require_POST
def account_cancel_email_change(request):
    """Cancel a pending email change."""
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    PendingEmailChange.objects.filter(user=request.user).delete()
    msg = str(_("Email change has been cancelled."))
    if is_ajax:
        return JsonResponse({"status": "ok", "message": msg})
    messages.success(request, msg)
    return redirect("users:account_details")


@login_required
@require_POST
def account_resend_email_change(request):
    """Resend the verification email for a pending email change."""
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    try:
        pending = request.user.pending_email_change
        if pending.is_expired:
            # Refresh the token
            pending = PendingEmailChange.create_for_user(request.user, pending.new_email)
        _send_email_change_verification(request, pending)
        email_html = format_html("<strong>{}</strong>", pending.new_email)
        msg = format_html(_("Verification link resent to {email}."), email=email_html)
        if is_ajax:
            return JsonResponse({"status": "ok", "message": str(msg)})
        messages.success(request, msg)
    except PendingEmailChange.DoesNotExist:
        msg = str(_("No pending email change found."))
        if is_ajax:
            return JsonResponse({"status": "error", "message": msg}, status=400)
        messages.error(request, msg)
    return redirect("users:account_details")


@login_required
def account_confirm_email_change(request, token):
    """Confirm the email change via the verification link."""
    try:
        pending = PendingEmailChange.objects.get(token=token, user=request.user)
    except PendingEmailChange.DoesNotExist:
        messages.error(request, _("Invalid or expired verification link."))
        return redirect("users:account_details")

    if pending.is_expired:
        pending.delete()
        messages.error(request, _("This verification link has expired. Please request a new email change."))
        return redirect("users:account_details")

    # Check if the new email is still available
    if CustomUser.objects.filter(email__iexact=pending.new_email).exclude(pk=request.user.pk).exists():
        pending.delete()
        messages.error(request, _("This email address is already in use by another account."))
        return redirect("users:account_details")

    # Apply the change
    old_email = request.user.email
    request.user.email = pending.new_email
    request.user.username = pending.new_email  # Keep username in sync
    request.user.save(update_fields=["email", "username"])

    # Update allauth EmailAddress records
    EmailAddress.objects.filter(user=request.user, email=old_email).delete()
    EmailAddress.objects.update_or_create(
        user=request.user,
        email=pending.new_email,
        defaults={"verified": True, "primary": True},
    )

    pending.delete()

    email_html = format_html("<strong>{}</strong>", pending.new_email)
    messages.success(request, format_html(_("Your email has been changed to {email}."), email=email_html))
    return redirect("users:account_details")


def _send_email_change_verification(request, pending):
    """Send the verification email to the new email address."""
    from apps.users.adapter import EmailAsUsernameAdapter

    adapter = EmailAsUsernameAdapter(request)
    confirm_url = request.build_absolute_uri(
        reverse("users:account_confirm_email_change", args=[pending.token])
    )
    context = {
        "confirm_url": confirm_url,
        "new_email": pending.new_email,
        "user": pending.user,
        "expiry_hours": 24,
    }
    adapter.send_mail(
        "account/email/email_change_verify",
        pending.new_email,
        context,
    )


def _send_email_change_notification(request, old_email, new_email):
    """Send notification to old email about the email change request."""
    from apps.users.adapter import EmailAsUsernameAdapter

    adapter = EmailAsUsernameAdapter(request)
    context = {
        "old_email": old_email,
        "new_email": new_email,
    }
    adapter.send_mail(
        "account/email/email_change_notify",
        old_email,
        context,
    )


# ── Custom Password Change View (redirect to account details) ────────


class CustomPasswordChangeView(PasswordChangeView):
    """Override allauth's PasswordChangeView so that after a successful
    password change the user is redirected back to the referring page
    (respecting the ?next= query parameter) instead of staying on the form."""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["back_url"] = self.request.GET.get(
            "next",
            reverse("users:account_details") + "#security-section",
        )
        return ctx

    def get_success_url(self):
        next_url = self.request.GET.get("next")
        if next_url:
            return next_url
        return reverse("users:account_details") + "#security-section"


# ── Custom Email Confirmation View (auto-login) ──────────────────────


class AutoLoginConfirmEmailView(ConfirmEmailView):
    """Override allauth's ConfirmEmailView to always auto-login the user
    whose email was just confirmed, regardless of session state."""

    def post(self, *args, **kwargs):
        self.object = verification = self.get_object()
        from allauth.account.internal.flows import email_verification

        email_address, response = email_verification.verify_email_and_resume(
            self.request, verification
        )
        if response:
            return response
        if not email_address:
            return self.respond(False)

        # Force-login the user whose email was just confirmed
        user = email_address.user
        if not self.request.user.is_authenticated or self.request.user.pk != user.pk:
            # Log out any currently logged-in user
            self.logout()
            # Hack: set backend attribute required by Django's login()
            backend = getattr(user, "backend", None)
            if not backend:
                from django.conf import settings as django_settings

                user.backend = django_settings.AUTHENTICATION_BACKENDS[0]
            auth_login(self.request, user)

        # Replace the default confirmation message so the email can be emphasized.
        for _msg in get_messages(self.request):
            pass
        email_html = format_html("<strong>{}</strong>", email_address.email)
        messages.success(self.request, format_html(_("You have confirmed {email}."), email=email_html))

        return redirect("/")


# ── Custom Password Reset From Key View (redirect to home) ──────────


class AutoLoginPasswordResetFromKeyView(PasswordResetFromKeyView):
    """Override allauth's PasswordResetFromKeyView so that after a
    successful password change the user is logged in and redirected to
    the homepage with a toast, instead of showing a separate 'done' page."""

    def form_valid(self, form):
        form.save()
        resp = password_reset_flow.finalize_password_reset(
            self.request, self.reset_user
        )
        if resp:
            return resp
        # Fallback: auto-login manually and redirect home
        user = self.reset_user
        backend = getattr(user, "backend", None)
        if not backend:
            from django.conf import settings as django_settings

            user.backend = django_settings.AUTHENTICATION_BACKENDS[0]
        auth_login(self.request, user)
        messages.success(self.request, _("Your password has been changed successfully."))
        return redirect("/")
