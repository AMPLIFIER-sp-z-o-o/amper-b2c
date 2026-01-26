"""Admin configuration for the support app.

This module:
1. Unregisters Django Sites admin (managed via SiteSettings model)
2. Configures custom allauth admin classes with Unfold styling
"""

from __future__ import annotations

from django.contrib import admin
from django.contrib.sites.models import Site

# Unregister Django Sites admin - we manage site settings through SiteSettings model
try:
    admin.site.unregister(Site)
except admin.sites.NotRegistered:
    pass

# Unregister allauth's default admin classes before registering our custom ones
from allauth.socialaccount.models import SocialAccount, SocialApp, SocialToken

for model in [SocialApp, SocialAccount, SocialToken]:
    try:
        admin.site.unregister(model)
    except admin.sites.NotRegistered:
        pass

# Import custom allauth admin (this will register the models with our custom classes)
from apps.support import allauth_admin  # noqa: F401, E402
