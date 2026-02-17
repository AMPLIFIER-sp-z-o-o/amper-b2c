from django import forms
from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group, Permission
from django.utils.translation import gettext_lazy as _
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from unfold.contrib.import_export.forms import ExportForm, ImportForm

from apps.utils.admin_mixins import HistoryModelAdmin

from .models import CustomUser

# Unregister default Group admin and re-register with search_fields for autocomplete
try:
    admin.site.unregister(Group)
except admin.sites.NotRegistered:
    pass


@admin.register(Group)
class CustomGroupAdmin(HistoryModelAdmin, GroupAdmin):
    search_fields = ["name"]


@admin.register(Permission)
class PermissionAdmin(HistoryModelAdmin):
    search_fields = ["name", "codename", "content_type__app_label", "content_type__model"]
    list_display = ["name", "codename", "content_type"]
    list_filter = ["content_type__app_label"]
    ordering = ["content_type__app_label", "codename"]


class CustomUserResource(resources.ModelResource):
    class Meta:
        model = CustomUser
        fields = (
            "id",
            "email",
            "first_name",
            "is_active",
            "is_staff",
            "is_superuser",
            "date_joined",
            "last_login",
        )
        export_order = fields
        import_id_fields = ["id"]
        # Exclude password from exports for security
        exclude = ("password",)


class CustomUserAdminCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ("email", "first_name")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "username" in self.fields:
            self.fields["username"].widget = forms.HiddenInput()
            self.fields["username"].required = False
        self.fields["email"].required = True
        self.fields["first_name"].required = True

    def clean(self):
        cleaned_data = super().clean()
        email = (cleaned_data.get("email") or "").strip().lower()
        if email:
            cleaned_data["username"] = email
            self.cleaned_data["username"] = email
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if email:
            user.username = email
            user.email = email
        user.last_name = ""
        if commit:
            user.save()
            self.save_m2m()
        return user


@admin.register(CustomUser)
class CustomUserAdmin(HistoryModelAdmin, UserAdmin, ImportExportModelAdmin):
    resource_class = CustomUserResource
    add_form = CustomUserAdminCreationForm
    import_form_class = ImportForm
    export_form_class = ExportForm
    list_display = ("email", "first_name", "is_staff", "date_joined")
    list_filter = ("is_staff", "is_superuser", "is_active", "groups", "date_joined")
    list_per_page = 50
    show_full_result_count = False
    search_fields = ("email", "first_name")
    ordering = ("-date_joined",)
    autocomplete_fields = ("groups", "user_permissions")
    fieldsets = (
        (None, {"fields": ("email", "first_name", "password")}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "first_name", "password1", "password2"),
            },
        ),
    )

    class Media:
        css = {
            "all": ["css/admin_product_image_inline.css"],
        }
