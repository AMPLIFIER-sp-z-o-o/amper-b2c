from allauth.account.internal.flows import password_reset as password_reset_flow
from allauth.account.models import EmailAddress
from allauth.account.views import ConfirmEmailView, PasswordResetFromKeyView
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
from .forms import CustomUserChangeForm, UploadAvatarForm
from .helpers import require_email_confirmation, user_has_confirmed_email_address
from .models import CustomUser

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
