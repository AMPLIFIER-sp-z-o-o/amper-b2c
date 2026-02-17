from django import forms
from django.utils.translation import gettext_lazy as _


class CheckoutDetailsForm(forms.Form):
    first_name = forms.CharField(label=_("First name"), max_length=150, required=True)
    last_name = forms.CharField(label=_("Last name"), max_length=150, required=True)
    company = forms.CharField(label=_("Company"), max_length=255, required=False)

    phone_country_code = forms.CharField(label=_("Country code"), max_length=10, required=True)
    phone_number = forms.CharField(label=_("Mobile phone"), max_length=50, required=True)

    email = forms.EmailField(label=_("Email"), required=True)

    shipping_city = forms.CharField(label=_("City"), max_length=120, required=True)
    shipping_postal_code = forms.CharField(label=_("Postal code"), max_length=20, required=True)
    shipping_street = forms.CharField(label=_("Street"), max_length=255, required=True)
    shipping_building_number = forms.CharField(label=_("Building number"), max_length=30, required=True)
    shipping_apartment_number = forms.CharField(label=_("Apartment number"), max_length=30, required=False)

    def clean_email(self):
        return (self.cleaned_data['email'] or '').strip().lower()

    def clean_first_name(self):
        return (self.cleaned_data.get("first_name") or "").strip()

    def clean_last_name(self):
        return (self.cleaned_data.get("last_name") or "").strip()

    def clean_company(self):
        return (self.cleaned_data.get("company") or "").strip()

    def clean_phone_country_code(self):
        value = (self.cleaned_data.get("phone_country_code") or "").strip()
        return value

    def clean_phone_number(self):
        return (self.cleaned_data.get("phone_number") or "").strip()

    def clean_shipping_city(self):
        return (self.cleaned_data['shipping_city'] or '').strip()

    def clean_shipping_postal_code(self):
        return (self.cleaned_data.get("shipping_postal_code") or "").strip()

    def clean_shipping_street(self):
        return (self.cleaned_data.get("shipping_street") or "").strip()

    def clean_shipping_building_number(self):
        return (self.cleaned_data.get("shipping_building_number") or "").strip()

    def clean_shipping_apartment_number(self):
        return (self.cleaned_data.get("shipping_apartment_number") or "").strip()

    def get_full_name(self) -> str:
        first = (self.cleaned_data.get("first_name") or "").strip()
        last = (self.cleaned_data.get("last_name") or "").strip()
        return (" ".join([p for p in (first, last) if p])).strip()

    def get_phone_display(self) -> str:
        code = (self.cleaned_data.get("phone_country_code") or "").strip()
        num = (self.cleaned_data.get("phone_number") or "").strip()
        return (" ".join([p for p in (code, num) if p])).strip()

    def get_address_line(self) -> str:
        street = (self.cleaned_data.get("shipping_street") or "").strip()
        building = (self.cleaned_data.get("shipping_building_number") or "").strip()
        apt = (self.cleaned_data.get("shipping_apartment_number") or "").strip()
        if apt:
            return f"{street} {building}/{apt}".strip()
        return f"{street} {building}".strip()
