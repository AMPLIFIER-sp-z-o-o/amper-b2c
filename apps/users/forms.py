import logging

import requests
from allauth.account.forms import LoginForm, SignupForm
from allauth.socialaccount.forms import SignupForm as SocialSignupForm
from django import forms
from django.conf import settings
from django.contrib.auth.forms import UserChangeForm
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from apps.utils.timezones import get_timezones_display

from .models import CustomUser, ShippingAddress


def _validate_turnstile_token(token):
    """Shared Turnstile token validation logic."""
    if not settings.TURNSTILE_SECRET:
        logging.info("No turnstile secret found, not checking captcha")
        return token

    if not token:
        raise forms.ValidationError(_("Missing captcha. Please try again."))

    turnstile_url = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    payload = {
        "secret": settings.TURNSTILE_SECRET,
        "response": token,
    }
    try:
        response = requests.post(turnstile_url, data=payload, timeout=10).json()
        if not response["success"]:
            raise forms.ValidationError(_("Invalid captcha. Please try again."))
    except requests.Timeout:
        raise forms.ValidationError(_("Captcha verification timed out. Please try again.")) from None

    return token


class TurnstileSignupForm(SignupForm):
    """
    Sign up form that includes a turnstile captcha.
    """

    turnstile_token = forms.CharField(widget=forms.HiddenInput(), required=False)

    def clean_turnstile_token(self):
        return _validate_turnstile_token(self.cleaned_data.get("turnstile_token", None))


class TurnstileLoginForm(LoginForm):
    """
    Login form that includes a turnstile captcha.
    """

    turnstile_token = forms.CharField(widget=forms.HiddenInput(), required=False)

    def clean_turnstile_token(self):
        return _validate_turnstile_token(self.cleaned_data.get("turnstile_token", None))


class CustomUserChangeForm(UserChangeForm):
    email = forms.EmailField(label=_("Email"), required=True)
    language = forms.ChoiceField(label=_("Language"))
    timezone = forms.ChoiceField(label=_("Time Zone"), required=False)

    class Meta:
        model = CustomUser
        fields = ("email", "first_name", "last_name", "language", "timezone")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        timezone = self.fields.get("timezone")
        timezone.choices = get_timezones_display()
        if settings.USE_I18N and len(settings.LANGUAGES) > 1:
            language = self.fields.get("language")
            language.choices = settings.LANGUAGES
        else:
            self.fields.pop("language")


class AccountDetailsForm(forms.ModelForm):
    """Form for updating the user's first name on the Account Details page."""

    first_name = forms.CharField(
        label=_("First Name"),
        max_length=150,
        required=False,
    )

    class Meta:
        model = CustomUser
        fields = ("first_name",)


class EmailChangeForm(forms.Form):
    """Form for requesting an email address change."""

    new_email = forms.EmailField(
        label=_("New Email Address"),
        max_length=254,
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_new_email(self):
        new_email = self.cleaned_data["new_email"].lower().strip()
        if new_email == self.user.email.lower():
            raise forms.ValidationError(_("This is already your current email address."))
        if CustomUser.objects.filter(email__iexact=new_email).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError(_("This email address is already in use."))
        return new_email


class DeleteAccountForm(forms.Form):
    """Form for confirming account deletion with password."""

    password = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput,
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise forms.ValidationError(_("Incorrect password. Please try again."))
        return password


class TermsSignupForm(TurnstileSignupForm):
    """Custom signup form to add a checkbox for accepting the terms."""

    first_name = forms.CharField(
        label=_("First Name"),
        max_length=150,
        required=True,
    )
    terms_agreement = forms.BooleanField(required=True)
    # Honeypot to catch bots. Must stay empty.
    phone_number_x = forms.CharField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # blank out overly-verbose help text
        self.fields["password1"].help_text = ""
        link = '<a class="link hover:underline" href="{}" target="_blank">{}</a>'.format(
            reverse("web:terms"),
            _("Terms and Conditions"),
        )
        self.fields["terms_agreement"].label = mark_safe(_("I agree to the {terms_link}").format(terms_link=link))

    def clean_phone_number_x(self):
        value = (self.cleaned_data.get("phone_number_x") or "").strip()
        if value:
            raise forms.ValidationError(_("Invalid signup submission."))
        return ""


class CustomSocialSignupForm(SocialSignupForm):
    """Custom social signup form to work around this issue:
    https://github.com/pennersr/django-allauth/issues/3266."""

    first_name = forms.CharField(
        label=_("First Name"),
        max_length=150,
        required=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.prevent_enumeration = False


class ShippingAddressForm(forms.ModelForm):
    class Meta:
        model = ShippingAddress
        fields = (
            "full_name",
            "phone_country_code",
            "phone_number",
            "shipping_city",
            "shipping_postal_code",
            "shipping_street",
            "shipping_building_number",
            "shipping_apartment_number",
            "is_default",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Keep the prefix stored, but don't expose it as a dropdown in the UI.
        if "phone_country_code" in self.fields:
            self.fields["phone_country_code"].widget = forms.HiddenInput()
            self.fields["phone_country_code"].initial = "+48"

    def clean_full_name(self):
        return (self.cleaned_data.get("full_name") or "").strip()

    def clean_phone_country_code(self):
        value = (self.cleaned_data.get("phone_country_code") or "").strip()
        return value or "+48"

    def clean_phone_number(self):
        return (self.cleaned_data.get("phone_number") or "").strip()

    def clean_shipping_city(self):
        return (self.cleaned_data.get("shipping_city") or "").strip()

    def clean_shipping_postal_code(self):
        return (self.cleaned_data.get("shipping_postal_code") or "").strip()

    def clean_shipping_street(self):
        return (self.cleaned_data.get("shipping_street") or "").strip()

    def clean_shipping_building_number(self):
        return (self.cleaned_data.get("shipping_building_number") or "").strip()

    def clean_shipping_apartment_number(self):
        return (self.cleaned_data.get("shipping_apartment_number") or "").strip()
