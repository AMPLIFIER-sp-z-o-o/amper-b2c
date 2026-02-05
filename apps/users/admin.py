from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group, Permission
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
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "is_staff",
            "is_superuser",
            "date_joined",
            "last_login",
            "language",
            "timezone",
        )
        export_order = fields
        import_id_fields = ["id"]
        # Exclude password from exports for security
        exclude = ("password",)


@admin.register(CustomUser)
class CustomUserAdmin(HistoryModelAdmin, UserAdmin, ImportExportModelAdmin):
    resource_class = CustomUserResource
    import_form_class = ImportForm
    export_form_class = ExportForm
    list_display = ("username", "email", "first_name", "last_name", "is_staff", "date_joined")
    list_filter = ("is_staff", "is_superuser", "is_active", "groups", "date_joined")
    list_per_page = 50
    show_full_result_count = False
    search_fields = ("email", "first_name", "last_name")
    ordering = ("-date_joined",)
    autocomplete_fields = ("groups", "user_permissions")

    class Media:
        css = {
            "all": ["css/admin_product_image_inline.css"],
        }

    fieldsets = UserAdmin.fieldsets + (
        (
            "Custom Fields",
            {
                "fields": (
                    "avatar",
                    "language",
                    "timezone",
                )
            },
        ),
    )  # type: ignore

    def formfield_for_dbfield(self, db_field, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, **kwargs)
        if db_field.name == "avatar":
            formfield.widget.attrs["data-product-image-upload"] = "true"
        return formfield
