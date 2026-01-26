from django.contrib import admin
from rest_framework_api_key.admin import APIKeyModelAdmin
from unfold.admin import ModelAdmin

from .models import UserAPIKey


@admin.register(UserAPIKey)
class UserAPIKeyModelAdmin(ModelAdmin, APIKeyModelAdmin):
    list_display = [*APIKeyModelAdmin.list_display, "user"]
    autocomplete_fields = ["user"]
