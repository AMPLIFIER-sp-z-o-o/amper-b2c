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

from .helpers import validate_profile_picture
from .models import CustomUser


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


class UploadAvatarForm(forms.Form):
    avatar = forms.FileField(validators=[validate_profile_picture])


class TermsSignupForm(TurnstileSignupForm):
    """Custom signup form to add a checkbox for accepting the terms."""

    terms_agreement = forms.BooleanField(required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # blank out overly-verbose help text
        self.fields["password1"].help_text = ""
        link = '<a class="link hover:underline" href="{}" target="_blank">{}</a>'.format(
            reverse("web:terms"),
            _("Terms and Conditions"),
        )
        self.fields["terms_agreement"].label = mark_safe(_("I agree to the {terms_link}").format(terms_link=link))


class CustomSocialSignupForm(SocialSignupForm):
    """Custom social signup form to work around this issue:
    https://github.com/pennersr/django-allauth/issues/3266."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.prevent_enumeration = False
