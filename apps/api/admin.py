from django.contrib import admin
from rest_framework_api_key.admin import APIKeyModelAdmin

from apps.utils.admin_mixins import HistoryModelAdmin

from .models import UserAPIKey


@admin.register(UserAPIKey)
class UserAPIKeyModelAdmin(HistoryModelAdmin, APIKeyModelAdmin):
    list_display = [*APIKeyModelAdmin.list_display, "user"]
    autocomplete_fields = ["user"]
