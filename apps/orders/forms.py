from django import forms
from django.utils.translation import gettext_lazy as _


class CheckoutDetailsForm(forms.Form):
    full_name = forms.CharField(label=_('Full name'), max_length=255, required=True)
    email = forms.EmailField(label=_('Email'), required=True)
    phone = forms.CharField(label=_('Phone'), max_length=50, required=False)

    shipping_country = forms.CharField(label=_('Country'), max_length=120, required=True)
    shipping_city = forms.CharField(label=_('City'), max_length=120, required=True)
    shipping_address = forms.CharField(label=_('Shipping address'), max_length=255, required=True)

    def clean_email(self):
        return (self.cleaned_data['email'] or '').strip().lower()

    def clean_full_name(self):
        return (self.cleaned_data['full_name'] or '').strip()

    def clean_shipping_country(self):
        return (self.cleaned_data['shipping_country'] or '').strip()

    def clean_shipping_city(self):
        return (self.cleaned_data['shipping_city'] or '').strip()

    def clean_shipping_address(self):
        return (self.cleaned_data['shipping_address'] or '').strip()
