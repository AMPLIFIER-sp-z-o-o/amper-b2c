from django.contrib import sitemaps
from django.urls import reverse

from apps.web.models import DynamicPage

from .meta import get_protocol


class StaticViewSitemap(sitemaps.Sitemap):
    """
    Sitemap for serving any static content you want.
    """

    @property
    def protocol(self):
        return get_protocol()

    def items(self):
        # add any urls (by name) for static content you want to appear in your sitemap to this list
        return [
            "web:home",
        ]

    def location(self, item):
        return reverse(item)


class DynamicPageSitemap(sitemaps.Sitemap):
    """Sitemap for CMS-managed dynamic pages."""

    @property
    def protocol(self):
        return get_protocol()

    def items(self):
        return DynamicPage.objects.filter(is_active=True, exclude_from_sitemap=False)

    def lastmod(self, obj):
        return obj.updated_at
