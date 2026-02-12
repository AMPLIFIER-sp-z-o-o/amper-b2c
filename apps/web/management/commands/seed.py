"""
Seed command for populating the database with predefined data.

It populates the current database with site settings, categories, products, etc.

Credentials loaded from environment variables (.env file):
- AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY -> MediaStorageSettings
- GOOGLE_CLIENT_ID, GOOGLE_SECRET_ID -> SocialApp (Google OAuth)
- SMTP_PASSWORD -> SystemSettings (SendGrid API key)

Default superuser:
- Email: admin@example.com
- Password: admin

Usage:
    uv run manage.py seed
    uv run manage.py seed --skip-users  # Skip superuser creation
"""

import os
import re
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialApp
from django.conf import settings
from django.contrib.sites.models import Site
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.dateparse import parse_datetime

from apps.catalog.models import (
    AttributeDefinition,
    AttributeOption,
    Category,
    CategoryBanner,
    CategoryRecommendedProduct,
    Product,
    ProductAttributeValue,
    ProductImage,
)
from apps.homepage.models import (
    Banner,
    BannerGroup,
    BannerSettings,
    BannerType,
    HomepageSection,
    HomepageSectionBanner,
    HomepageSectionCategoryBox,
    HomepageSectionCategoryItem,
    HomepageSectionProduct,
)
from apps.media.models import MediaStorageSettings
from apps.users.models import CustomUser, SocialAppSettings
from apps.web.models import (
    BottomBar,
    BottomBarLink,
    CustomCSS,
    DynamicPage,
    Footer,
    FooterSection,
    FooterSectionLink,
    FooterSocialMedia,
    Navbar,
    NavbarItem,
    SiteSettings,
    SystemSettings,
    TopBar,
)

# Site domain is read from SITE_DOMAIN env var (default: localhost:8000).
# On QA/production, set e.g. SITE_DOMAIN=amper-b2c.ampliapps.com
_SITE_DOMAIN = os.environ.get("SITE_DOMAIN", "localhost:8000")
_SITE_SCHEME = "http" if _SITE_DOMAIN.startswith("localhost") else "https"
_SITE_URL = f"{_SITE_SCHEME}://{_SITE_DOMAIN}"

SITES_DATA = [{"id": 1, "domain": _SITE_DOMAIN, "name": "AMPLFIER sp. z o.o."}]

TOPBAR_DATA = [
    {
        "id": 1,
        "name": "Promocja letnia",
        "singleton_key": 1,
        "content_type": "standard",
        "background_color": "#1A56DB",
        "text": "Letnia wyprzedaż! -20% na wszystkie produkty z kodem LATO2026",
        "link_label": "Zobacz ofertę",
        "link_url": "https://www.google.pl",
        "custom_html": '<div class="countdown-container"><h3>Promocja kończy się za:</h3><div class="countdown-timer" id="topbar-countdown"><div class="countdown-item"><span class="countdown-value" id="countdown-hours">00</span> <span class="countdown-label">godzin</span></div><div class="countdown-separator">:</div><div class="countdown-item"><span class="countdown-value" id="countdown-minutes">00</span> <span class="countdown-label">minut</span></div><div class="countdown-separator">:</div><div class="countdown-item"><span class="countdown-value" id="countdown-seconds">00</span> <span class="countdown-label">sekund</span></div></div></div>',
        "custom_css": """.countdown-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 10px 15px;
  background: linear-gradient(90deg, #ff6b6b, #ee5a5a);
  color: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  text-align: center;
}

.countdown-container h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}

.countdown-timer {
  display: flex;
  align-items: center;
  gap: 6px;
  animation: pulse 2s infinite ease-in-out;
}

.countdown-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  background: rgba(0, 0, 0, 0.2);
  padding: 5px 8px;
  border-radius: 4px;
}

.countdown-value {
  font-size: 18px;
  font-weight: bold;
  font-variant-numeric: tabular-nums;
}

.countdown-label {
  font-size: 9px;
  text-transform: uppercase;
  opacity: 0.9;
}

.countdown-separator {
  font-size: 18px;
  font-weight: bold;
}

@keyframes pulse {
  0%,
  100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.05);
  }
}""",
        "custom_js": """(function() {
  const endTime = new Date().getTime() + (2 * 60 * 60 * 1000);
  
  function updateCountdown() {
    const now = new Date().getTime();
    const distance = endTime - now;
    
    if (distance < 0) {
      const container = document.getElementById('topbar-countdown');
      if (container) container.innerHTML = '<span>Promocja zakończona!</span>';
      return;
    }
    
    const hours = Math.floor(distance / (1000 * 60 * 60));
    const minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
    const seconds = Math.floor((distance % (1000 * 60)) / 1000);
    
    const h = document.getElementById('countdown-hours');
    const m = document.getElementById('countdown-minutes');
    const s = document.getElementById('countdown-seconds');
    
    if (h) h.textContent = hours.toString().padStart(2, '0');
    if (m) m.textContent = minutes.toString().padStart(2, '0');
    if (s) s.textContent = seconds.toString().padStart(2, '0');
  }
  
  updateCountdown();
  setInterval(updateCountdown, 1000);
  console.log('Countdown timer initialized!');
})();""",
        "is_active": True,
        "available_from": None,
        "available_to": None,
        "order": 0,
    }
]

CUSTOM_CSS_DATA = [
    {
        "id": 1,
        "custom_css": """/* Top bar styles */
#top-bar-standard  {
  background-color: #1a56db;
}""",
        "custom_css_active": True,
    }
]

SITE_SETTINGS_DATA = [
    {
        "id": 1,
        "store_name": "AMPER",
        "site_url": _SITE_URL,
        "description": "Your one-stop shop for quality products.",
        "keywords": "e-commerce, amper, shop",
        "default_image": "",
        "currency": "PLN",
        "logo": "site/amper-b2c-logo.png",
    }
]

SYSTEM_SETTINGS_DATA = [
    {
        "id": 1,
        "smtp_host": "smtp.sendgrid.net",
        "smtp_port": 587,
        "smtp_username": "apikey",
        "smtp_use_tls": True,
        "smtp_use_ssl": False,
        "smtp_default_from_email": "noreply@ampliapps.com",
        "smtp_timeout": 30,
        "smtp_enabled": True,
        "turnstile_enabled": False,
    }
]

DYNAMIC_PAGES_DATA = [
    {
        "id": 1,
        "name": "Privacy Policy",
        "slug": "privacy-policy",
        "meta_title": "Privacy Policy",
        "meta_description": "Read our privacy policy for details on data processing.",
        "is_active": True,
        "exclude_from_sitemap": False,
        "seo_noindex": False,
        "content": "<p>Privacy policy content goes here.</p>",
    },
    {
        "id": 2,
        "name": "Promotions",
        "slug": "promotions",
        "meta_title": "Promotions",
        "meta_description": "Browse the latest promotions and special offers.",
        "is_active": True,
        "exclude_from_sitemap": False,
        "seo_noindex": False,
        "content": "<p>Promotions content goes here.</p>",
    },
]

NAVBAR_DATA = [
    {
        "id": 1,
        "singleton_key": 1,
        "mode": "custom",
    }
]

FOOTER_DATA = [
    {
        "id": 1,
        "singleton_key": 1,
        "content_type": "custom",
        "custom_html": """<div class="footer-sections"><div class="footer-section"><h6 class="footer-section-title">Test Section2</h6><ul class="footer-section-links"><li><a class="footer-link" href="/about/">About Us</a></li><li><a class="footer-link" href="/contact/">Contact</a></li></ul></div><div class="footer-section"><h6 class="footer-section-title">Shop</h6><ul class="footer-section-links"><li><a class="footer-link" href="/">Catalog</a></li><li><a class="footer-link" href="/">New Arrivals</a></li><li><a class="footer-link" href="/">Best Sellers</a></li><li><a class="footer-link" href="/dynamic-page/promotions/2/">Promotions</a></li><li><a class="footer-link" href="/">Deals</a></li></ul></div><div class="footer-section"><h6 class="footer-section-title">Support</h6><ul class="footer-section-links"><li><a class="footer-link" href="/">Help Center</a></li><li><a class="footer-link" href="/">Contact Us</a></li><li><a class="footer-link" href="/">Shipping</a></li><li><a class="footer-link" href="/">Returns</a></li></ul></div><div class="footer-section"><h6 class="footer-section-title">Company</h6><ul class="footer-section-links"><li><a class="footer-link" href="/">About Us</a></li><li><a class="footer-link" href="/">Careers</a></li><li><a class="footer-link" href="/">Press</a></li><li><a class="footer-link" href="/">Blog</a></li></ul></div><div class="footer-section"><h6 class="footer-section-title">Legal</h6><ul class="footer-section-links"><li><a class="footer-link" href="/">Privacy Policy</a></li><li><a class="footer-link" href="/">Terms of Service</a></li><li><a class="footer-link" href="/">Cookie Policy</a></li><li><a class="footer-link" href="/">Sitemap</a></li></ul></div><div class="footer-section"><h6 class="footer-section-title">Resources</h6><ul class="footer-section-links"><li><a class="footer-link" href="/">Documentation</a></li><li><a class="footer-link" href="/">API Reference</a></li><li><a class="footer-link" href="/">Community</a></li><li><a class="footer-link" href="/">Partners</a></li></ul></div><div class="footer-section"><h6 class="footer-section-title">Account</h6><ul class="footer-section-links"><li><a class="footer-link" href="/users/profile/">My Profile</a></li><li><a class="footer-link" href="/">My Orders</a></li><li><a class="footer-link" href="/">Wishlist</a></li><li><a class="footer-link" href="/">Settings</a></li></ul></div><div class="footer-section"><h6 class="footer-section-title">Social Media</h6><ul class="footer-section-links"><li><a class="footer-social-link" target="_blank" rel="noopener noreferrer" href="https://facebook.com"><svg class="footer-social-icon" fill="currentColor" viewbox="0 0 24 24" aria-hidden="true"><path fill-rule="evenodd" d="M22 12c0-5.523-4.477-10-10-10S2 6.477 2 12c0 4.991 3.657 9.128 8.438 9.878v-6.987h-2.54V12h2.54V9.797c0-2.506 1.492-3.89 3.777-3.89 1.094 0 2.238.195 2.238.195v2.46h-1.26c-1.243 0-1.63.771-1.63 1.562V12h2.773l-.443 2.89h-2.33v6.988C18.343 21.128 22 16.991 22 12z" clip-rule="evenodd"></path></svg>Facebook</a></li><li><a class="footer-social-link" target="_blank" rel="noopener noreferrer" href="https://youtube.com"><svg class="footer-social-icon" fill="currentColor" viewbox="0 0 24 24" aria-hidden="true"><path fill-rule="evenodd" d="M19.812 5.418c.861.23 1.538.907 1.768 1.768C21.998 8.746 22 12 22 12s0 3.255-.418 4.814a2.504 2.504 0 0 1-1.768 1.768c-1.56.419-7.814.419-7.814.419s-6.255 0-7.814-.419a2.505 2.505 0 0 1-1.768-1.768C2 15.255 2 12 2 12s0-3.255.418-4.814a2.507 2.507 0 0 1 1.768-1.768C5.746 5 12 5 12 5s6.255 0 7.814.418zM15.194 12 10 15V9l5.194 3z" clip-rule="evenodd"></path></svg>YouTube</a></li><li><a class="footer-social-link" target="_blank" rel="noopener noreferrer" href="https://instagram.com"><svg class="footer-social-icon" fill="currentColor" viewbox="0 0 24 24" aria-hidden="true"><path fill-rule="evenodd" d="M12.315 2c2.43 0 2.784.013 3.808.06 1.064.049 1.791.218 2.427.465a4.902 4.902 0 011.772 1.153 4.902 4.902 0 011.153 1.772c.247.636.416 1.363.465 2.427.048 1.067.06 1.407.06 4.123v.08c0 2.643-.012 2.987-.06 4.043-.049 1.064-.218 1.791-.465 2.427a4.902 4.902 0 01-1.153 1.772 4.902 4.902 0 01-1.772 1.153c-.636.247-1.363.416-2.427.465-1.067.048-1.407.06-4.123.06h-.08c-2.643 0-2.987-.012-4.043-.06-1.064-.049-1.791-.218-2.427-.465a4.902 4.902 0 01-1.772-1.153 4.902 4.902 0 01-1.153-1.772c-.247-.636-.416-1.363-.465-2.427-.047-1.024-.06-1.379-.06-3.808v-.63c0-2.43.013-2.784.06-3.808.049-1.064.218-1.791.465-2.427a4.902 4.902 0 011.153-1.772A4.902 4.902 0 015.45 2.525c.636-.247 1.363-.416 2.427-.465C8.901 2.013 9.256 2 11.685 2h.63zm-.081 1.802h-.468c-2.456 0-2.784.011-3.807.058-.975.045-1.504.207-1.857.344-.467.182-.8.398-1.15.748-.35.35-.566.683-.748 1.15-.137.353-.3.882-.344 1.857-.047 1.023-.058 1.351-.058 3.807v.468c0 2.456.011 2.784.058 3.807.045.975.207 1.504.344 1.857.182.466.399.8.748 1.15.35.35.683.566 1.15.748.353.137.882.3 1.857.344 1.054.048 1.37.058 4.041.058h.08c2.597 0 2.917-.01 3.96-.058.976-.045 1.505-.207 1.858-.344.466-.182.8-.398 1.15-.748.35-.35.566-.683.748-1.15.137-.353.3-.882.344-1.857.048-1.055.058-1.37.058-4.041v-.08c0-2.597-.01-2.917-.058-3.96-.045-.976-.207-1.505-.344-1.858a3.097 3.097 0 00-.748-1.15 3.098 3.098 0 00-1.15-.748c-.353-.137-.882-.3-1.857-.344-1.023-.047-1.351-.058-3.807-.058zM12 6.865a5.135 5.135 0 110 10.27 5.135 5.135 0 010-10.27zm0 1.802a3.333 3.333 0 100 6.666 3.333 3.333 0 000-6.666zm5.338-3.205a1.2 1.2 0 110 2.4 1.2 1.2 0 010-2.4z" clip-rule="evenodd"></path></svg>Instagram</a></li><li><a class="footer-social-link" target="_blank" rel="noopener noreferrer" href="https://twitter.com"><svg class="footer-social-icon" fill="currentColor" viewbox="0 0 24 24" aria-hidden="true"><path d="M8.29 20.251c7.547 0 11.675-6.253 11.675-11.675 0-.178 0-.355-.012-.53A8.348 8.348 0 0022 5.92a8.19 8.19 0 01-2.357.646 a4.118 4.118 0 001.804-2.27 8.224 8.224 0 01-2.605.996 a4.107 4.107 0 00-6.993 3.743 a11.65 11.65 0 01-8.457-4.287 a4.106 4.106 0 001.27 5.477 a4.072 4.072 0 01-1.991-.551 v.052 a4.105 4.105 0 003.292 4.022 a4.095 4.095 0 01-1.853.07 a4.108 4.108 0 003.834 2.85 A8.233 8.233 0 012 18.407 a11.616 11.616 0 006.29 1.84"></path></svg>Twitter</a></li><li><a class="footer-social-link" target="_blank" rel="noopener noreferrer" href="https://tiktok.com"><svg class="footer-social-icon" fill="currentColor" viewbox="0 0 24 24" aria-hidden="true"><path d="M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z"></path></svg>TikTok&nbsp;</a></li></ul></div></div>""",
        "custom_css": """/* Custom footer helpers */
.footer-sections {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1.5rem;
  padding: 1.5rem 0;
  border-bottom: 1px solid #e5e7eb;
}

@media (min-width: 768px) {
  .footer-sections {
    gap: 2rem;
    padding: 2rem 0;
  }
}

@media (min-width: 1024px) {
  .footer-sections {
    grid-template-columns: repeat(4, 1fr);
    padding: 4rem 0;
  }
}

@media (min-width: 1280px) {
  .footer-sections {
    grid-template-columns: repeat(5, 1fr);
  }
}

.footer-section {
  min-width: 0;
}

.footer-section-title {
  font-size: 0.875rem;
  font-weight: 600;
  text-transform: uppercase;
  color: #111827;
  margin-bottom: 1rem;
  letter-spacing: 0.025em;
}

.footer-section-links {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.footer-link {
  color: #4b5563;
  text-decoration: none;
  transition: color 0.15s ease;
}

.footer-link:hover {
  color: #111827;
}

.footer-social-link {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: #4b5563;
  text-decoration: none;
  transition: color 0.15s ease;
}

.footer-social-link:hover {
  color: #111827;
}

.footer-social-icon {
  width: 1.25rem;
  height: 1.25rem;
  flex-shrink: 0;
}

/* Only apply dark mode overrides if .dark class is explicitly present on a parent */
.dark .footer-sections {
  border-bottom-color: #374151;
}

.dark .footer-section-title {
  color: #ffffff;
}

.dark .footer-link,
.dark .footer-social-link {
  color: #9ca3af;
}

.dark .footer-link:hover,
.dark .footer-social-link:hover {
  color: #ffffff;
}""",
        "custom_js": "",
        "is_active": True,
    }
]

FOOTER_SECTIONS_DATA = [
    {"id": 1, "footer_id": 1, "name": "Test Section", "order": 0},
    {"id": 2, "footer_id": 1, "name": "Shop", "order": 0},
    {"id": 3, "footer_id": 1, "name": "Support", "order": 0},
    {"id": 4, "footer_id": 1, "name": "Company", "order": 0},
    {"id": 5, "footer_id": 1, "name": "Legal", "order": 0},
    {"id": 6, "footer_id": 1, "name": "Resources", "order": 0},
    {"id": 7, "footer_id": 1, "name": "Account", "order": 0},
]

FOOTER_SECTION_LINKS_DATA = [
    {"id": 1, "section_id": 1, "label": "About Us", "url": "/about/", "order": 0},
    {"id": 2, "section_id": 1, "label": "Contact", "url": "/contact/", "order": 1},
    {"id": 3, "section_id": 2, "label": "Catalog", "url": "/", "order": 0},
    {"id": 4, "section_id": 2, "label": "New Arrivals", "url": "/", "order": 1},
    {"id": 5, "section_id": 2, "label": "Best Sellers", "url": "/", "order": 2},
    {"id": 6, "section_id": 2, "label": "Deals", "url": "/", "order": 3},
    {
        "id": 27,
        "section_id": 2,
        "label": "Promotions",
        "url": "/dynamic-page/promotions/2/",
        "link_type": "custom_url",
        "order": 4,
    },
    {"id": 7, "section_id": 3, "label": "Help Center", "url": "/", "order": 0},
    {"id": 8, "section_id": 3, "label": "Contact Us", "url": "/", "order": 1},
    {"id": 9, "section_id": 3, "label": "Shipping", "url": "/", "order": 2},
    {"id": 10, "section_id": 3, "label": "Returns", "url": "/", "order": 3},
    {"id": 11, "section_id": 4, "label": "About Us", "url": "/", "order": 0},
    {"id": 12, "section_id": 4, "label": "Careers", "url": "/", "order": 1},
    {"id": 13, "section_id": 4, "label": "Press", "url": "/", "order": 2},
    {"id": 14, "section_id": 4, "label": "Blog", "url": "/", "order": 3},
    {
        "id": 15,
        "section_id": 5,
        "label": "Privacy Policy",
        "url": "/dynamic-page/privacy-policy/1/",
        "link_type": "custom_url",
        "order": 0,
    },
    {"id": 16, "section_id": 5, "label": "Terms of Service", "url": "/", "order": 1},
    {"id": 17, "section_id": 5, "label": "Cookie Policy", "url": "/", "order": 2},
    {"id": 18, "section_id": 5, "label": "Sitemap", "url": "/", "order": 3},
    {"id": 19, "section_id": 6, "label": "Documentation", "url": "/", "order": 0},
    {"id": 20, "section_id": 6, "label": "API Reference", "url": "/", "order": 1},
    {"id": 21, "section_id": 6, "label": "Community", "url": "/", "order": 2},
    {"id": 22, "section_id": 6, "label": "Partners", "url": "/", "order": 3},
    {"id": 23, "section_id": 7, "label": "My Profile", "url": "/users/profile/", "order": 0},
    {"id": 24, "section_id": 7, "label": "My Orders", "url": "/", "order": 1},
    {"id": 25, "section_id": 7, "label": "Wishlist", "url": "/", "order": 2},
    {"id": 26, "section_id": 7, "label": "Settings", "url": "/", "order": 3},
]

FOOTER_SOCIAL_MEDIA_DATA = [
    {
        "id": 1,
        "footer_id": 1,
        "platform": "facebook",
        "label": "Facebook",
        "url": "https://facebook.com",
        "is_active": True,
        "order": 0,
    },
    {
        "id": 2,
        "footer_id": 1,
        "platform": "youtube",
        "label": "YouTube",
        "url": "https://youtube.com",
        "is_active": True,
        "order": 1,
    },
    {
        "id": 3,
        "footer_id": 1,
        "platform": "instagram",
        "label": "Instagram",
        "url": "https://instagram.com",
        "is_active": True,
        "order": 2,
    },
    {
        "id": 4,
        "footer_id": 1,
        "platform": "twitter",
        "label": "Twitter",
        "url": "https://twitter.com",
        "is_active": True,
        "order": 3,
    },
    {
        "id": 5,
        "footer_id": 1,
        "platform": "tiktok",
        "label": "TikTok",
        "url": "https://tiktok.com",
        "is_active": True,
        "order": 4,
    },
]

BOTTOMBAR_DATA = [{"id": 1, "singleton_key": 1, "is_active": True}]

BOTTOMBAR_LINKS_DATA = [
    {"id": 1, "bottom_bar_id": 1, "label": "Legal Notice", "url": "/legal/", "order": 0},
    {"id": 2, "bottom_bar_id": 1, "label": "Privacy Policy", "url": "/terms/", "order": 1},
    {"id": 3, "bottom_bar_id": 1, "label": "Terms of Use", "url": "/terms/", "order": 2},
    {"id": 4, "bottom_bar_id": 1, "label": "Cookie Settings", "url": "#", "order": 3},
    {"id": 5, "bottom_bar_id": 1, "label": "Accessibility", "url": "#", "order": 4},
]

CATEGORIES_DATA = [
    {
        "id": 47,
        "name": "Car Accessories",
        "slug": "car-accessories",
        "parent_id": None,
        "image": "",
        "icon": "truck",
        "sort_order": 1,
    },
    {
        "id": 49,
        "name": "Lighting",
        "slug": "lighting",
        "parent_id": None,
        "image": "",
        "icon": "light-bulb",
        "sort_order": 2,
    },
    {
        "id": 43,
        "name": "Wet Wipes",
        "slug": "wet-wipes",
        "parent_id": None,
        "image": "",
        "icon": "sparkles",
        "sort_order": 3,
    },
    {
        "id": 40,
        "name": "Batteries",
        "slug": "batteries",
        "parent_id": None,
        "image": "",
        "icon": "bolt",
        "sort_order": 4,
    },
    {
        "id": 61,
        "name": "Beauty & Health",
        "slug": "beauty-health",
        "parent_id": None,
        "image": "",
        "icon": "heart",
        "sort_order": 5,
    },
    {
        "id": 62,
        "name": "Household",
        "slug": "household",
        "parent_id": None,
        "image": "",
        "icon": "home",
        "sort_order": 6,
    },
    {
        "id": 63,
        "name": "Electronics",
        "slug": "electronics",
        "parent_id": None,
        "image": "",
        "icon": "device-mobile",
        "sort_order": 0,
    },
    {
        "id": 64,
        "name": "Pet Supplies",
        "slug": "pet-supplies",
        "parent_id": None,
        "image": "",
        "icon": "tag",
        "sort_order": 8,
    },
    {
        "id": 65,
        "name": "Office",
        "slug": "office",
        "parent_id": None,
        "image": "",
        "icon": "briefcase",
        "sort_order": 9,
    },
    # More root categories for testing scroll
    {
        "id": 66,
        "name": "Toys & Games",
        "slug": "toys-games",
        "parent_id": None,
        "image": "",
        "icon": "puzzle-piece",
        "sort_order": 10,
    },
    {
        "id": 67,
        "name": "Sports & Outdoors",
        "slug": "sports-outdoors",
        "parent_id": None,
        "image": "",
        "icon": "fire",
        "sort_order": 11,
    },
    {
        "id": 68,
        "name": "Garden & Patio",
        "slug": "garden-patio",
        "parent_id": None,
        "image": "",
        "icon": "leaf",
        "sort_order": 12,
    },
    {
        "id": 69,
        "name": "Tools & Hardware",
        "slug": "tools-hardware",
        "parent_id": None,
        "image": "",
        "icon": "wrench",
        "sort_order": 13,
    },
    {
        "id": 70,
        "name": "Grocery & Gourmet",
        "slug": "grocery-gourmet",
        "parent_id": None,
        "image": "",
        "icon": "shopping-bag",
        "sort_order": 14,
    },
    {"id": 71, "name": "Baby", "slug": "baby", "parent_id": None, "image": "", "icon": "emoji-happy", "sort_order": 15},
    {
        "id": 72,
        "name": "Automotive",
        "slug": "automotive",
        "parent_id": None,
        "image": "",
        "icon": "truck",
        "sort_order": 16,
    },
    {
        "id": 73,
        "name": "Industrial",
        "slug": "industrial",
        "parent_id": None,
        "image": "",
        "icon": "briefcase",
        "sort_order": 17,
    },
    {
        "id": 74,
        "name": "Arts & Crafts",
        "slug": "arts-crafts",
        "parent_id": None,
        "image": "",
        "icon": "scissors",
        "sort_order": 18,
    },
    {"id": 75, "name": "Books", "slug": "books", "parent_id": None, "image": "", "icon": "book-open", "sort_order": 19},
    # Subcategories
    {
        "id": 42,
        "name": "Watch Batteries",
        "slug": "watch-batteries",
        "parent_id": 40,
        "image": "",
        "icon": "clock",
        "sort_order": 0,
    },
    {
        "id": 41,
        "name": "Alkaline Batteries",
        "slug": "alkaline-batteries",
        "parent_id": 40,
        "image": "",
        "icon": "bolt",
        "sort_order": 0,
    },
    {
        "id": 300,
        "name": "AA Batteries",
        "slug": "aa-batteries",
        "parent_id": 41,
        "image": "",
        "icon": "bolt",
        "sort_order": 1,
    },
    {
        "id": 301,
        "name": "Bulk Packs",
        "slug": "bulk-packs",
        "parent_id": 300,
        "image": "",
        "icon": "bolt",
        "sort_order": 1,
    },
    {
        "id": 310,
        "name": "12-Pack",
        "slug": "bulk-12-pack",
        "parent_id": 301,
        "image": "",
        "icon": "bolt",
        "sort_order": 1,
    },
    {
        "id": 311,
        "name": "24-Pack",
        "slug": "bulk-24-pack",
        "parent_id": 301,
        "image": "",
        "icon": "bolt",
        "sort_order": 2,
    },
    {
        "id": 312,
        "name": "48-Pack",
        "slug": "bulk-48-pack",
        "parent_id": 301,
        "image": "",
        "icon": "bolt",
        "sort_order": 3,
    },
    {
        "id": 302,
        "name": "Value Packs",
        "slug": "value-packs",
        "parent_id": 300,
        "image": "",
        "icon": "bolt",
        "sort_order": 2,
    },
    {
        "id": 303,
        "name": "Industrial Packs",
        "slug": "industrial-packs",
        "parent_id": 300,
        "image": "",
        "icon": "bolt",
        "sort_order": 3,
    },
    {
        "id": 304,
        "name": "High Capacity",
        "slug": "high-capacity",
        "parent_id": 300,
        "image": "",
        "icon": "bolt",
        "sort_order": 4,
    },
    {
        "id": 305,
        "name": "Professional Series",
        "slug": "professional-series",
        "parent_id": 300,
        "image": "",
        "icon": "bolt",
        "sort_order": 5,
    },
    {
        "id": 306,
        "name": "Consumer Series",
        "slug": "consumer-series",
        "parent_id": 300,
        "image": "",
        "icon": "bolt",
        "sort_order": 6,
    },
    {
        "id": 200,
        "name": "Rechargeable Batteries",
        "slug": "rechargeable-batteries",
        "parent_id": 40,
        "image": "",
        "icon": "bolt",
        "sort_order": 2,
    },
    {
        "id": 201,
        "name": "Lithium Batteries",
        "slug": "lithium-batteries",
        "parent_id": 40,
        "image": "",
        "icon": "bolt",
        "sort_order": 3,
    },
    {
        "id": 202,
        "name": "Button Cells",
        "slug": "button-cells",
        "parent_id": 40,
        "image": "",
        "icon": "clock",
        "sort_order": 4,
    },
    {
        "id": 203,
        "name": "Hearing Aid Batteries",
        "slug": "hearing-aid-batteries",
        "parent_id": 40,
        "image": "",
        "icon": "heart",
        "sort_order": 5,
    },
    {
        "id": 204,
        "name": "Camera Batteries",
        "slug": "camera-batteries",
        "parent_id": 40,
        "image": "",
        "icon": "camera",
        "sort_order": 6,
    },
    {
        "id": 205,
        "name": "Power Tool Batteries",
        "slug": "power-tool-batteries",
        "parent_id": 40,
        "image": "",
        "icon": "wrench",
        "sort_order": 7,
    },
    {
        "id": 206,
        "name": "Battery Chargers",
        "slug": "battery-chargers",
        "parent_id": 40,
        "image": "",
        "icon": "sparkles",
        "sort_order": 8,
    },
    {
        "id": 207,
        "name": "Battery Holders",
        "slug": "battery-holders",
        "parent_id": 40,
        "image": "",
        "icon": "chip",
        "sort_order": 9,
    },
    {
        "id": 45,
        "name": "Kids Wipes",
        "slug": "kids-wipes",
        "parent_id": 43,
        "image": "",
        "icon": "puzzle-piece",
        "sort_order": 0,
    },
    {
        "id": 44,
        "name": "Baby Wipes",
        "slug": "baby-wipes",
        "parent_id": 43,
        "image": "",
        "icon": "heart",
        "sort_order": 0,
    },
    {
        "id": 46,
        "name": "Intimate Care",
        "slug": "intimate-care",
        "parent_id": 43,
        "image": "",
        "icon": "sparkles",
        "sort_order": 0,
    },
    {
        "id": 234,
        "name": "Antibacterial Wipes",
        "slug": "antibacterial-wipes",
        "parent_id": 43,
        "image": "",
        "icon": "sparkles",
        "sort_order": 1,
    },
    {
        "id": 235,
        "name": "Makeup Remover Wipes",
        "slug": "makeup-remover-wipes",
        "parent_id": 43,
        "image": "",
        "icon": "sparkles",
        "sort_order": 2,
    },
    {
        "id": 236,
        "name": "Household Wipes",
        "slug": "household-wipes",
        "parent_id": 43,
        "image": "",
        "icon": "sparkles",
        "sort_order": 3,
    },
    {
        "id": 237,
        "name": "Travel Wipes",
        "slug": "travel-wipes",
        "parent_id": 43,
        "image": "",
        "icon": "briefcase",
        "sort_order": 4,
    },
    {
        "id": 48,
        "name": "Air Fresheners",
        "slug": "air-fresheners",
        "parent_id": 47,
        "image": "",
        "icon": "sparkles",
        "sort_order": 0,
    },
    {
        "id": 226,
        "name": "Phone Holders",
        "slug": "phone-holders",
        "parent_id": 47,
        "image": "",
        "icon": "device-mobile",
        "sort_order": 1,
    },
    {
        "id": 227,
        "name": "Car Chargers",
        "slug": "car-chargers",
        "parent_id": 47,
        "image": "",
        "icon": "bolt",
        "sort_order": 2,
    },
    {
        "id": 228,
        "name": "Seat Covers",
        "slug": "seat-covers",
        "parent_id": 47,
        "image": "",
        "icon": "sparkles",
        "sort_order": 3,
    },
    {
        "id": 229,
        "name": "Floor Mats",
        "slug": "floor-mats",
        "parent_id": 47,
        "image": "",
        "icon": "sparkles",
        "sort_order": 4,
    },
    {
        "id": 50,
        "name": "LED Bulbs",
        "slug": "led-bulbs",
        "parent_id": 49,
        "image": "",
        "icon": "light-bulb",
        "sort_order": 0,
    },
    {
        "id": 230,
        "name": "Smart Bulbs",
        "slug": "smart-bulbs",
        "parent_id": 49,
        "image": "",
        "icon": "light-bulb",
        "sort_order": 1,
    },
    {
        "id": 231,
        "name": "Light Fixtures",
        "slug": "light-fixtures",
        "parent_id": 49,
        "image": "",
        "icon": "light-bulb",
        "sort_order": 2,
    },
    {
        "id": 232,
        "name": "Outdoor Lighting",
        "slug": "outdoor-lighting",
        "parent_id": 49,
        "image": "",
        "icon": "light-bulb",
        "sort_order": 3,
    },
    {
        "id": 233,
        "name": "LED Strips",
        "slug": "led-strips",
        "parent_id": 49,
        "image": "",
        "icon": "light-bulb",
        "sort_order": 4,
    },
    {
        "id": 208,
        "name": "Skincare",
        "slug": "skincare",
        "parent_id": 61,
        "image": "",
        "icon": "sparkles",
        "sort_order": 0,
    },
    {
        "id": 209,
        "name": "Hair Care",
        "slug": "hair-care",
        "parent_id": 61,
        "image": "",
        "icon": "sparkles",
        "sort_order": 1,
    },
    {
        "id": 210,
        "name": "Oral Care",
        "slug": "oral-care",
        "parent_id": 61,
        "image": "",
        "icon": "sparkles",
        "sort_order": 2,
    },
    {
        "id": 211,
        "name": "Vitamins & Supplements",
        "slug": "vitamins-supplements",
        "parent_id": 61,
        "image": "",
        "icon": "heart",
        "sort_order": 3,
    },
    {
        "id": 212,
        "name": "Personal Care",
        "slug": "personal-care",
        "parent_id": 61,
        "image": "",
        "icon": "heart",
        "sort_order": 4,
    },
    {"id": 213, "name": "Makeup", "slug": "makeup", "parent_id": 61, "image": "", "icon": "sparkles", "sort_order": 5},
    {
        "id": 214,
        "name": "Cleaning Supplies",
        "slug": "cleaning-supplies",
        "parent_id": 62,
        "image": "",
        "icon": "sparkles",
        "sort_order": 0,
    },
    {
        "id": 215,
        "name": "Laundry",
        "slug": "laundry",
        "parent_id": 62,
        "image": "",
        "icon": "sparkles",
        "sort_order": 1,
    },
    {
        "id": 216,
        "name": "Kitchen Essentials",
        "slug": "kitchen-essentials",
        "parent_id": 62,
        "image": "",
        "icon": "shopping-bag",
        "sort_order": 2,
    },
    {"id": 217, "name": "Bathroom", "slug": "bathroom", "parent_id": 62, "image": "", "icon": "home", "sort_order": 3},
    {
        "id": 218,
        "name": "Storage & Organization",
        "slug": "storage-organization",
        "parent_id": 62,
        "image": "",
        "icon": "briefcase",
        "sort_order": 4,
    },
    {
        "id": 219,
        "name": "Paper Goods",
        "slug": "paper-goods",
        "parent_id": 62,
        "image": "",
        "icon": "book-open",
        "sort_order": 5,
    },
    {"id": 220, "name": "Dog Food", "slug": "dog-food", "parent_id": 64, "image": "", "icon": "tag", "sort_order": 0},
    {"id": 221, "name": "Cat Food", "slug": "cat-food", "parent_id": 64, "image": "", "icon": "tag", "sort_order": 1},
    {
        "id": 222,
        "name": "Litter & Accessories",
        "slug": "litter-accessories",
        "parent_id": 64,
        "image": "",
        "icon": "sparkles",
        "sort_order": 2,
    },
    {
        "id": 223,
        "name": "Pet Toys",
        "slug": "pet-toys",
        "parent_id": 64,
        "image": "",
        "icon": "puzzle-piece",
        "sort_order": 3,
    },
    {
        "id": 224,
        "name": "Grooming",
        "slug": "pet-grooming",
        "parent_id": 64,
        "image": "",
        "icon": "sparkles",
        "sort_order": 4,
    },
    {
        "id": 225,
        "name": "Health & Wellness",
        "slug": "pet-health-wellness",
        "parent_id": 64,
        "image": "",
        "icon": "heart",
        "sort_order": 5,
    },
    # New sub-categories for recursion test under "Intimate Care" (id 46)
    {
        "id": 51,
        "name": "Feminine Hygiene",
        "slug": "feminine-hygiene",
        "parent_id": 46,
        "image": "",
        "icon": "heart",
        "sort_order": 0,
    },
    {
        "id": 52,
        "name": "Daily Freshness",
        "slug": "daily-freshness",
        "parent_id": 46,
        "image": "",
        "icon": "sun",
        "sort_order": 0,
    },
    {
        "id": 53,
        "name": "Travel Packs",
        "slug": "travel-packs",
        "parent_id": 46,
        "image": "",
        "icon": "briefcase",
        "sort_order": 0,
    },
    {"id": 54, "name": "Eco Wipes", "slug": "eco-wipes", "parent_id": 46, "image": "", "icon": "leaf", "sort_order": 0},
    {
        "id": 55,
        "name": "Sensitive",
        "slug": "sensitive",
        "parent_id": 46,
        "image": "",
        "icon": "shield-check",
        "sort_order": 0,
    },
    {"id": 56, "name": "Sport", "slug": "sport-care", "parent_id": 46, "image": "", "icon": "fire", "sort_order": 0},
    {
        "id": 57,
        "name": "Fragrance Free",
        "slug": "fragrance-free",
        "parent_id": 46,
        "image": "",
        "icon": "x-circle",
        "sort_order": 0,
    },
    {
        "id": 58,
        "name": "Natural Cotton",
        "slug": "natural-cotton",
        "parent_id": 46,
        "image": "",
        "icon": "cloud",
        "sort_order": 0,
    },
    {
        "id": 59,
        "name": "Night Care",
        "slug": "night-care",
        "parent_id": 46,
        "image": "",
        "icon": "moon",
        "sort_order": 0,
    },
    # Level 4 Categories (Children of Sport)
    {
        "id": 160,
        "name": "Gym Wipes",
        "slug": "gym-wipes",
        "parent_id": 56,
        "image": "",
        "icon": "fire",
        "sort_order": 0,
    },
    {
        "id": 161,
        "name": "Cycling Wipes",
        "slug": "cycling-wipes",
        "parent_id": 56,
        "image": "",
        "icon": "fire",
        "sort_order": 0,
    },
    # Subcategories for Electronics (ID 63) to test "More..." link
    {
        "id": 80,
        "name": "Smartphones",
        "slug": "smartphones",
        "parent_id": 63,
        "image": "",
        "icon": "device-mobile",
        "sort_order": 0,
    },
    {
        "id": 81,
        "name": "Laptops",
        "slug": "laptops",
        "parent_id": 63,
        "image": "",
        "icon": "desktop-computer",
        "sort_order": 1,
    },
    {
        "id": 82,
        "name": "Tablets",
        "slug": "tablets",
        "parent_id": 63,
        "image": "",
        "icon": "device-tablet",
        "sort_order": 2,
    },
    {"id": 83, "name": "Cameras", "slug": "cameras", "parent_id": 63, "image": "", "icon": "camera", "sort_order": 3},
    {"id": 84, "name": "Audio", "slug": "audio", "parent_id": 63, "image": "", "icon": "music-note", "sort_order": 4},
    {
        "id": 85,
        "name": "Gaming",
        "slug": "gaming",
        "parent_id": 63,
        "image": "",
        "icon": "puzzle-piece",
        "sort_order": 5,
    },
    {
        "id": 86,
        "name": "Accessories",
        "slug": "accessories",
        "parent_id": 63,
        "image": "",
        "icon": "sparkles",
        "sort_order": 6,
    },
    {
        "id": 87,
        "name": "Components",
        "slug": "components",
        "parent_id": 63,
        "image": "",
        "icon": "chip",
        "sort_order": 7,
    },
    {
        "id": 88,
        "name": "Networking",
        "slug": "networking",
        "parent_id": 63,
        "image": "",
        "icon": "wifi",
        "sort_order": 8,
    },
    {
        "id": 89,
        "name": "Printers",
        "slug": "printers",
        "parent_id": 63,
        "image": "",
        "icon": "printer",
        "sort_order": 9,
    },
    {
        "id": 90,
        "name": "Monitors",
        "slug": "monitors",
        "parent_id": 63,
        "image": "",
        "icon": "desktop-computer",
        "sort_order": 10,
    },
    {
        "id": 91,
        "name": "Wearables",
        "slug": "wearables",
        "parent_id": 63,
        "image": "",
        "icon": "clock",
        "sort_order": 11,
    },
    {
        "id": 120,
        "name": "Home Cinema",
        "slug": "home-cinema",
        "parent_id": 63,
        "image": "",
        "icon": "video-camera",
        "sort_order": 12,
    },
    {
        "id": 121,
        "name": "Projectors",
        "slug": "projectors",
        "parent_id": 63,
        "image": "",
        "icon": "presentation-chart-bar",
        "sort_order": 13,
    },
    {
        "id": 122,
        "name": "Electric Scooters",
        "slug": "electric-scooters",
        "parent_id": 63,
        "image": "",
        "icon": "truck",
        "sort_order": 14,
    },
    {
        "id": 123,
        "name": "Drones",
        "slug": "drones",
        "parent_id": 63,
        "image": "",
        "icon": "paper-airplane",
        "sort_order": 15,
    },
    {
        "id": 124,
        "name": "Smart Home",
        "slug": "smart-home",
        "parent_id": 63,
        "image": "",
        "icon": "home",
        "sort_order": 16,
    },
    {
        "id": 125,
        "name": "Security Cameras",
        "slug": "security-cameras",
        "parent_id": 63,
        "image": "",
        "icon": "eye",
        "sort_order": 17,
    },
    {
        "id": 126,
        "name": "Car Electronics",
        "slug": "car-electronics",
        "parent_id": 63,
        "image": "",
        "icon": "device-tablet",
        "sort_order": 18,
    },
    {
        "id": 127,
        "name": "Media Players",
        "slug": "media-players",
        "parent_id": 63,
        "image": "",
        "icon": "play",
        "sort_order": 19,
    },
    {
        "id": 128,
        "name": "Portable Audio",
        "slug": "portable-audio",
        "parent_id": 63,
        "image": "",
        "icon": "music-note",
        "sort_order": 20,
    },
    {
        "id": 129,
        "name": "Microphones",
        "slug": "microphones",
        "parent_id": 63,
        "image": "",
        "icon": "microphone",
        "sort_order": 21,
    },
    {
        "id": 130,
        "name": "Keyboards",
        "slug": "keyboards",
        "parent_id": 63,
        "image": "",
        "icon": "calculator",
        "sort_order": 22,
    },
    {"id": 131, "name": "Mice", "slug": "mice", "parent_id": 63, "image": "", "icon": "cursor-click", "sort_order": 23},
    {"id": 132, "name": "Cables", "slug": "cables", "parent_id": 63, "image": "", "icon": "link", "sort_order": 24},
    {
        "id": 133,
        "name": "Storage",
        "slug": "storage",
        "parent_id": 63,
        "image": "",
        "icon": "database",
        "sort_order": 25,
    },
    {
        "id": 134,
        "name": "Power Banks",
        "slug": "power-banks",
        "parent_id": 63,
        "image": "",
        "icon": "lightning-bolt",
        "sort_order": 26,
    },
    {"id": 135, "name": "Cases", "slug": "cases", "parent_id": 63, "image": "", "icon": "briefcase", "sort_order": 27},
]

ATTRIBUTE_DEFINITIONS_DATA = [
    {"id": 44, "name": "Brand", "show_on_tile": True, "tile_display_order": 1},
    {"id": 45, "name": "Battery Type", "show_on_tile": True, "tile_display_order": 2},
    {"id": 46, "name": "Pack Size", "show_on_tile": True, "tile_display_order": 3},
    {"id": 47, "name": "Product Line", "show_on_tile": True, "tile_display_order": 4},
    {"id": 48, "name": "Voltage", "show_on_tile": True, "tile_display_order": 5},
    {"id": 49, "name": "Wipe Type", "show_on_tile": True, "tile_display_order": 6},
    {"id": 50, "name": "Scent", "show_on_tile": True, "tile_display_order": 7},
    {"id": 51, "name": "Weight", "show_on_tile": True, "tile_display_order": 8},
    {"id": 52, "name": "Product Type", "show_on_tile": True, "tile_display_order": 9},
    {"id": 53, "name": "Wattage", "show_on_tile": True, "tile_display_order": 10},
    {"id": 54, "name": "Lumens", "show_on_tile": True, "tile_display_order": 11},
    {"id": 55, "name": "Socket Type", "show_on_tile": True, "tile_display_order": 12},
    {"id": 56, "name": "Character", "show_on_tile": True, "tile_display_order": 13},
    {"id": 57, "name": "Age Range", "show_on_tile": True, "tile_display_order": 14},
    {"id": 58, "name": "Volume", "show_on_tile": True, "tile_display_order": 15},
]

ATTRIBUTE_OPTIONS_DATA = [
    {"id": 82, "attribute_id": 44, "value": "Energizer"},
    {"id": 83, "attribute_id": 45, "value": "AAA"},
    {"id": 84, "attribute_id": 46, "value": "4"},
    {"id": 85, "attribute_id": 47, "value": "MAX"},
    {"id": 86, "attribute_id": 45, "value": "Silver Oxide"},
    {"id": 87, "attribute_id": 48, "value": "1.55V"},
    {"id": 88, "attribute_id": 47, "value": "Silver"},
    {"id": 89, "attribute_id": 44, "value": "Novita"},
    {"id": 90, "attribute_id": 46, "value": "15"},
    {"id": 91, "attribute_id": 49, "value": "Intimate"},
    {"id": 92, "attribute_id": 47, "value": "Intimate"},
    {"id": 93, "attribute_id": 44, "value": "California Scents"},
    {"id": 94, "attribute_id": 50, "value": "Coronado Cherry"},
    {"id": 95, "attribute_id": 51, "value": "42g"},
    {"id": 96, "attribute_id": 52, "value": "Car Air Freshener"},
    {"id": 97, "attribute_id": 53, "value": "6.2W"},
    {"id": 98, "attribute_id": 54, "value": "450"},
    {"id": 99, "attribute_id": 55, "value": "E14"},
    {"id": 100, "attribute_id": 44, "value": "Smile"},
    {"id": 101, "attribute_id": 56, "value": "Cars - Jackson Storm"},
    {"id": 102, "attribute_id": 49, "value": "Kids"},
    {"id": 103, "attribute_id": 46, "value": "60"},
    {"id": 104, "attribute_id": 49, "value": "Baby"},
    {"id": 105, "attribute_id": 57, "value": "0+"},
    {"id": 106, "attribute_id": 44, "value": "Refresh Your Car"},
    {"id": 107, "attribute_id": 50, "value": "New Car + Cool Breeze"},
    {"id": 108, "attribute_id": 58, "value": "7ml"},
    {"id": 109, "attribute_id": 52, "value": "Car Diffuser"},
    # Additional brands for Alkaline Batteries
    {"id": 110, "attribute_id": 44, "value": "Duracell"},
    {"id": 111, "attribute_id": 44, "value": "Panasonic"},
    {"id": 112, "attribute_id": 44, "value": "Varta"},
    {"id": 113, "attribute_id": 44, "value": "GP"},
    # Additional battery types
    {"id": 114, "attribute_id": 45, "value": "AA"},
    # Additional pack sizes
    {"id": 115, "attribute_id": 46, "value": "8"},
    # Additional product lines
    {"id": 116, "attribute_id": 47, "value": "Plus"},
    {"id": 117, "attribute_id": 47, "value": "Ultra"},
    {"id": 118, "attribute_id": 47, "value": "Evolta"},
    {"id": 119, "attribute_id": 47, "value": "Longlife"},
    {"id": 120, "attribute_id": 47, "value": "High Energy"},
    {"id": 121, "attribute_id": 47, "value": "Ultra Plus"},
    # Additional voltages
    {"id": 122, "attribute_id": 48, "value": "1.5V"},
    # Additional brands for Alkaline Batteries
    {"id": 123, "attribute_id": 44, "value": "Amazon Basics"},
    {"id": 124, "attribute_id": 44, "value": "Ikea"},
    {"id": 125, "attribute_id": 44, "value": "Toshiba"},
    {"id": 126, "attribute_id": 44, "value": "Sanyo"},
    {"id": 127, "attribute_id": 44, "value": "Eveready"},
    {"id": 128, "attribute_id": 44, "value": "Philips"},
    {"id": 129, "attribute_id": 44, "value": "Rayovac"},
    {"id": 130, "attribute_id": 44, "value": "Maxell"},
    {"id": 131, "attribute_id": 44, "value": "Kodak"},
    {"id": 132, "attribute_id": 44, "value": "Camelion"},
    {"id": 133, "attribute_id": 44, "value": "Fujitsu"},
    {"id": 134, "attribute_id": 44, "value": "Ansmann"},
    {"id": 135, "attribute_id": 44, "value": "Procell"},
    {"id": 136, "attribute_id": 44, "value": "Sony"},
    # Additional battery types
    {"id": 137, "attribute_id": 45, "value": "C"},
    {"id": 138, "attribute_id": 45, "value": "D"},
    {"id": 139, "attribute_id": 45, "value": "9V"},
    {"id": 140, "attribute_id": 45, "value": "AA/AAA"},
    # Additional pack sizes
    {"id": 141, "attribute_id": 46, "value": "2"},
    {"id": 142, "attribute_id": 46, "value": "6"},
    {"id": 143, "attribute_id": 46, "value": "10"},
    {"id": 144, "attribute_id": 46, "value": "12"},
    {"id": 145, "attribute_id": 46, "value": "16"},
    {"id": 146, "attribute_id": 46, "value": "20"},
    {"id": 147, "attribute_id": 46, "value": "24"},
    {"id": 148, "attribute_id": 46, "value": "36"},
    {"id": 149, "attribute_id": 46, "value": "40"},
    {"id": 150, "attribute_id": 46, "value": "48"},
    {"id": 151, "attribute_id": 46, "value": "1"},
    # Additional product lines
    {"id": 152, "attribute_id": 47, "value": "Coppertop"},
    {"id": 153, "attribute_id": 47, "value": "Optimum"},
    {"id": 154, "attribute_id": 47, "value": "Power Seal"},
    {"id": 155, "attribute_id": 47, "value": "Industrial"},
    {"id": 156, "attribute_id": 47, "value": "Eco Advanced"},
    {"id": 157, "attribute_id": 47, "value": "Pro Power"},
    {"id": 158, "attribute_id": 47, "value": "Gold"},
    {"id": 159, "attribute_id": 47, "value": "Xtralife"},
    {"id": 160, "attribute_id": 47, "value": "Stamina Plus"},
    {"id": 161, "attribute_id": 47, "value": "Fusion"},
    {"id": 162, "attribute_id": 47, "value": "Premium"},
    {"id": 163, "attribute_id": 47, "value": "Ultra Alkaline"},
    {"id": 164, "attribute_id": 47, "value": "Power Life"},
]

PRODUCTS_DATA = [
    {
        "id": 50,
        "name": "Energizer MAX AAA 4-Pack",
        "slug": "energizer-max-aaa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "12.99",
        "stock": 150,
        "sales_total": "0",
        "revenue_total": "0",
        "sales_per_day": "0",
        "sales_per_month": "0",
        "description": "<h2><strong>Energizer MAX AAA Alkaline Batteries</strong></h2>\n<p>Power your everyday devices with <strong>Energizer MAX</strong> - trusted worldwide for reliable performance.</p>\n<h3>Key Features</h3>\n<ul>\n<li><strong>Long-lasting power</strong> for your everyday devices</li>\n<li>Up to <strong>10 years</strong> shelf life</li>\n<li><strong>Leak-proof construction</strong> protects your devices for up to 2 years</li>\n</ul>\n<p>Energizer MAX batteries deliver dependable power to the devices you use every day. <em>From flashlights to toys</em>, these batteries keep your world running.</p>\n<blockquote><p>PROTECTS YOUR DEVICES from leakage of fully used batteries up to 2 years.</p></blockquote>",
    },
    {
        "id": 51,
        "name": "Energizer Silver Watch Battery 1.55V",
        "slug": "energizer-silver-watch-battery-155v",
        "category_id": 42,
        "status": "active",
        "price": "6.99",
        "stock": 500,
        "sales_total": "0",
        "revenue_total": "0",
        "sales_per_day": "0",
        "sales_per_month": "0",
        "description": "<h2><strong>Energizer Silver Oxide Watch Battery</strong></h2>\n<p>Precision power for your <strong>watches and small electronics</strong>.</p>\n<h3>Specifications</h3>\n<ul>\n<li>Voltage: <strong>1.55V</strong></li>\n<li>Type: <strong>Silver Oxide</strong></li>\n<li><strong>0% Mercury</strong> - eco-friendly</li>\n<li>Perfect for <strong>watches, calculators, toys</strong></li>\n</ul>\n<p>Energizer Silver batteries provide <em>consistent power output</em> throughout their life. Multilingual packaging: DE/FR/NL/DA.</p>\n<blockquote><p>Reliable power for precision timepieces.</p></blockquote>",
    },
    {
        "id": 52,
        "name": "Novita Intimate Wet Wipes 15pcs",
        "slug": "novita-intimate-wet-wipes-15pcs",
        "category_id": 46,
        "status": "active",
        "price": "5.49",
        "stock": 220,
        "sales_total": "0",
        "revenue_total": "0",
        "sales_per_day": "0",
        "sales_per_month": "0",
        "description": "<h2><strong>Novita Intimate Wet Wipes</strong></h2>\n<p>Gentle care with <strong>Vegetal Amiderm Complex</strong> for daily freshness.</p>\n<h3>Benefits</h3>\n<ul>\n<li><strong>Bioflushable</strong> cloth - eco-friendly</li>\n<li><strong>Neutralizes odor</strong> naturally</li>\n<li><strong>Long-lasting freshness</strong></li>\n<li>Contains <strong>Vegetal Amiderm Complex</strong></li>\n</ul>\n<p>Novita Intimate wipes are specially formulated for <em>gentle daily hygiene</em>. Compact pack perfect for travel.</p>\n<blockquote><p>Bioflushable cloth for eco-conscious care.</p></blockquote>",
    },
    {
        "id": 53,
        "name": "California Scents Car Freshener Coronado Cherry 42g",
        "slug": "california-scents-car-freshener-coronado-cherry-42",
        "category_id": 48,
        "status": "active",
        "price": "14.99",
        "stock": 95,
        "sales_total": "0",
        "revenue_total": "0",
        "sales_per_day": "0",
        "sales_per_month": "0",
        "description": "<h2><strong>California Scents Car Air Freshener</strong></h2>\n<p>Experience the iconic <strong>Coronado Cherry</strong> scent - Made in USA!</p>\n<h3>Fragrance Details</h3>\n<ul>\n<li><strong>Long-lasting</strong> cherry scent</li>\n<li>Lasts up to <strong>60 days</strong></li>\n<li><strong>Made in USA</strong></li>\n<li>Available in can and vent clip formats</li>\n</ul>\n<p>The original California Scents air freshener in the classic can design. <em>Désodorisant / Lufterfrischer</em> - loved worldwide!</p>\n<blockquote><p>Transform your car with the iconic California Scents experience!</p></blockquote>",
    },
    {
        "id": 54,
        "name": "Energizer LED R50 E14 6.2W 450 Lumens",
        "slug": "energizer-led-r50-e14-62w-450-lumens",
        "category_id": 50,
        "status": "active",
        "price": "11.99",
        "stock": 180,
        "sales_total": "0",
        "revenue_total": "0",
        "sales_per_day": "0",
        "sales_per_month": "0",
        "description": "<h2><strong>Energizer LED R50 Light Bulb</strong></h2>\n<p>Save energy with <strong>84% less energy</strong> than traditional bulbs!</p>\n<h3>Specifications</h3>\n<ul>\n<li><strong>6.2W</strong> replaces <strong>40W</strong> traditional bulb</li>\n<li><strong>450 Lumens</strong> brightness</li>\n<li><strong>3000K Warm White</strong> color temperature</li>\n<li><strong>10,000 hours</strong> lifetime / 10 year lifespan</li>\n</ul>\n<p>Energizer LED bulbs combine <em>energy efficiency</em> with long-lasting performance. SES/E14 socket compatible.</p>\n<blockquote><p>10 YEAR LIFESPAN - Up to 84% energy savings!</p></blockquote>",
    },
    {
        "id": 55,
        "name": "Smile Wet Wipes Cars Jackson Storm 15pcs",
        "slug": "smile-wet-wipes-cars-jackson-storm-15pcs",
        "category_id": 45,
        "status": "active",
        "price": "4.99",
        "stock": 300,
        "sales_total": "0",
        "revenue_total": "0",
        "sales_per_day": "0",
        "sales_per_month": "0",
        "description": "<h2><strong>Smile Wet Wipes - Disney Pixar Cars Edition</strong></h2>\n<p>Make cleaning fun with <strong>Jackson Storm</strong> from Disney Pixar's Cars 3!</p>\n<h3>Features</h3>\n<ul>\n<li><strong>Gentle formula</strong> safe for children</li>\n<li>Fun <strong>Cars character design</strong></li>\n<li>Removes <strong>ink from hands</strong> easily</li>\n<li>Compact <strong>15 piece pack</strong> - perfect for on-the-go</li>\n</ul>\n<p>These wipes feature the sleek <em>Jackson Storm 2.0</em> design that kids love. Perfect for school, travel, and everyday messes!</p>",
    },
    {
        "id": 56,
        "name": "Smile Baby Wet Wipes with Chamomile 60pcs",
        "slug": "smile-baby-wet-wipes-with-chamomile-60pcs",
        "category_id": 44,
        "status": "active",
        "price": "7.49",
        "stock": 250,
        "sales_total": "0",
        "revenue_total": "0",
        "sales_per_day": "0",
        "sales_per_month": "0",
        "description": "<h2><strong>Smile Baby Wet Wipes - Gentle Care</strong></h2>\n<p>The <strong>gentle choice</strong> for your baby's delicate skin.</p>\n<h3>Why Choose These Wipes?</h3>\n<ul>\n<li><strong>Hypoallergenic</strong> and dermatologically tested</li>\n<li>Contains <strong>chamomile and aloe</strong> extracts</li>\n<li><strong>Alcohol-free</strong> formula</li>\n<li>Safe from <strong>0+ months</strong></li>\n</ul>\n<p>Smile Baby wipes are specially formulated with natural ingredients. <em>Dermatologically tested</em> for peace of mind.</p>\n<blockquote><p>With chamomile and aloe extracts - gentle care your baby deserves.</p></blockquote>",
    },
    {
        "id": 57,
        "name": "Refresh Your Car Diffuser New Car/Cool Breeze 7ml",
        "slug": "refresh-your-car-diffuser-new-carcool-breeze-7ml",
        "category_id": 48,
        "status": "active",
        "price": "9.99",
        "stock": 140,
        "sales_total": "0",
        "revenue_total": "0",
        "sales_per_day": "0",
        "sales_per_month": "0",
        "description": '<h2><strong>Refresh Your Car Diffuser</strong></h2><p>Dual fragrance system: <strong>New Car</strong> and <strong>Cool Breeze</strong> scents in one!</p><h3>Features</h3><ul><li data-list-item-id="ef798f52db0e47085e20d2fbc48623d62"><strong>Scent Control</strong> - adjustable intensity</li><li data-list-item-id="e84c3726bdc76ead7ece12051832d5f8b"><strong>Eliminates odors</strong> effectively</li><li data-list-item-id="ee74e2a94ad35196013090f68bc70941f"><strong>Dual fragrance</strong> design</li><li data-list-item-id="ed94399150f6b60ad41d1b718911c6386"><strong>7ml</strong> long-lasting formula</li></ul><p>The innovative diffuser design allows you to <i>control scent intensity</i>. Available in multiple scent combinations.</p><blockquote><p>Scent Control / Réglage de l\'intensité - Your car, your way!</p></blockquote>',
    },
    {
        "id": 58,
        "name": "Energizer Alkaline Power 9V 1-Pack",
        "slug": "energizer-alkaline-power-9v-1-pack",
        "category_id": 40,
        "status": "active",
        "price": "14.49",
        "stock": 60,
        "sales_total": "0",
        "revenue_total": "0",
        "sales_per_day": "0",
        "sales_per_month": "0",
        "description": "<p>Reliable 9V battery for smoke detectors and high-drain devices.</p>",
    },
    {
        "id": 59,
        "name": "Novita Wet Wipes Anti-bacterial 15pcs",
        "slug": "novita-wet-wipes-anti-bacterial-15pcs",
        "category_id": 43,
        "status": "active",
        "price": "4.99",
        "stock": 200,
        "sales_total": "0",
        "revenue_total": "0",
        "sales_per_day": "0",
        "sales_per_month": "0",
        "description": "<p>Anti-bacterial wet wipes for hands and surfaces.</p>",
    },
    {
        "id": 150,
        "name": "Energizer Industrial AA 10-Pack",
        "slug": "energizer-industrial-aa-10-pack",
        "category_id": 305,
        "status": "active",
        "price": "24.99",
        "stock": 50,
        "sales_total": "0",
        "revenue_total": "0",
        "sales_per_day": "0",
        "sales_per_month": "0",
        "description": "<p>Professional grade AA batteries in bulk.</p>",
    },
    {
        "id": 151,
        "name": "Energizer Everyday AA 4-Pack",
        "slug": "energizer-everyday-aa-4-pack",
        "category_id": 306,
        "status": "active",
        "price": "14.99",
        "stock": 100,
        "sales_total": "0",
        "revenue_total": "0",
        "sales_per_day": "0",
        "sales_per_month": "0",
        "description": "<p>Standard AA batteries for daily use.</p>",
    },
    # Products for parent categories without subcategories to populate navigation
    {
        "id": 160,
        "name": "Samsung Galaxy Buds Pro",
        "slug": "samsung-galaxy-buds-pro",
        "category_id": 63,  # Electronics (parent)
        "status": "active",
        "price": "199.99",
        "stock": 45,
        "sales_total": "0",
        "revenue_total": "0",
        "sales_per_day": "0",
        "sales_per_month": "0",
        "description": "<p>Premium wireless earbuds with active noise cancellation.</p>",
    },
    {
        "id": 161,
        "name": "Vitamin C Serum 30ml",
        "slug": "vitamin-c-serum-30ml",
        "category_id": 61,  # Beauty & Health (parent)
        "status": "active",
        "price": "29.99",
        "stock": 120,
        "sales_total": "0",
        "revenue_total": "0",
        "sales_per_day": "0",
        "sales_per_month": "0",
        "description": "<p>Brightening vitamin C facial serum for radiant skin.</p>",
    },
    {
        "id": 162,
        "name": "Multi-Purpose Cleaner 750ml",
        "slug": "multi-purpose-cleaner-750ml",
        "category_id": 62,  # Household (parent)
        "status": "active",
        "price": "8.99",
        "stock": 200,
        "sales_total": "0",
        "revenue_total": "0",
        "sales_per_day": "0",
        "sales_per_month": "0",
        "description": "<p>All-surface cleaning solution for kitchen and bathroom.</p>",
    },
    {
        "id": 163,
        "name": "Premium Dog Food 2kg",
        "slug": "premium-dog-food-2kg",
        "category_id": 64,  # Pet Supplies (parent)
        "status": "active",
        "price": "24.99",
        "stock": 80,
        "sales_total": "0",
        "revenue_total": "0",
        "sales_per_day": "0",
        "sales_per_month": "0",
        "description": "<p>High-protein dog food for adult dogs of all breeds.</p>",
    },
    {
        "id": 164,
        "name": "A4 Copy Paper 500 Sheets",
        "slug": "a4-copy-paper-500-sheets",
        "category_id": 65,  # Office (parent)
        "status": "active",
        "price": "12.99",
        "stock": 300,
        "sales_total": "0",
        "revenue_total": "0",
        "sales_per_day": "0",
        "sales_per_month": "0",
        "description": "<p>Premium quality A4 paper for printing and copying.</p>",
    },
    {
        "id": 165,
        "name": "LEGO City Police Station",
        "slug": "lego-city-police-station",
        "category_id": 66,  # Toys & Games (parent)
        "status": "active",
        "price": "89.99",
        "stock": 25,
        "sales_total": "0",
        "revenue_total": "0",
        "sales_per_day": "0",
        "sales_per_month": "0",
        "description": "<p>Build your own police station with this 743-piece LEGO set.</p>",
    },
    {
        "id": 166,
        "name": "Yoga Mat Premium 6mm",
        "slug": "yoga-mat-premium-6mm",
        "category_id": 67,  # Sports & Outdoors (parent)
        "status": "active",
        "price": "34.99",
        "stock": 75,
        "sales_total": "0",
        "revenue_total": "0",
        "sales_per_day": "0",
        "sales_per_month": "0",
        "description": "<p>Non-slip yoga mat with excellent cushioning for all exercises.</p>",
    },
    {
        "id": 167,
        "name": "Garden Hose 15m",
        "slug": "garden-hose-15m",
        "category_id": 68,  # Garden & Patio (parent)
        "status": "active",
        "price": "29.99",
        "stock": 50,
        "sales_total": "0",
        "revenue_total": "0",
        "sales_per_day": "0",
        "sales_per_month": "0",
        "description": "<p>Flexible garden hose with spray nozzle included.</p>",
    },
    {
        "id": 168,
        "name": "Cordless Drill 18V",
        "slug": "cordless-drill-18v",
        "category_id": 69,  # Tools & Hardware (parent)
        "status": "active",
        "price": "79.99",
        "stock": 40,
        "sales_total": "0",
        "revenue_total": "0",
        "sales_per_day": "0",
        "sales_per_month": "0",
        "description": "<p>Professional cordless drill with two batteries included.</p>",
    },
    {
        "id": 169,
        "name": "Organic Extra Virgin Olive Oil 500ml",
        "slug": "organic-olive-oil-500ml",
        "category_id": 70,  # Grocery & Gourmet (parent)
        "status": "active",
        "price": "15.99",
        "stock": 150,
        "sales_total": "0",
        "revenue_total": "0",
        "sales_per_day": "0",
        "sales_per_month": "0",
        "description": "<p>Cold-pressed extra virgin olive oil from organic olives.</p>",
    },
    {
        "id": 170,
        "name": "Baby Bottle Set 3-Pack",
        "slug": "baby-bottle-set-3-pack",
        "category_id": 71,  # Baby (parent)
        "status": "active",
        "price": "18.99",
        "stock": 90,
        "sales_total": "0",
        "revenue_total": "0",
        "sales_per_day": "0",
        "sales_per_month": "0",
        "description": "<p>Anti-colic baby bottles with slow flow nipples.</p>",
    },
    {
        "id": 171,
        "name": "Car Wax Premium 500ml",
        "slug": "car-wax-premium-500ml",
        "category_id": 72,  # Automotive (parent)
        "status": "active",
        "price": "22.99",
        "stock": 60,
        "sales_total": "0",
        "revenue_total": "0",
        "sales_per_day": "0",
        "sales_per_month": "0",
        "description": "<p>Long-lasting car wax for ultimate shine and protection.</p>",
    },
    {
        "id": 172,
        "name": "Safety Gloves Industrial Pack",
        "slug": "safety-gloves-industrial",
        "category_id": 73,  # Industrial (parent)
        "status": "active",
        "price": "19.99",
        "stock": 200,
        "sales_total": "0",
        "revenue_total": "0",
        "sales_per_day": "0",
        "sales_per_month": "0",
        "description": "<p>Heavy-duty work gloves for industrial applications.</p>",
    },
    {
        "id": 173,
        "name": "Acrylic Paint Set 24 Colors",
        "slug": "acrylic-paint-set-24-colors",
        "category_id": 74,  # Arts & Crafts (parent)
        "status": "active",
        "price": "24.99",
        "stock": 85,
        "sales_total": "0",
        "revenue_total": "0",
        "sales_per_day": "0",
        "sales_per_month": "0",
        "description": "<p>Vibrant acrylic paint set perfect for beginners and professionals.</p>",
    },
    {
        "id": 174,
        "name": "The Art of Programming",
        "slug": "the-art-of-programming-book",
        "category_id": 75,  # Books (parent)
        "status": "active",
        "price": "49.99",
        "stock": 55,
        "sales_total": "0",
        "revenue_total": "0",
        "sales_per_day": "0",
        "sales_per_month": "0",
        "description": "<p>Classic computer science book covering algorithms and data structures.</p>",
    },
    # === Alkaline Batteries Category (41) - Products for pagination testing ===
    # Adding 144 products to test 4 pages of 36 products each
    {
        "id": 200,
        "name": "Energizer MAX AA 4-Pack",
        "slug": "energizer-max-aa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "14.99",
        "stock": 200,
        "sales_total": "150",
        "revenue_total": "2248.50",
        "sales_per_day": "5",
        "sales_per_month": "150",
        "description": "<p>Long-lasting AA alkaline batteries.</p>",
    },
    {
        "id": 201,
        "name": "Energizer MAX AA 8-Pack",
        "slug": "energizer-max-aa-8-pack",
        "category_id": 41,
        "status": "active",
        "price": "24.99",
        "stock": 180,
        "sales_total": "120",
        "revenue_total": "2998.80",
        "sales_per_day": "4",
        "sales_per_month": "120",
        "description": "<p>Value pack of 8 AA batteries.</p>",
    },
    {
        "id": 202,
        "name": "Energizer MAX AAA 8-Pack",
        "slug": "energizer-max-aaa-8-pack",
        "category_id": 41,
        "status": "active",
        "price": "22.99",
        "stock": 175,
        "sales_total": "110",
        "revenue_total": "2528.90",
        "sales_per_day": "4",
        "sales_per_month": "110",
        "description": "<p>Value pack of 8 AAA batteries.</p>",
    },
    {
        "id": 203,
        "name": "Duracell Plus AA 4-Pack",
        "slug": "duracell-plus-aa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "15.49",
        "stock": 220,
        "sales_total": "180",
        "revenue_total": "2788.20",
        "sales_per_day": "6",
        "sales_per_month": "180",
        "description": "<p>Duracell Plus Power AA batteries.</p>",
    },
    {
        "id": 204,
        "name": "Duracell Plus AA 8-Pack",
        "slug": "duracell-plus-aa-8-pack",
        "category_id": 41,
        "status": "active",
        "price": "25.99",
        "stock": 160,
        "sales_total": "95",
        "revenue_total": "2469.05",
        "sales_per_day": "3",
        "sales_per_month": "95",
        "description": "<p>Duracell Plus Power AA batteries, 8 pack.</p>",
    },
    {
        "id": 205,
        "name": "Duracell Plus AAA 4-Pack",
        "slug": "duracell-plus-aaa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "14.49",
        "stock": 210,
        "sales_total": "160",
        "revenue_total": "2318.40",
        "sales_per_day": "5",
        "sales_per_month": "160",
        "description": "<p>Duracell Plus Power AAA batteries.</p>",
    },
    {
        "id": 206,
        "name": "Duracell Plus AAA 8-Pack",
        "slug": "duracell-plus-aaa-8-pack",
        "category_id": 41,
        "status": "active",
        "price": "23.99",
        "stock": 155,
        "sales_total": "85",
        "revenue_total": "2039.15",
        "sales_per_day": "3",
        "sales_per_month": "85",
        "description": "<p>Duracell Plus Power AAA batteries, 8 pack.</p>",
    },
    {
        "id": 207,
        "name": "Duracell Ultra AA 4-Pack",
        "slug": "duracell-ultra-aa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "17.99",
        "stock": 140,
        "sales_total": "70",
        "revenue_total": "1259.30",
        "sales_per_day": "2",
        "sales_per_month": "70",
        "description": "<p>Duracell Ultra Power AA batteries with extended life.</p>",
    },
    {
        "id": 208,
        "name": "Duracell Ultra AAA 4-Pack",
        "slug": "duracell-ultra-aaa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "16.99",
        "stock": 145,
        "sales_total": "65",
        "revenue_total": "1104.35",
        "sales_per_day": "2",
        "sales_per_month": "65",
        "description": "<p>Duracell Ultra Power AAA batteries with extended life.</p>",
    },
    {
        "id": 209,
        "name": "Panasonic Evolta AA 4-Pack",
        "slug": "panasonic-evolta-aa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "13.99",
        "stock": 190,
        "sales_total": "140",
        "revenue_total": "1958.60",
        "sales_per_day": "5",
        "sales_per_month": "140",
        "description": "<p>Panasonic Evolta premium AA batteries.</p>",
    },
    {
        "id": 210,
        "name": "Panasonic Evolta AA 8-Pack",
        "slug": "panasonic-evolta-aa-8-pack",
        "category_id": 41,
        "status": "active",
        "price": "23.49",
        "stock": 130,
        "sales_total": "75",
        "revenue_total": "1761.75",
        "sales_per_day": "3",
        "sales_per_month": "75",
        "description": "<p>Panasonic Evolta premium AA batteries, 8 pack.</p>",
    },
    {
        "id": 211,
        "name": "Panasonic Evolta AAA 4-Pack",
        "slug": "panasonic-evolta-aaa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "12.99",
        "stock": 185,
        "sales_total": "130",
        "revenue_total": "1688.70",
        "sales_per_day": "4",
        "sales_per_month": "130",
        "description": "<p>Panasonic Evolta premium AAA batteries.</p>",
    },
    {
        "id": 212,
        "name": "Panasonic Evolta AAA 8-Pack",
        "slug": "panasonic-evolta-aaa-8-pack",
        "category_id": 41,
        "status": "active",
        "price": "21.99",
        "stock": 125,
        "sales_total": "60",
        "revenue_total": "1319.40",
        "sales_per_day": "2",
        "sales_per_month": "60",
        "description": "<p>Panasonic Evolta premium AAA batteries, 8 pack.</p>",
    },
    {
        "id": 213,
        "name": "Varta Longlife AA 4-Pack",
        "slug": "varta-longlife-aa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "11.99",
        "stock": 250,
        "sales_total": "200",
        "revenue_total": "2398.00",
        "sales_per_day": "7",
        "sales_per_month": "200",
        "description": "<p>Varta Longlife AA alkaline batteries.</p>",
    },
    {
        "id": 214,
        "name": "Varta Longlife AA 8-Pack",
        "slug": "varta-longlife-aa-8-pack",
        "category_id": 41,
        "status": "active",
        "price": "19.99",
        "stock": 180,
        "sales_total": "120",
        "revenue_total": "2398.80",
        "sales_per_day": "4",
        "sales_per_month": "120",
        "description": "<p>Varta Longlife AA batteries, value 8 pack.</p>",
    },
    {
        "id": 215,
        "name": "Varta Longlife AAA 4-Pack",
        "slug": "varta-longlife-aaa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "10.99",
        "stock": 240,
        "sales_total": "190",
        "revenue_total": "2088.10",
        "sales_per_day": "6",
        "sales_per_month": "190",
        "description": "<p>Varta Longlife AAA alkaline batteries.</p>",
    },
    {
        "id": 216,
        "name": "Varta Longlife AAA 8-Pack",
        "slug": "varta-longlife-aaa-8-pack",
        "category_id": 41,
        "status": "active",
        "price": "18.49",
        "stock": 170,
        "sales_total": "100",
        "revenue_total": "1849.00",
        "sales_per_day": "3",
        "sales_per_month": "100",
        "description": "<p>Varta Longlife AAA batteries, value 8 pack.</p>",
    },
    {
        "id": 217,
        "name": "Varta High Energy AA 4-Pack",
        "slug": "varta-high-energy-aa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "14.49",
        "stock": 165,
        "sales_total": "90",
        "revenue_total": "1304.10",
        "sales_per_day": "3",
        "sales_per_month": "90",
        "description": "<p>Varta High Energy AA batteries for high-drain devices.</p>",
    },
    {
        "id": 218,
        "name": "Varta High Energy AAA 4-Pack",
        "slug": "varta-high-energy-aaa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "13.49",
        "stock": 160,
        "sales_total": "85",
        "revenue_total": "1146.65",
        "sales_per_day": "3",
        "sales_per_month": "85",
        "description": "<p>Varta High Energy AAA batteries for high-drain devices.</p>",
    },
    {
        "id": 219,
        "name": "GP Ultra Plus AA 4-Pack",
        "slug": "gp-ultra-plus-aa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "9.99",
        "stock": 300,
        "sales_total": "250",
        "revenue_total": "2497.50",
        "sales_per_day": "8",
        "sales_per_month": "250",
        "description": "<p>GP Ultra Plus alkaline AA batteries.</p>",
    },
    {
        "id": 220,
        "name": "GP Ultra Plus AA 8-Pack",
        "slug": "gp-ultra-plus-aa-8-pack",
        "category_id": 41,
        "status": "active",
        "price": "16.99",
        "stock": 220,
        "sales_total": "150",
        "revenue_total": "2548.50",
        "sales_per_day": "5",
        "sales_per_month": "150",
        "description": "<p>GP Ultra Plus alkaline AA batteries, 8 pack.</p>",
    },
    {
        "id": 221,
        "name": "GP Ultra Plus AAA 4-Pack",
        "slug": "gp-ultra-plus-aaa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "8.99",
        "stock": 290,
        "sales_total": "240",
        "revenue_total": "2157.60",
        "sales_per_day": "8",
        "sales_per_month": "240",
        "description": "<p>GP Ultra Plus alkaline AAA batteries.</p>",
    },
    {
        "id": 222,
        "name": "GP Ultra Plus AAA 8-Pack",
        "slug": "gp-ultra-plus-aaa-8-pack",
        "category_id": 41,
        "status": "active",
        "price": "15.49",
        "stock": 210,
        "sales_total": "140",
        "revenue_total": "2168.60",
        "sales_per_day": "5",
        "sales_per_month": "140",
        "description": "<p>GP Ultra Plus alkaline AAA batteries, 8 pack.</p>",
    },
    {
        "id": 223,
        "name": "GP Super AA 4-Pack",
        "slug": "gp-super-aa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "7.99",
        "stock": 350,
        "sales_total": "300",
        "revenue_total": "2397.00",
        "sales_per_day": "10",
        "sales_per_month": "300",
        "description": "<p>GP Super budget-friendly AA batteries.</p>",
    },
    {
        "id": 224,
        "name": "GP Super AAA 4-Pack",
        "slug": "gp-super-aaa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "6.99",
        "stock": 340,
        "sales_total": "280",
        "revenue_total": "1957.20",
        "sales_per_day": "9",
        "sales_per_month": "280",
        "description": "<p>GP Super budget-friendly AAA batteries.</p>",
    },
    {
        "id": 225,
        "name": "Energizer Industrial AA 10-Pack",
        "slug": "energizer-industrial-aa-10-pack-alk",
        "category_id": 41,
        "status": "active",
        "price": "29.99",
        "stock": 100,
        "sales_total": "45",
        "revenue_total": "1349.55",
        "sales_per_day": "2",
        "sales_per_month": "45",
        "description": "<p>Professional grade AA batteries for industrial use.</p>",
    },
    {
        "id": 226,
        "name": "Energizer Industrial AAA 10-Pack",
        "slug": "energizer-industrial-aaa-10-pack-alk",
        "category_id": 41,
        "status": "active",
        "price": "27.99",
        "stock": 95,
        "sales_total": "40",
        "revenue_total": "1119.60",
        "sales_per_day": "1",
        "sales_per_month": "40",
        "description": "<p>Professional grade AAA batteries for industrial use.</p>",
    },
    {
        "id": 227,
        "name": "Duracell Industrial AA 10-Pack",
        "slug": "duracell-industrial-aa-10-pack",
        "category_id": 41,
        "status": "active",
        "price": "31.99",
        "stock": 90,
        "sales_total": "35",
        "revenue_total": "1119.65",
        "sales_per_day": "1",
        "sales_per_month": "35",
        "description": "<p>Duracell Procell AA batteries for business.</p>",
    },
    {
        "id": 228,
        "name": "Duracell Industrial AAA 10-Pack",
        "slug": "duracell-industrial-aaa-10-pack",
        "category_id": 41,
        "status": "active",
        "price": "29.99",
        "stock": 85,
        "sales_total": "30",
        "revenue_total": "899.70",
        "sales_per_day": "1",
        "sales_per_month": "30",
        "description": "<p>Duracell Procell AAA batteries for business.</p>",
    },
    {
        "id": 229,
        "name": "Energizer MAX AA 12-Pack",
        "slug": "energizer-max-aa-12-pack",
        "category_id": 41,
        "status": "active",
        "price": "34.99",
        "stock": 120,
        "sales_total": "60",
        "revenue_total": "2099.40",
        "sales_per_day": "2",
        "sales_per_month": "60",
        "description": "<p>Family size 12-pack of AA batteries.</p>",
    },
    {
        "id": 230,
        "name": "Energizer MAX AAA 12-Pack",
        "slug": "energizer-max-aaa-12-pack",
        "category_id": 41,
        "status": "active",
        "price": "32.99",
        "stock": 115,
        "sales_total": "55",
        "revenue_total": "1814.45",
        "sales_per_day": "2",
        "sales_per_month": "55",
        "description": "<p>Family size 12-pack of AAA batteries.</p>",
    },
    {
        "id": 231,
        "name": "Duracell Plus AA 12-Pack",
        "slug": "duracell-plus-aa-12-pack",
        "category_id": 41,
        "status": "active",
        "price": "36.99",
        "stock": 110,
        "sales_total": "50",
        "revenue_total": "1849.50",
        "sales_per_day": "2",
        "sales_per_month": "50",
        "description": "<p>Duracell Plus Power AA 12-pack.</p>",
    },
    {
        "id": 232,
        "name": "Duracell Plus AAA 12-Pack",
        "slug": "duracell-plus-aaa-12-pack",
        "category_id": 41,
        "status": "active",
        "price": "34.99",
        "stock": 105,
        "sales_total": "45",
        "revenue_total": "1574.55",
        "sales_per_day": "2",
        "sales_per_month": "45",
        "description": "<p>Duracell Plus Power AAA 12-pack.</p>",
    },
    {
        "id": 233,
        "name": "Energizer MAX C 2-Pack",
        "slug": "energizer-max-c-2-pack",
        "category_id": 41,
        "status": "active",
        "price": "12.99",
        "stock": 80,
        "sales_total": "25",
        "revenue_total": "324.75",
        "sales_per_day": "1",
        "sales_per_month": "25",
        "description": "<p>Energizer MAX C size batteries, 2 pack.</p>",
    },
    {
        "id": 234,
        "name": "Energizer MAX D 2-Pack",
        "slug": "energizer-max-d-2-pack",
        "category_id": 41,
        "status": "active",
        "price": "14.99",
        "stock": 75,
        "sales_total": "20",
        "revenue_total": "299.80",
        "sales_per_day": "1",
        "sales_per_month": "20",
        "description": "<p>Energizer MAX D size batteries, 2 pack.</p>",
    },
    {
        "id": 235,
        "name": "Duracell Plus C 2-Pack",
        "slug": "duracell-plus-c-2-pack",
        "category_id": 41,
        "status": "active",
        "price": "13.49",
        "stock": 78,
        "sales_total": "22",
        "revenue_total": "296.78",
        "sales_per_day": "1",
        "sales_per_month": "22",
        "description": "<p>Duracell Plus C size batteries, 2 pack.</p>",
    },
    {
        "id": 236,
        "name": "Duracell Plus D 2-Pack",
        "slug": "duracell-plus-d-2-pack",
        "category_id": 41,
        "status": "active",
        "price": "15.49",
        "stock": 72,
        "sales_total": "18",
        "revenue_total": "278.82",
        "sales_per_day": "1",
        "sales_per_month": "18",
        "description": "<p>Duracell Plus D size batteries, 2 pack.</p>",
    },
    {
        "id": 237,
        "name": "Varta Longlife C 2-Pack",
        "slug": "varta-longlife-c-2-pack",
        "category_id": 41,
        "status": "active",
        "price": "11.99",
        "stock": 82,
        "sales_total": "28",
        "revenue_total": "335.72",
        "sales_per_day": "1",
        "sales_per_month": "28",
        "description": "<p>Varta Longlife C size batteries.</p>",
    },
    {
        "id": 238,
        "name": "Varta Longlife D 2-Pack",
        "slug": "varta-longlife-d-2-pack",
        "category_id": 41,
        "status": "active",
        "price": "13.99",
        "stock": 70,
        "sales_total": "15",
        "revenue_total": "209.85",
        "sales_per_day": "1",
        "sales_per_month": "15",
        "description": "<p>Varta Longlife D size batteries.</p>",
    },
    {
        "id": 239,
        "name": "Panasonic Evolta C 2-Pack",
        "slug": "panasonic-evolta-c-2-pack",
        "category_id": 41,
        "status": "active",
        "price": "12.49",
        "stock": 76,
        "sales_total": "24",
        "revenue_total": "299.76",
        "sales_per_day": "1",
        "sales_per_month": "24",
        "description": "<p>Panasonic Evolta C size batteries.</p>",
    },
    {
        "id": 240,
        "name": "Panasonic Evolta D 2-Pack",
        "slug": "panasonic-evolta-d-2-pack",
        "category_id": 41,
        "status": "active",
        "price": "14.49",
        "stock": 68,
        "sales_total": "16",
        "revenue_total": "231.84",
        "sales_per_day": "1",
        "sales_per_month": "16",
        "description": "<p>Panasonic Evolta D size batteries.</p>",
    },
    {
        "id": 241,
        "name": "Energizer MAX AA 24-Pack",
        "slug": "energizer-max-aa-24-pack",
        "category_id": 41,
        "status": "active",
        "price": "54.99",
        "stock": 60,
        "sales_total": "25",
        "revenue_total": "1374.75",
        "sales_per_day": "1",
        "sales_per_month": "25",
        "description": "<p>Bulk pack of 24 AA batteries.</p>",
    },
    {
        "id": 242,
        "name": "Energizer MAX AAA 24-Pack",
        "slug": "energizer-max-aaa-24-pack",
        "category_id": 41,
        "status": "active",
        "price": "49.99",
        "stock": 55,
        "sales_total": "22",
        "revenue_total": "1099.78",
        "sales_per_day": "1",
        "sales_per_month": "22",
        "description": "<p>Bulk pack of 24 AAA batteries.</p>",
    },
    {
        "id": 243,
        "name": "Duracell Plus AA 24-Pack",
        "slug": "duracell-plus-aa-24-pack",
        "category_id": 41,
        "status": "active",
        "price": "59.99",
        "stock": 50,
        "sales_total": "20",
        "revenue_total": "1199.80",
        "sales_per_day": "1",
        "sales_per_month": "20",
        "description": "<p>Duracell value pack of 24 AA batteries.</p>",
    },
    {
        "id": 244,
        "name": "Duracell Plus AAA 24-Pack",
        "slug": "duracell-plus-aaa-24-pack",
        "category_id": 41,
        "status": "active",
        "price": "54.99",
        "stock": 48,
        "sales_total": "18",
        "revenue_total": "989.82",
        "sales_per_day": "1",
        "sales_per_month": "18",
        "description": "<p>Duracell value pack of 24 AAA batteries.</p>",
    },
    {
        "id": 245,
        "name": "GP Ultra AA 16-Pack",
        "slug": "gp-ultra-aa-16-pack",
        "category_id": 41,
        "status": "active",
        "price": "29.99",
        "stock": 140,
        "sales_total": "80",
        "revenue_total": "2399.20",
        "sales_per_day": "3",
        "sales_per_month": "80",
        "description": "<p>GP Ultra alkaline AA family pack.</p>",
    },
    {
        "id": 246,
        "name": "GP Ultra AAA 16-Pack",
        "slug": "gp-ultra-aaa-16-pack",
        "category_id": 41,
        "status": "active",
        "price": "27.99",
        "stock": 135,
        "sales_total": "75",
        "revenue_total": "2099.25",
        "sales_per_day": "3",
        "sales_per_month": "75",
        "description": "<p>GP Ultra alkaline AAA family pack.</p>",
    },
    {
        "id": 247,
        "name": "Energizer Eco Advanced AA 4-Pack",
        "slug": "energizer-eco-advanced-aa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "16.99",
        "stock": 100,
        "sales_total": "45",
        "revenue_total": "764.55",
        "sales_per_day": "2",
        "sales_per_month": "45",
        "description": "<p>Made with recycled batteries - eco-friendly choice.</p>",
    },
    {
        "id": 248,
        "name": "Energizer Eco Advanced AAA 4-Pack",
        "slug": "energizer-eco-advanced-aaa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "15.99",
        "stock": 95,
        "sales_total": "40",
        "revenue_total": "639.60",
        "sales_per_day": "1",
        "sales_per_month": "40",
        "description": "<p>Made with recycled batteries - eco-friendly AAA.</p>",
    },
    {
        "id": 249,
        "name": "Varta Industrial AA 10-Pack",
        "slug": "varta-industrial-aa-10-pack",
        "category_id": 41,
        "status": "active",
        "price": "24.99",
        "stock": 110,
        "sales_total": "55",
        "revenue_total": "1374.45",
        "sales_per_day": "2",
        "sales_per_month": "55",
        "description": "<p>Varta Industrial Pro AA for professionals.</p>",
    },
    {
        "id": 250,
        "name": "Varta Industrial AAA 10-Pack",
        "slug": "varta-industrial-aaa-10-pack",
        "category_id": 41,
        "status": "active",
        "price": "22.99",
        "stock": 105,
        "sales_total": "50",
        "revenue_total": "1149.50",
        "sales_per_day": "2",
        "sales_per_month": "50",
        "description": "<p>Varta Industrial Pro AAA for professionals.</p>",
    },
    {
        "id": 251,
        "name": "Philips Power Life AA 4-Pack",
        "slug": "philips-power-life-aa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "8.99",
        "stock": 200,
        "sales_total": "160",
        "revenue_total": "1438.40",
        "sales_per_day": "5",
        "sales_per_month": "160",
        "description": "<p>Philips Power Life AA alkaline batteries.</p>",
    },
    {
        "id": 252,
        "name": "Philips Power Life AAA 4-Pack",
        "slug": "philips-power-life-aaa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "7.99",
        "stock": 195,
        "sales_total": "150",
        "revenue_total": "1198.50",
        "sales_per_day": "5",
        "sales_per_month": "150",
        "description": "<p>Philips Power Life AAA alkaline batteries.</p>",
    },
    {
        "id": 253,
        "name": "Philips Ultra Alkaline AA 4-Pack",
        "slug": "philips-ultra-aa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "11.49",
        "stock": 150,
        "sales_total": "90",
        "revenue_total": "1034.10",
        "sales_per_day": "3",
        "sales_per_month": "90",
        "description": "<p>Philips Ultra Alkaline AA for high performance.</p>",
    },
    {
        "id": 254,
        "name": "Philips Ultra Alkaline AAA 4-Pack",
        "slug": "philips-ultra-aaa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "10.49",
        "stock": 145,
        "sales_total": "85",
        "revenue_total": "891.65",
        "sales_per_day": "3",
        "sales_per_month": "85",
        "description": "<p>Philips Ultra Alkaline AAA for high performance.</p>",
    },
    {
        "id": 255,
        "name": "Sony Stamina Plus AA 4-Pack",
        "slug": "sony-stamina-plus-aa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "10.99",
        "stock": 170,
        "sales_total": "100",
        "revenue_total": "1099.00",
        "sales_per_day": "3",
        "sales_per_month": "100",
        "description": "<p>Sony Stamina Plus AA batteries.</p>",
    },
    {
        "id": 256,
        "name": "Sony Stamina Plus AAA 4-Pack",
        "slug": "sony-stamina-plus-aaa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "9.99",
        "stock": 165,
        "sales_total": "95",
        "revenue_total": "949.05",
        "sales_per_day": "3",
        "sales_per_month": "95",
        "description": "<p>Sony Stamina Plus AAA batteries.</p>",
    },
    {
        "id": 257,
        "name": "Rayovac High Energy AA 8-Pack",
        "slug": "rayovac-high-energy-aa-8-pack",
        "category_id": 41,
        "status": "active",
        "price": "14.99",
        "stock": 180,
        "sales_total": "110",
        "revenue_total": "1648.90",
        "sales_per_day": "4",
        "sales_per_month": "110",
        "description": "<p>Rayovac High Energy AA value pack.</p>",
    },
    {
        "id": 258,
        "name": "Rayovac High Energy AAA 8-Pack",
        "slug": "rayovac-high-energy-aaa-8-pack",
        "category_id": 41,
        "status": "active",
        "price": "13.99",
        "stock": 175,
        "sales_total": "105",
        "revenue_total": "1468.95",
        "sales_per_day": "4",
        "sales_per_month": "105",
        "description": "<p>Rayovac High Energy AAA value pack.</p>",
    },
    {
        "id": 259,
        "name": "Maxell Alkaline AA 4-Pack",
        "slug": "maxell-alkaline-aa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "7.49",
        "stock": 230,
        "sales_total": "180",
        "revenue_total": "1348.20",
        "sales_per_day": "6",
        "sales_per_month": "180",
        "description": "<p>Maxell alkaline AA everyday batteries.</p>",
    },
    {
        "id": 260,
        "name": "Maxell Alkaline AAA 4-Pack",
        "slug": "maxell-alkaline-aaa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "6.49",
        "stock": 225,
        "sales_total": "170",
        "revenue_total": "1103.30",
        "sales_per_day": "6",
        "sales_per_month": "170",
        "description": "<p>Maxell alkaline AAA everyday batteries.</p>",
    },
    {
        "id": 261,
        "name": "Kodak Xtralife AA 4-Pack",
        "slug": "kodak-xtralife-aa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "6.99",
        "stock": 260,
        "sales_total": "200",
        "revenue_total": "1398.00",
        "sales_per_day": "7",
        "sales_per_month": "200",
        "description": "<p>Kodak Xtralife alkaline AA batteries.</p>",
    },
    {
        "id": 262,
        "name": "Kodak Xtralife AAA 4-Pack",
        "slug": "kodak-xtralife-aaa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "5.99",
        "stock": 255,
        "sales_total": "190",
        "revenue_total": "1138.10",
        "sales_per_day": "6",
        "sales_per_month": "190",
        "description": "<p>Kodak Xtralife alkaline AAA batteries.</p>",
    },
    {
        "id": 263,
        "name": "Kodak Max AA 8-Pack",
        "slug": "kodak-max-aa-8-pack",
        "category_id": 41,
        "status": "active",
        "price": "12.99",
        "stock": 190,
        "sales_total": "120",
        "revenue_total": "1558.80",
        "sales_per_day": "4",
        "sales_per_month": "120",
        "description": "<p>Kodak Max alkaline AA 8-pack.</p>",
    },
    {
        "id": 264,
        "name": "Kodak Max AAA 8-Pack",
        "slug": "kodak-max-aaa-8-pack",
        "category_id": 41,
        "status": "active",
        "price": "11.99",
        "stock": 185,
        "sales_total": "115",
        "revenue_total": "1378.85",
        "sales_per_day": "4",
        "sales_per_month": "115",
        "description": "<p>Kodak Max alkaline AAA 8-pack.</p>",
    },
    {
        "id": 265,
        "name": "Energizer Ultimate Lithium AA 4-Pack",
        "slug": "energizer-lithium-aa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "24.99",
        "stock": 80,
        "sales_total": "35",
        "revenue_total": "874.65",
        "sales_per_day": "1",
        "sales_per_month": "35",
        "description": "<p>World's longest lasting AA battery.</p>",
    },
    {
        "id": 266,
        "name": "Energizer Ultimate Lithium AAA 4-Pack",
        "slug": "energizer-lithium-aaa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "22.99",
        "stock": 75,
        "sales_total": "30",
        "revenue_total": "689.70",
        "sales_per_day": "1",
        "sales_per_month": "30",
        "description": "<p>World's longest lasting AAA battery.</p>",
    },
    {
        "id": 267,
        "name": "Duracell Optimum AA 4-Pack",
        "slug": "duracell-optimum-aa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "18.99",
        "stock": 120,
        "sales_total": "65",
        "revenue_total": "1234.35",
        "sales_per_day": "2",
        "sales_per_month": "65",
        "description": "<p>Duracell Optimum extra power AA.</p>",
    },
    {
        "id": 268,
        "name": "Duracell Optimum AAA 4-Pack",
        "slug": "duracell-optimum-aaa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "17.99",
        "stock": 115,
        "sales_total": "60",
        "revenue_total": "1079.40",
        "sales_per_day": "2",
        "sales_per_month": "60",
        "description": "<p>Duracell Optimum extra power AAA.</p>",
    },
    {
        "id": 269,
        "name": "Energizer MAX Plus AA 4-Pack",
        "slug": "energizer-max-plus-aa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "16.49",
        "stock": 140,
        "sales_total": "75",
        "revenue_total": "1236.75",
        "sales_per_day": "3",
        "sales_per_month": "75",
        "description": "<p>Energizer MAX Plus enhanced performance.</p>",
    },
    {
        "id": 270,
        "name": "Energizer MAX Plus AAA 4-Pack",
        "slug": "energizer-max-plus-aaa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "15.49",
        "stock": 135,
        "sales_total": "70",
        "revenue_total": "1084.30",
        "sales_per_day": "2",
        "sales_per_month": "70",
        "description": "<p>Energizer MAX Plus enhanced performance AAA.</p>",
    },
    {
        "id": 271,
        "name": "GP ReCyko AA 4-Pack (Rechargeable)",
        "slug": "gp-recyko-aa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "19.99",
        "stock": 90,
        "sales_total": "40",
        "revenue_total": "799.60",
        "sales_per_day": "1",
        "sales_per_month": "40",
        "description": "<p>GP ReCyko rechargeable AA - up to 1000 cycles.</p>",
    },
    {
        "id": 272,
        "name": "GP ReCyko AAA 4-Pack (Rechargeable)",
        "slug": "gp-recyko-aaa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "17.99",
        "stock": 85,
        "sales_total": "35",
        "revenue_total": "629.65",
        "sales_per_day": "1",
        "sales_per_month": "35",
        "description": "<p>GP ReCyko rechargeable AAA - up to 1000 cycles.</p>",
    },
    {
        "id": 273,
        "name": "Panasonic Eneloop AA 4-Pack",
        "slug": "panasonic-eneloop-aa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "24.99",
        "stock": 70,
        "sales_total": "30",
        "revenue_total": "749.70",
        "sales_per_day": "1",
        "sales_per_month": "30",
        "description": "<p>Panasonic Eneloop rechargeable AA - 2100 cycles.</p>",
    },
    {
        "id": 274,
        "name": "Panasonic Eneloop AAA 4-Pack",
        "slug": "panasonic-eneloop-aaa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "22.99",
        "stock": 65,
        "sales_total": "25",
        "revenue_total": "574.75",
        "sales_per_day": "1",
        "sales_per_month": "25",
        "description": "<p>Panasonic Eneloop rechargeable AAA - 2100 cycles.</p>",
    },
    {
        "id": 275,
        "name": "Amazon Basics AA 20-Pack",
        "slug": "amazon-basics-aa-20-pack",
        "category_id": 41,
        "status": "active",
        "price": "29.99",
        "stock": 200,
        "sales_total": "150",
        "revenue_total": "4498.50",
        "sales_per_day": "5",
        "sales_per_month": "150",
        "description": "<p>Amazon Basics high-performance AA batteries.</p>",
    },
    {
        "id": 276,
        "name": "Amazon Basics AAA 20-Pack",
        "slug": "amazon-basics-aaa-20-pack",
        "category_id": 41,
        "status": "active",
        "price": "27.99",
        "stock": 195,
        "sales_total": "145",
        "revenue_total": "4058.55",
        "sales_per_day": "5",
        "sales_per_month": "145",
        "description": "<p>Amazon Basics high-performance AAA batteries.</p>",
    },
    {
        "id": 277,
        "name": "Amazon Basics AA 48-Pack",
        "slug": "amazon-basics-aa-48-pack",
        "category_id": 41,
        "status": "active",
        "price": "59.99",
        "stock": 80,
        "sales_total": "40",
        "revenue_total": "2399.60",
        "sales_per_day": "1",
        "sales_per_month": "40",
        "description": "<p>Amazon Basics bulk pack of 48 AA batteries.</p>",
    },
    {
        "id": 278,
        "name": "Amazon Basics AAA 48-Pack",
        "slug": "amazon-basics-aaa-48-pack",
        "category_id": 41,
        "status": "active",
        "price": "54.99",
        "stock": 75,
        "sales_total": "35",
        "revenue_total": "1924.65",
        "sales_per_day": "1",
        "sales_per_month": "35",
        "description": "<p>Amazon Basics bulk pack of 48 AAA batteries.</p>",
    },
    {
        "id": 279,
        "name": "Ikea LADDA AA 4-Pack",
        "slug": "ikea-ladda-aa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "9.99",
        "stock": 150,
        "sales_total": "100",
        "revenue_total": "999.00",
        "sales_per_day": "3",
        "sales_per_month": "100",
        "description": "<p>Ikea LADDA rechargeable AA batteries.</p>",
    },
    {
        "id": 280,
        "name": "Ikea LADDA AAA 4-Pack",
        "slug": "ikea-ladda-aaa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "8.99",
        "stock": 145,
        "sales_total": "95",
        "revenue_total": "854.05",
        "sales_per_day": "3",
        "sales_per_month": "95",
        "description": "<p>Ikea LADDA rechargeable AAA batteries.</p>",
    },
    {
        "id": 281,
        "name": "Energizer Power Seal AA 6-Pack",
        "slug": "energizer-power-seal-aa-6-pack",
        "category_id": 41,
        "status": "active",
        "price": "18.99",
        "stock": 130,
        "sales_total": "70",
        "revenue_total": "1329.30",
        "sales_per_day": "2",
        "sales_per_month": "70",
        "description": "<p>Energizer with Power Seal technology.</p>",
    },
    {
        "id": 282,
        "name": "Energizer Power Seal AAA 6-Pack",
        "slug": "energizer-power-seal-aaa-6-pack",
        "category_id": 41,
        "status": "active",
        "price": "17.49",
        "stock": 125,
        "sales_total": "65",
        "revenue_total": "1136.85",
        "sales_per_day": "2",
        "sales_per_month": "65",
        "description": "<p>Energizer AAA with Power Seal technology.</p>",
    },
    {
        "id": 283,
        "name": "Toshiba High Power AA 4-Pack",
        "slug": "toshiba-high-power-aa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "8.49",
        "stock": 180,
        "sales_total": "120",
        "revenue_total": "1018.80",
        "sales_per_day": "4",
        "sales_per_month": "120",
        "description": "<p>Toshiba High Power alkaline AA.</p>",
    },
    {
        "id": 284,
        "name": "Toshiba High Power AAA 4-Pack",
        "slug": "toshiba-high-power-aaa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "7.49",
        "stock": 175,
        "sales_total": "115",
        "revenue_total": "861.35",
        "sales_per_day": "4",
        "sales_per_month": "115",
        "description": "<p>Toshiba High Power alkaline AAA.</p>",
    },
    {
        "id": 285,
        "name": "Sanyo Eneloop Pro AA 4-Pack",
        "slug": "sanyo-eneloop-pro-aa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "29.99",
        "stock": 60,
        "sales_total": "25",
        "revenue_total": "749.75",
        "sales_per_day": "1",
        "sales_per_month": "25",
        "description": "<p>High capacity rechargeable AA.</p>",
    },
    {
        "id": 286,
        "name": "Sanyo Eneloop Pro AAA 4-Pack",
        "slug": "sanyo-eneloop-pro-aaa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "27.99",
        "stock": 55,
        "sales_total": "20",
        "revenue_total": "559.80",
        "sales_per_day": "1",
        "sales_per_month": "20",
        "description": "<p>High capacity rechargeable AAA.</p>",
    },
    {
        "id": 287,
        "name": "Varta Recharge Accu Power AA 4-Pack",
        "slug": "varta-recharge-aa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "21.99",
        "stock": 75,
        "sales_total": "35",
        "revenue_total": "769.65",
        "sales_per_day": "1",
        "sales_per_month": "35",
        "description": "<p>Varta rechargeable AA 2600mAh.</p>",
    },
    {
        "id": 288,
        "name": "Varta Recharge Accu Power AAA 4-Pack",
        "slug": "varta-recharge-aaa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "19.99",
        "stock": 70,
        "sales_total": "30",
        "revenue_total": "599.70",
        "sales_per_day": "1",
        "sales_per_month": "30",
        "description": "<p>Varta rechargeable AAA 1000mAh.</p>",
    },
    {
        "id": 289,
        "name": "Duracell Recharge Ultra AA 4-Pack",
        "slug": "duracell-recharge-ultra-aa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "23.99",
        "stock": 65,
        "sales_total": "28",
        "revenue_total": "671.72",
        "sales_per_day": "1",
        "sales_per_month": "28",
        "description": "<p>Duracell rechargeable AA 2500mAh.</p>",
    },
    {
        "id": 290,
        "name": "Duracell Recharge Ultra AAA 4-Pack",
        "slug": "duracell-recharge-ultra-aaa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "21.99",
        "stock": 60,
        "sales_total": "25",
        "revenue_total": "549.75",
        "sales_per_day": "1",
        "sales_per_month": "25",
        "description": "<p>Duracell rechargeable AAA 900mAh.</p>",
    },
    {
        "id": 291,
        "name": "Energizer Recharge Universal AA 4-Pack",
        "slug": "energizer-recharge-aa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "19.99",
        "stock": 80,
        "sales_total": "38",
        "revenue_total": "759.62",
        "sales_per_day": "1",
        "sales_per_month": "38",
        "description": "<p>Energizer rechargeable AA 2000mAh.</p>",
    },
    {
        "id": 292,
        "name": "Energizer Recharge Universal AAA 4-Pack",
        "slug": "energizer-recharge-aaa-4-pack",
        "category_id": 41,
        "status": "active",
        "price": "17.99",
        "stock": 75,
        "sales_total": "33",
        "revenue_total": "593.67",
        "sales_per_day": "1",
        "sales_per_month": "33",
        "description": "<p>Energizer rechargeable AAA 700mAh.</p>",
    },
    {
        "id": 293,
        "name": "GP Super Alkaline C 2-Pack",
        "slug": "gp-super-c-2-pack",
        "category_id": 41,
        "status": "active",
        "price": "8.99",
        "stock": 100,
        "sales_total": "50",
        "revenue_total": "449.50",
        "sales_per_day": "2",
        "sales_per_month": "50",
        "description": "<p>GP Super alkaline C size batteries.</p>",
    },
    {
        "id": 294,
        "name": "GP Super Alkaline D 2-Pack",
        "slug": "gp-super-d-2-pack",
        "category_id": 41,
        "status": "active",
        "price": "10.99",
        "stock": 95,
        "sales_total": "45",
        "revenue_total": "494.55",
        "sales_per_day": "2",
        "sales_per_month": "45",
        "description": "<p>GP Super alkaline D size batteries.</p>",
    },
    {
        "id": 295,
        "name": "Energizer AA 36-Pack Value Box",
        "slug": "energizer-aa-36-pack-box",
        "category_id": 41,
        "status": "active",
        "price": "69.99",
        "stock": 40,
        "sales_total": "15",
        "revenue_total": "1049.85",
        "sales_per_day": "1",
        "sales_per_month": "15",
        "description": "<p>Energizer family value box of 36 AA batteries.</p>",
    },
    {
        "id": 296,
        "name": "Energizer AAA 36-Pack Value Box",
        "slug": "energizer-aaa-36-pack-box",
        "category_id": 41,
        "status": "active",
        "price": "64.99",
        "stock": 38,
        "sales_total": "12",
        "revenue_total": "779.88",
        "sales_per_day": "1",
        "sales_per_month": "12",
        "description": "<p>Energizer family value box of 36 AAA batteries.</p>",
    },
    {
        "id": 297,
        "name": "Duracell AA 36-Pack Value Box",
        "slug": "duracell-aa-36-pack-box",
        "category_id": 41,
        "status": "active",
        "price": "74.99",
        "stock": 35,
        "sales_total": "10",
        "revenue_total": "749.90",
        "sales_per_day": "1",
        "sales_per_month": "10",
        "description": "<p>Duracell family value box of 36 AA batteries.</p>",
    },
    {
        "id": 298,
        "name": "Duracell AAA 36-Pack Value Box",
        "slug": "duracell-aaa-36-pack-box",
        "category_id": 41,
        "status": "active",
        "price": "69.99",
        "stock": 32,
        "sales_total": "8",
        "revenue_total": "559.92",
        "sales_per_day": "1",
        "sales_per_month": "8",
        "description": "<p>Duracell family value box of 36 AAA batteries.</p>",
    },
    {
        "id": 299,
        "name": "Varta AA 40-Pack Megabox",
        "slug": "varta-aa-40-pack-megabox",
        "category_id": 41,
        "status": "active",
        "price": "49.99",
        "stock": 50,
        "sales_total": "25",
        "revenue_total": "1249.75",
        "sales_per_day": "1",
        "sales_per_month": "25",
        "description": "<p>Varta megabox of 40 AA batteries.</p>",
    },
    {
        "id": 300,
        "name": "Varta AAA 40-Pack Megabox",
        "slug": "varta-aaa-40-pack-megabox",
        "category_id": 41,
        "status": "active",
        "price": "44.99",
        "stock": 48,
        "sales_total": "22",
        "revenue_total": "989.78",
        "sales_per_day": "1",
        "sales_per_month": "22",
        "description": "<p>Varta megabox of 40 AAA batteries.</p>",
    },
    {
        "id": 301,
        "name": "Energizer AA & AAA Combo 24-Pack",
        "slug": "energizer-combo-pack-24",
        "category_id": 41,
        "status": "active",
        "price": "44.99",
        "stock": 60,
        "sales_total": "30",
        "revenue_total": "1349.70",
        "sales_per_day": "1",
        "sales_per_month": "30",
        "description": "<p>12x AA + 12x AAA combo pack.</p>",
    },
    {
        "id": 302,
        "name": "Duracell AA & AAA Combo 24-Pack",
        "slug": "duracell-combo-pack-24",
        "category_id": 41,
        "status": "active",
        "price": "47.99",
        "stock": 55,
        "sales_total": "28",
        "revenue_total": "1343.72",
        "sales_per_day": "1",
        "sales_per_month": "28",
        "description": "<p>12x AA + 12x AAA Duracell combo pack.</p>",
    },
    {
        "id": 303,
        "name": "GP Premium AA 10-Pack",
        "slug": "gp-premium-aa-10-pack",
        "category_id": 41,
        "status": "active",
        "price": "16.99",
        "stock": 160,
        "sales_total": "95",
        "revenue_total": "1614.05",
        "sales_per_day": "3",
        "sales_per_month": "95",
        "description": "<p>GP Premium alkaline AA 10-pack.</p>",
    },
    {
        "id": 304,
        "name": "GP Premium AAA 10-Pack",
        "slug": "gp-premium-aaa-10-pack",
        "category_id": 41,
        "status": "active",
        "price": "14.99",
        "stock": 155,
        "sales_total": "90",
        "revenue_total": "1349.10",
        "sales_per_day": "3",
        "sales_per_month": "90",
        "description": "<p>GP Premium alkaline AAA 10-pack.</p>",
    },
    {
        "id": 340,
        "name": "Philips Power AA 8-Pack",
        "slug": "philips-power-aa-8-pack",
        "category_id": 41,
        "status": "active",
        "price": "13.99",
        "stock": 140,
        "sales_total": "80",
        "revenue_total": "1119.20",
        "sales_per_day": "3",
        "sales_per_month": "80",
        "description": "<p>Philips Power alkaline AA 8-pack.</p>",
    },
    {
        "id": 341,
        "name": "Philips Power AAA 8-Pack",
        "slug": "philips-power-aaa-8-pack",
        "category_id": 41,
        "status": "active",
        "price": "12.49",
        "stock": 135,
        "sales_total": "75",
        "revenue_total": "936.75",
        "sales_per_day": "3",
        "sales_per_month": "75",
        "description": "<p>Philips Power alkaline AAA 8-pack.</p>",
    },
    {
        "id": 342,
        "name": "Rayovac Fusion AA 8-Pack",
        "slug": "rayovac-fusion-aa-8-pack",
        "category_id": 41,
        "status": "active",
        "price": "15.99",
        "stock": 120,
        "sales_total": "65",
        "revenue_total": "1039.35",
        "sales_per_day": "2",
        "sales_per_month": "65",
        "description": "<p>Rayovac Fusion premium AA batteries.</p>",
    },
    {
        "id": 343,
        "name": "Rayovac Fusion AAA 8-Pack",
        "slug": "rayovac-fusion-aaa-8-pack",
        "category_id": 41,
        "status": "active",
        "price": "14.49",
        "stock": 115,
        "sales_total": "60",
        "revenue_total": "869.40",
        "sales_per_day": "2",
        "sales_per_month": "60",
        "description": "<p>Rayovac Fusion premium AAA batteries.</p>",
    },
    {
        "id": 344,
        "name": "Maxell Gold AA 6-Pack",
        "slug": "maxell-gold-aa-6-pack",
        "category_id": 41,
        "status": "active",
        "price": "11.99",
        "stock": 160,
        "sales_total": "100",
        "revenue_total": "1199.00",
        "sales_per_day": "3",
        "sales_per_month": "100",
        "description": "<p>Maxell Gold alkaline AA batteries.</p>",
    },
    {
        "id": 345,
        "name": "Maxell Gold AAA 6-Pack",
        "slug": "maxell-gold-aaa-6-pack",
        "category_id": 41,
        "status": "active",
        "price": "10.99",
        "stock": 155,
        "sales_total": "95",
        "revenue_total": "1044.05",
        "sales_per_day": "3",
        "sales_per_month": "95",
        "description": "<p>Maxell Gold alkaline AAA batteries.</p>",
    },
    {
        "id": 346,
        "name": "Energizer Max AA 16-Pack",
        "slug": "energizer-max-aa-16-pack",
        "category_id": 41,
        "status": "active",
        "price": "39.99",
        "stock": 90,
        "sales_total": "45",
        "revenue_total": "1799.55",
        "sales_per_day": "2",
        "sales_per_month": "45",
        "description": "<p>Energizer Max AA family 16-pack.</p>",
    },
    {
        "id": 347,
        "name": "Energizer Max AAA 16-Pack",
        "slug": "energizer-max-aaa-16-pack",
        "category_id": 41,
        "status": "active",
        "price": "37.99",
        "stock": 85,
        "sales_total": "40",
        "revenue_total": "1519.60",
        "sales_per_day": "1",
        "sales_per_month": "40",
        "description": "<p>Energizer Max AAA family 16-pack.</p>",
    },
    # Additional products to reach 144+ total
    {
        "id": 348,
        "name": "Panasonic Pro Power AA 4-Pack",
        "slug": "panasonic-pro-power-aa-4",
        "category_id": 41,
        "status": "active",
        "price": "11.49",
        "stock": 180,
        "sales_total": "110",
        "revenue_total": "1263.90",
        "sales_per_day": "4",
        "sales_per_month": "110",
        "description": "<p>Panasonic Pro Power alkaline AA.</p>",
    },
    {
        "id": 349,
        "name": "Panasonic Pro Power AAA 4-Pack",
        "slug": "panasonic-pro-power-aaa-4",
        "category_id": 41,
        "status": "active",
        "price": "10.49",
        "stock": 175,
        "sales_total": "105",
        "revenue_total": "1101.45",
        "sales_per_day": "4",
        "sales_per_month": "105",
        "description": "<p>Panasonic Pro Power alkaline AAA.</p>",
    },
    {
        "id": 350,
        "name": "Panasonic Pro Power AA 8-Pack",
        "slug": "panasonic-pro-power-aa-8",
        "category_id": 41,
        "status": "active",
        "price": "19.99",
        "stock": 120,
        "sales_total": "65",
        "revenue_total": "1299.35",
        "sales_per_day": "2",
        "sales_per_month": "65",
        "description": "<p>Panasonic Pro Power AA 8 pack.</p>",
    },
    {
        "id": 351,
        "name": "Panasonic Pro Power AAA 8-Pack",
        "slug": "panasonic-pro-power-aaa-8",
        "category_id": 41,
        "status": "active",
        "price": "18.49",
        "stock": 115,
        "sales_total": "60",
        "revenue_total": "1109.40",
        "sales_per_day": "2",
        "sales_per_month": "60",
        "description": "<p>Panasonic Pro Power AAA 8 pack.</p>",
    },
    {
        "id": 352,
        "name": "Camelion Plus AA 4-Pack",
        "slug": "camelion-plus-aa-4",
        "category_id": 41,
        "status": "active",
        "price": "5.99",
        "stock": 300,
        "sales_total": "220",
        "revenue_total": "1317.80",
        "sales_per_day": "7",
        "sales_per_month": "220",
        "description": "<p>Budget-friendly Camelion AA batteries.</p>",
    },
    {
        "id": 353,
        "name": "Camelion Plus AAA 4-Pack",
        "slug": "camelion-plus-aaa-4",
        "category_id": 41,
        "status": "active",
        "price": "4.99",
        "stock": 290,
        "sales_total": "210",
        "revenue_total": "1047.90",
        "sales_per_day": "7",
        "sales_per_month": "210",
        "description": "<p>Budget-friendly Camelion AAA batteries.</p>",
    },
    {
        "id": 354,
        "name": "Camelion Plus AA 8-Pack",
        "slug": "camelion-plus-aa-8",
        "category_id": 41,
        "status": "active",
        "price": "9.99",
        "stock": 200,
        "sales_total": "140",
        "revenue_total": "1398.60",
        "sales_per_day": "5",
        "sales_per_month": "140",
        "description": "<p>Camelion AA value 8-pack.</p>",
    },
    {
        "id": 355,
        "name": "Camelion Plus AAA 8-Pack",
        "slug": "camelion-plus-aaa-8",
        "category_id": 41,
        "status": "active",
        "price": "8.99",
        "stock": 195,
        "sales_total": "135",
        "revenue_total": "1213.65",
        "sales_per_day": "5",
        "sales_per_month": "135",
        "description": "<p>Camelion AAA value 8-pack.</p>",
    },
    {
        "id": 356,
        "name": "Fujitsu G Plus AA 4-Pack",
        "slug": "fujitsu-g-plus-aa-4",
        "category_id": 41,
        "status": "active",
        "price": "12.99",
        "stock": 130,
        "sales_total": "70",
        "revenue_total": "909.30",
        "sales_per_day": "2",
        "sales_per_month": "70",
        "description": "<p>Fujitsu G Plus alkaline AA batteries.</p>",
    },
    {
        "id": 357,
        "name": "Fujitsu G Plus AAA 4-Pack",
        "slug": "fujitsu-g-plus-aaa-4",
        "category_id": 41,
        "status": "active",
        "price": "11.99",
        "stock": 125,
        "sales_total": "65",
        "revenue_total": "779.35",
        "sales_per_day": "2",
        "sales_per_month": "65",
        "description": "<p>Fujitsu G Plus alkaline AAA batteries.</p>",
    },
    {
        "id": 358,
        "name": "Eveready Gold AA 4-Pack",
        "slug": "eveready-gold-aa-4",
        "category_id": 41,
        "status": "active",
        "price": "7.99",
        "stock": 220,
        "sales_total": "160",
        "revenue_total": "1278.40",
        "sales_per_day": "5",
        "sales_per_month": "160",
        "description": "<p>Eveready Gold AA batteries.</p>",
    },
    {
        "id": 359,
        "name": "Eveready Gold AAA 4-Pack",
        "slug": "eveready-gold-aaa-4",
        "category_id": 41,
        "status": "active",
        "price": "6.99",
        "stock": 215,
        "sales_total": "155",
        "revenue_total": "1083.45",
        "sales_per_day": "5",
        "sales_per_month": "155",
        "description": "<p>Eveready Gold AAA batteries.</p>",
    },
    {
        "id": 360,
        "name": "Eveready Super Heavy Duty AA 4-Pack",
        "slug": "eveready-heavy-duty-aa-4",
        "category_id": 41,
        "status": "active",
        "price": "4.49",
        "stock": 350,
        "sales_total": "280",
        "revenue_total": "1257.20",
        "sales_per_day": "9",
        "sales_per_month": "280",
        "description": "<p>Eveready Super Heavy Duty AA - budget choice.</p>",
    },
    {
        "id": 361,
        "name": "Eveready Super Heavy Duty AAA 4-Pack",
        "slug": "eveready-heavy-duty-aaa-4",
        "category_id": 41,
        "status": "active",
        "price": "3.99",
        "stock": 340,
        "sales_total": "270",
        "revenue_total": "1077.30",
        "sales_per_day": "9",
        "sales_per_month": "270",
        "description": "<p>Eveready Super Heavy Duty AAA - budget choice.</p>",
    },
    {
        "id": 362,
        "name": "Energizer AA + Charger Kit",
        "slug": "energizer-aa-charger-kit",
        "category_id": 41,
        "status": "active",
        "price": "34.99",
        "stock": 50,
        "sales_total": "22",
        "revenue_total": "769.78",
        "sales_per_day": "1",
        "sales_per_month": "22",
        "description": "<p>4x rechargeable AA + Base Charger.</p>",
    },
    {
        "id": 363,
        "name": "Energizer AAA + Charger Kit",
        "slug": "energizer-aaa-charger-kit",
        "category_id": 41,
        "status": "active",
        "price": "32.99",
        "stock": 48,
        "sales_total": "20",
        "revenue_total": "659.80",
        "sales_per_day": "1",
        "sales_per_month": "20",
        "description": "<p>4x rechargeable AAA + Base Charger.</p>",
    },
    {
        "id": 364,
        "name": "Duracell AA + Charger Kit",
        "slug": "duracell-aa-charger-kit",
        "category_id": 41,
        "status": "active",
        "price": "39.99",
        "stock": 45,
        "sales_total": "18",
        "revenue_total": "719.82",
        "sales_per_day": "1",
        "sales_per_month": "18",
        "description": "<p>4x rechargeable AA + Duracell Charger.</p>",
    },
    {
        "id": 365,
        "name": "Duracell AAA + Charger Kit",
        "slug": "duracell-aaa-charger-kit",
        "category_id": 41,
        "status": "active",
        "price": "37.99",
        "stock": 42,
        "sales_total": "15",
        "revenue_total": "569.85",
        "sales_per_day": "1",
        "sales_per_month": "15",
        "description": "<p>4x rechargeable AAA + Duracell Charger.</p>",
    },
    {
        "id": 366,
        "name": "Ansmann Industrial AA 10-Pack",
        "slug": "ansmann-industrial-aa-10",
        "category_id": 41,
        "status": "active",
        "price": "18.99",
        "stock": 100,
        "sales_total": "55",
        "revenue_total": "1044.45",
        "sales_per_day": "2",
        "sales_per_month": "55",
        "description": "<p>Ansmann Industrial alkaline AA.</p>",
    },
    {
        "id": 367,
        "name": "Ansmann Industrial AAA 10-Pack",
        "slug": "ansmann-industrial-aaa-10",
        "category_id": 41,
        "status": "active",
        "price": "16.99",
        "stock": 95,
        "sales_total": "50",
        "revenue_total": "849.50",
        "sales_per_day": "2",
        "sales_per_month": "50",
        "description": "<p>Ansmann Industrial alkaline AAA.</p>",
    },
    {
        "id": 368,
        "name": "Procell AA 10-Pack",
        "slug": "procell-aa-10-pack",
        "category_id": 41,
        "status": "active",
        "price": "22.99",
        "stock": 80,
        "sales_total": "40",
        "revenue_total": "919.60",
        "sales_per_day": "1",
        "sales_per_month": "40",
        "description": "<p>Procell (by Duracell) professional AA.</p>",
    },
    {
        "id": 369,
        "name": "Procell AAA 10-Pack",
        "slug": "procell-aaa-10-pack",
        "category_id": 41,
        "status": "active",
        "price": "20.99",
        "stock": 75,
        "sales_total": "35",
        "revenue_total": "734.65",
        "sales_per_day": "1",
        "sales_per_month": "35",
        "description": "<p>Procell (by Duracell) professional AAA.</p>",
    },
    {
        "id": 370,
        "name": "Energizer Industrial LR14 C 12-Pack",
        "slug": "energizer-industrial-c-12",
        "category_id": 41,
        "status": "active",
        "price": "49.99",
        "stock": 40,
        "sales_total": "15",
        "revenue_total": "749.85",
        "sales_per_day": "1",
        "sales_per_month": "15",
        "description": "<p>Industrial C batteries 12-pack.</p>",
    },
    {
        "id": 371,
        "name": "Energizer Industrial LR20 D 12-Pack",
        "slug": "energizer-industrial-d-12",
        "category_id": 41,
        "status": "active",
        "price": "54.99",
        "stock": 35,
        "sales_total": "12",
        "revenue_total": "659.88",
        "sales_per_day": "1",
        "sales_per_month": "12",
        "description": "<p>Industrial D batteries 12-pack.</p>",
    },
    {
        "id": 372,
        "name": "GP Super Alkaline AA 12-Pack",
        "slug": "gp-super-aa-12-pack",
        "category_id": 41,
        "status": "active",
        "price": "17.99",
        "stock": 150,
        "sales_total": "90",
        "revenue_total": "1619.10",
        "sales_per_day": "3",
        "sales_per_month": "90",
        "description": "<p>GP Super AA value 12-pack.</p>",
    },
    {
        "id": 373,
        "name": "GP Super Alkaline AAA 12-Pack",
        "slug": "gp-super-aaa-12-pack",
        "category_id": 41,
        "status": "active",
        "price": "15.99",
        "stock": 145,
        "sales_total": "85",
        "revenue_total": "1359.15",
        "sales_per_day": "3",
        "sales_per_month": "85",
        "description": "<p>GP Super AAA value 12-pack.</p>",
    },
    {
        "id": 374,
        "name": "Varta AA & AAA Combo 20-Pack",
        "slug": "varta-combo-20",
        "category_id": 41,
        "status": "active",
        "price": "34.99",
        "stock": 70,
        "sales_total": "35",
        "revenue_total": "1224.65",
        "sales_per_day": "1",
        "sales_per_month": "35",
        "description": "<p>10x AA + 10x AAA combo.</p>",
    },
    {
        "id": 375,
        "name": "Energizer Max Power Seal AA 20-Pack",
        "slug": "energizer-power-seal-aa-20",
        "category_id": 41,
        "status": "active",
        "price": "44.99",
        "stock": 65,
        "sales_total": "30",
        "revenue_total": "1349.70",
        "sales_per_day": "1",
        "sales_per_month": "30",
        "description": "<p>Power Seal technology 20-pack.</p>",
    },
    {
        "id": 376,
        "name": "Energizer Max Power Seal AAA 20-Pack",
        "slug": "energizer-power-seal-aaa-20",
        "category_id": 41,
        "status": "active",
        "price": "42.99",
        "stock": 60,
        "sales_total": "25",
        "revenue_total": "1074.75",
        "sales_per_day": "1",
        "sales_per_month": "25",
        "description": "<p>Power Seal technology AAA 20-pack.</p>",
    },
    {
        "id": 377,
        "name": "Duracell Coppertop AA 4-Pack",
        "slug": "duracell-coppertop-aa-4",
        "category_id": 41,
        "status": "active",
        "price": "13.99",
        "stock": 200,
        "sales_total": "125",
        "revenue_total": "1748.75",
        "sales_per_day": "4",
        "sales_per_month": "125",
        "description": "<p>Duracell Coppertop reliable AA.</p>",
    },
    {
        "id": 378,
        "name": "Duracell Coppertop AAA 4-Pack",
        "slug": "duracell-coppertop-aaa-4",
        "category_id": 41,
        "status": "active",
        "price": "12.99",
        "stock": 195,
        "sales_total": "120",
        "revenue_total": "1558.80",
        "sales_per_day": "4",
        "sales_per_month": "120",
        "description": "<p>Duracell Coppertop reliable AAA.</p>",
    },
    {
        "id": 379,
        "name": "Duracell Coppertop AA 8-Pack",
        "slug": "duracell-coppertop-aa-8",
        "category_id": 41,
        "status": "active",
        "price": "23.99",
        "stock": 140,
        "sales_total": "75",
        "revenue_total": "1799.25",
        "sales_per_day": "3",
        "sales_per_month": "75",
        "description": "<p>Duracell Coppertop AA 8-pack.</p>",
    },
    {
        "id": 380,
        "name": "Duracell Coppertop AAA 8-Pack",
        "slug": "duracell-coppertop-aaa-8",
        "category_id": 41,
        "status": "active",
        "price": "21.99",
        "stock": 135,
        "sales_total": "70",
        "revenue_total": "1539.30",
        "sales_per_day": "2",
        "sales_per_month": "70",
        "description": "<p>Duracell Coppertop AAA 8-pack.</p>",
    },
]

PRODUCT_IMAGES_DATA = [
    {
        "id": 37,
        "product_id": 50,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Energizer MAX AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 38,
        "product_id": 51,
        "image": "product-images/energizer-silver-watch-battery-155v.jpg",
        "alt_text": "Energizer Silver Watch Battery 1.55V",
        "sort_order": 0,
    },
    {
        "id": 39,
        "product_id": 52,
        "image": "product-images/novita-intimate-wet-wipes-15pcs.jpg",
        "alt_text": "Novita Intimate Wet Wipes 15pcs",
        "sort_order": 0,
    },
    {
        "id": 40,
        "product_id": 53,
        "image": "product-images/california-scents-car-freshener-coronado-cherry-42.jpg",
        "alt_text": "California Scents Car Freshener Coronado Cherry 42g",
        "sort_order": 0,
    },
    {
        "id": 41,
        "product_id": 54,
        "image": "product-images/energizer-led-r50-e14-62w-450-lumens.jpg",
        "alt_text": "Energizer LED R50 E14 6.2W 450 Lumens",
        "sort_order": 0,
    },
    {
        "id": 42,
        "product_id": 55,
        "image": "product-images/smile-wet-wipes-cars-jackson-storm-15pcs.jpg",
        "alt_text": "Smile Wet Wipes Cars Jackson Storm 15pcs",
        "sort_order": 0,
    },
    {
        "id": 43,
        "product_id": 56,
        "image": "product-images/smile-baby-wet-wipes-with-chamomile-60pcs.jpg",
        "alt_text": "Smile Baby Wet Wipes with Chamomile 60pcs",
        "sort_order": 0,
    },
    {
        "id": 44,
        "product_id": 57,
        "image": "product-images/refresh-your-car-diffuser-new-carcool-breeze-7ml.jpg",
        "alt_text": "Refresh Your Car Diffuser New Car/Cool Breeze 7ml",
        "sort_order": 0,
    },
    {
        "id": 45,
        "product_id": 58,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Energizer Alkaline Power 9V 1-Pack",
        "sort_order": 0,
    },
    {
        "id": 46,
        "product_id": 59,
        "image": "product-images/novita-intimate-wet-wipes-15pcs.jpg",
        "alt_text": "Novita Wet Wipes Anti-bacterial 15pcs",
        "sort_order": 0,
    },
    {
        "id": 47,
        "product_id": 150,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Energizer Industrial AA 10-Pack",
        "sort_order": 0,
    },
    {
        "id": 48,
        "product_id": 151,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Energizer Everyday AA 4-Pack",
        "sort_order": 0,
    },
    # Products 160-174 - using existing images (cycling through available ones)
    {
        "id": 49,
        "product_id": 160,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Samsung Galaxy Buds Pro",
        "sort_order": 0,
    },
    {
        "id": 50,
        "product_id": 161,
        "image": "product-images/novita-intimate-wet-wipes-15pcs.jpg",
        "alt_text": "Vitamin C Serum 30ml",
        "sort_order": 0,
    },
    {
        "id": 51,
        "product_id": 162,
        "image": "product-images/california-scents-car-freshener-coronado-cherry-42.jpg",
        "alt_text": "Multi-Purpose Cleaner 750ml",
        "sort_order": 0,
    },
    {
        "id": 52,
        "product_id": 163,
        "image": "product-images/smile-baby-wet-wipes-with-chamomile-60pcs.jpg",
        "alt_text": "Premium Dog Food 2kg",
        "sort_order": 0,
    },
    {
        "id": 53,
        "product_id": 164,
        "image": "product-images/energizer-led-r50-e14-62w-450-lumens.jpg",
        "alt_text": "A4 Copy Paper 500 Sheets",
        "sort_order": 0,
    },
    {
        "id": 54,
        "product_id": 165,
        "image": "product-images/smile-wet-wipes-cars-jackson-storm-15pcs.jpg",
        "alt_text": "LEGO City Police Station",
        "sort_order": 0,
    },
    {
        "id": 55,
        "product_id": 166,
        "image": "product-images/refresh-your-car-diffuser-new-carcool-breeze-7ml.jpg",
        "alt_text": "Yoga Mat Premium 6mm",
        "sort_order": 0,
    },
    {
        "id": 56,
        "product_id": 167,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Garden Hose 15m",
        "sort_order": 0,
    },
    {
        "id": 57,
        "product_id": 168,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Cordless Drill 18V",
        "sort_order": 0,
    },
    {
        "id": 58,
        "product_id": 169,
        "image": "product-images/california-scents-car-freshener-coronado-cherry-42.jpg",
        "alt_text": "Organic Extra Virgin Olive Oil 500ml",
        "sort_order": 0,
    },
    {
        "id": 59,
        "product_id": 170,
        "image": "product-images/smile-baby-wet-wipes-with-chamomile-60pcs.jpg",
        "alt_text": "Baby Bottle Set 3-Pack",
        "sort_order": 0,
    },
    {
        "id": 60,
        "product_id": 171,
        "image": "product-images/energizer-silver-watch-battery-155v.jpg",
        "alt_text": "Car Floor Mats Set",
        "sort_order": 0,
    },
    {
        "id": 61,
        "product_id": 172,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Industrial Work Gloves",
        "sort_order": 0,
    },
    {
        "id": 62,
        "product_id": 173,
        "image": "product-images/novita-intimate-wet-wipes-15pcs.jpg",
        "alt_text": "Acrylic Paint Set 24 Colors",
        "sort_order": 0,
    },
    {
        "id": 63,
        "product_id": 174,
        "image": "product-images/energizer-led-r50-e14-62w-450-lumens.jpg",
        "alt_text": "The Art of Programming",
        "sort_order": 0,
    },
    # === Alkaline Batteries Category Images (Products 200-380) ===
    # Cycling through existing battery images on S3
    {
        "id": 64,
        "product_id": 200,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Energizer MAX AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 65,
        "product_id": 201,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Energizer MAX AA 8-Pack",
        "sort_order": 0,
    },
    {
        "id": 66,
        "product_id": 202,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Energizer MAX AAA 8-Pack",
        "sort_order": 0,
    },
    {
        "id": 67,
        "product_id": 203,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Duracell Plus AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 68,
        "product_id": 204,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Duracell Plus AA 8-Pack",
        "sort_order": 0,
    },
    {
        "id": 69,
        "product_id": 205,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Duracell Plus AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 70,
        "product_id": 206,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Duracell Plus AAA 8-Pack",
        "sort_order": 0,
    },
    {
        "id": 71,
        "product_id": 207,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Duracell Ultra AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 72,
        "product_id": 208,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Duracell Ultra AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 73,
        "product_id": 209,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Panasonic Evolta AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 74,
        "product_id": 210,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Panasonic Evolta AA 8-Pack",
        "sort_order": 0,
    },
    {
        "id": 75,
        "product_id": 211,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Panasonic Evolta AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 76,
        "product_id": 212,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Panasonic Evolta AAA 8-Pack",
        "sort_order": 0,
    },
    {
        "id": 77,
        "product_id": 213,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Varta Longlife AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 78,
        "product_id": 214,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Varta Longlife AA 8-Pack",
        "sort_order": 0,
    },
    {
        "id": 79,
        "product_id": 215,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Varta Longlife AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 80,
        "product_id": 216,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Varta Longlife AAA 8-Pack",
        "sort_order": 0,
    },
    {
        "id": 81,
        "product_id": 217,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Varta High Energy AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 82,
        "product_id": 218,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Varta High Energy AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 83,
        "product_id": 219,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "GP Ultra Plus AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 84,
        "product_id": 220,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "GP Ultra Plus AA 8-Pack",
        "sort_order": 0,
    },
    {
        "id": 85,
        "product_id": 221,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "GP Ultra Plus AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 86,
        "product_id": 222,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "GP Ultra Plus AAA 8-Pack",
        "sort_order": 0,
    },
    {
        "id": 87,
        "product_id": 223,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "GP Super AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 88,
        "product_id": 224,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "GP Super AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 89,
        "product_id": 225,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Energizer Industrial AA 10-Pack",
        "sort_order": 0,
    },
    {
        "id": 90,
        "product_id": 226,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Energizer Industrial AAA 10-Pack",
        "sort_order": 0,
    },
    {
        "id": 91,
        "product_id": 227,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Duracell Industrial AA 10-Pack",
        "sort_order": 0,
    },
    {
        "id": 92,
        "product_id": 228,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Duracell Industrial AAA 10-Pack",
        "sort_order": 0,
    },
    {
        "id": 93,
        "product_id": 229,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Energizer MAX AA 12-Pack",
        "sort_order": 0,
    },
    {
        "id": 94,
        "product_id": 230,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Energizer MAX AAA 12-Pack",
        "sort_order": 0,
    },
    {
        "id": 95,
        "product_id": 231,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Duracell Plus AA 12-Pack",
        "sort_order": 0,
    },
    {
        "id": 96,
        "product_id": 232,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Duracell Plus AAA 12-Pack",
        "sort_order": 0,
    },
    {
        "id": 97,
        "product_id": 233,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Energizer MAX C 2-Pack",
        "sort_order": 0,
    },
    {
        "id": 98,
        "product_id": 234,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Energizer MAX D 2-Pack",
        "sort_order": 0,
    },
    {
        "id": 99,
        "product_id": 235,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Duracell Plus C 2-Pack",
        "sort_order": 0,
    },
    {
        "id": 100,
        "product_id": 236,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Duracell Plus D 2-Pack",
        "sort_order": 0,
    },
    {
        "id": 101,
        "product_id": 237,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Varta Longlife C 2-Pack",
        "sort_order": 0,
    },
    {
        "id": 102,
        "product_id": 238,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Varta Longlife D 2-Pack",
        "sort_order": 0,
    },
    {
        "id": 103,
        "product_id": 239,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Panasonic Evolta C 2-Pack",
        "sort_order": 0,
    },
    {
        "id": 104,
        "product_id": 240,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Panasonic Evolta D 2-Pack",
        "sort_order": 0,
    },
    {
        "id": 105,
        "product_id": 241,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Energizer MAX AA 24-Pack",
        "sort_order": 0,
    },
    {
        "id": 106,
        "product_id": 242,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Energizer MAX AAA 24-Pack",
        "sort_order": 0,
    },
    {
        "id": 107,
        "product_id": 243,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Duracell Plus AA 24-Pack",
        "sort_order": 0,
    },
    {
        "id": 108,
        "product_id": 244,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Duracell Plus AAA 24-Pack",
        "sort_order": 0,
    },
    {
        "id": 109,
        "product_id": 245,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "GP Ultra AA 16-Pack",
        "sort_order": 0,
    },
    {
        "id": 110,
        "product_id": 246,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "GP Ultra AAA 16-Pack",
        "sort_order": 0,
    },
    {
        "id": 111,
        "product_id": 247,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Energizer Eco Advanced AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 112,
        "product_id": 248,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Energizer Eco Advanced AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 113,
        "product_id": 249,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Varta Industrial AA 10-Pack",
        "sort_order": 0,
    },
    {
        "id": 114,
        "product_id": 250,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Varta Industrial AAA 10-Pack",
        "sort_order": 0,
    },
    {
        "id": 115,
        "product_id": 251,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Philips Power Life AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 116,
        "product_id": 252,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Philips Power Life AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 117,
        "product_id": 253,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Philips Ultra Alkaline AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 118,
        "product_id": 254,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Philips Ultra Alkaline AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 119,
        "product_id": 255,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Sony Stamina Plus AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 120,
        "product_id": 256,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Sony Stamina Plus AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 121,
        "product_id": 257,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Rayovac High Energy AA 8-Pack",
        "sort_order": 0,
    },
    {
        "id": 122,
        "product_id": 258,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Rayovac High Energy AAA 8-Pack",
        "sort_order": 0,
    },
    {
        "id": 123,
        "product_id": 259,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Maxell Alkaline AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 124,
        "product_id": 260,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Maxell Alkaline AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 125,
        "product_id": 261,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Kodak Xtralife AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 126,
        "product_id": 262,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Kodak Xtralife AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 127,
        "product_id": 263,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Kodak Max AA 8-Pack",
        "sort_order": 0,
    },
    {
        "id": 128,
        "product_id": 264,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Kodak Max AAA 8-Pack",
        "sort_order": 0,
    },
    {
        "id": 129,
        "product_id": 265,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Energizer Ultimate Lithium AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 130,
        "product_id": 266,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Energizer Ultimate Lithium AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 131,
        "product_id": 267,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Duracell Optimum AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 132,
        "product_id": 268,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Duracell Optimum AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 133,
        "product_id": 269,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Energizer MAX Plus AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 134,
        "product_id": 270,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Energizer MAX Plus AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 135,
        "product_id": 271,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "GP ReCyko AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 136,
        "product_id": 272,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "GP ReCyko AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 137,
        "product_id": 273,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Panasonic Eneloop AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 138,
        "product_id": 274,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Panasonic Eneloop AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 139,
        "product_id": 275,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Amazon Basics AA 20-Pack",
        "sort_order": 0,
    },
    {
        "id": 140,
        "product_id": 276,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Amazon Basics AAA 20-Pack",
        "sort_order": 0,
    },
    {
        "id": 141,
        "product_id": 277,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Amazon Basics AA 48-Pack",
        "sort_order": 0,
    },
    {
        "id": 142,
        "product_id": 278,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Amazon Basics AAA 48-Pack",
        "sort_order": 0,
    },
    {
        "id": 143,
        "product_id": 279,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Ikea LADDA AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 144,
        "product_id": 280,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Ikea LADDA AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 145,
        "product_id": 281,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Energizer Power Seal AA 6-Pack",
        "sort_order": 0,
    },
    {
        "id": 146,
        "product_id": 282,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Energizer Power Seal AAA 6-Pack",
        "sort_order": 0,
    },
    {
        "id": 147,
        "product_id": 283,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Toshiba High Power AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 148,
        "product_id": 284,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Toshiba High Power AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 149,
        "product_id": 285,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Sanyo Eneloop Pro AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 150,
        "product_id": 286,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Sanyo Eneloop Pro AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 151,
        "product_id": 287,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Varta Recharge Accu Power AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 152,
        "product_id": 288,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Varta Recharge Accu Power AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 153,
        "product_id": 289,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Duracell Recharge Ultra AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 154,
        "product_id": 290,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Duracell Recharge Ultra AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 155,
        "product_id": 291,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Energizer Recharge Universal AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 156,
        "product_id": 292,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Energizer Recharge Universal AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 157,
        "product_id": 293,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "GP Super Alkaline C 2-Pack",
        "sort_order": 0,
    },
    {
        "id": 158,
        "product_id": 294,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "GP Super Alkaline D 2-Pack",
        "sort_order": 0,
    },
    {
        "id": 159,
        "product_id": 295,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Energizer AA 36-Pack Value Box",
        "sort_order": 0,
    },
    {
        "id": 160,
        "product_id": 296,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Energizer AAA 36-Pack Value Box",
        "sort_order": 0,
    },
    {
        "id": 161,
        "product_id": 297,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Duracell AA 36-Pack Value Box",
        "sort_order": 0,
    },
    {
        "id": 162,
        "product_id": 298,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Duracell AAA 36-Pack Value Box",
        "sort_order": 0,
    },
    {
        "id": 163,
        "product_id": 299,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Varta AA 40-Pack Megabox",
        "sort_order": 0,
    },
    {
        "id": 164,
        "product_id": 300,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Varta AAA 40-Pack Megabox",
        "sort_order": 0,
    },
    {
        "id": 165,
        "product_id": 301,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Energizer AA & AAA Combo 24-Pack",
        "sort_order": 0,
    },
    {
        "id": 166,
        "product_id": 302,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Duracell AA & AAA Combo 24-Pack",
        "sort_order": 0,
    },
    {
        "id": 167,
        "product_id": 303,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "GP Premium AA 10-Pack",
        "sort_order": 0,
    },
    {
        "id": 168,
        "product_id": 304,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "GP Premium AAA 10-Pack",
        "sort_order": 0,
    },
    # Products 340-380
    {
        "id": 169,
        "product_id": 340,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Philips Power AA 8-Pack",
        "sort_order": 0,
    },
    {
        "id": 170,
        "product_id": 341,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Philips Power AAA 8-Pack",
        "sort_order": 0,
    },
    {
        "id": 171,
        "product_id": 342,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Rayovac Fusion AA 8-Pack",
        "sort_order": 0,
    },
    {
        "id": 172,
        "product_id": 343,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Rayovac Fusion AAA 8-Pack",
        "sort_order": 0,
    },
    {
        "id": 173,
        "product_id": 344,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Maxell Gold AA 6-Pack",
        "sort_order": 0,
    },
    {
        "id": 174,
        "product_id": 345,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Maxell Gold AAA 6-Pack",
        "sort_order": 0,
    },
    {
        "id": 175,
        "product_id": 346,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Energizer Max AA 16-Pack",
        "sort_order": 0,
    },
    {
        "id": 176,
        "product_id": 347,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Energizer Max AAA 16-Pack",
        "sort_order": 0,
    },
    {
        "id": 177,
        "product_id": 348,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Panasonic Pro Power AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 178,
        "product_id": 349,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Panasonic Pro Power AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 179,
        "product_id": 350,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Panasonic Pro Power AA 8-Pack",
        "sort_order": 0,
    },
    {
        "id": 180,
        "product_id": 351,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Panasonic Pro Power AAA 8-Pack",
        "sort_order": 0,
    },
    {
        "id": 181,
        "product_id": 352,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Camelion Plus AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 182,
        "product_id": 353,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Camelion Plus AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 183,
        "product_id": 354,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Camelion Plus AA 8-Pack",
        "sort_order": 0,
    },
    {
        "id": 184,
        "product_id": 355,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Camelion Plus AAA 8-Pack",
        "sort_order": 0,
    },
    {
        "id": 185,
        "product_id": 356,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Fujitsu G Plus AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 186,
        "product_id": 357,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Fujitsu G Plus AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 187,
        "product_id": 358,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Eveready Gold AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 188,
        "product_id": 359,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Eveready Gold AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 189,
        "product_id": 360,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Eveready Super Heavy Duty AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 190,
        "product_id": 361,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Eveready Super Heavy Duty AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 191,
        "product_id": 362,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Energizer AA + Charger Kit",
        "sort_order": 0,
    },
    {
        "id": 192,
        "product_id": 363,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Energizer AAA + Charger Kit",
        "sort_order": 0,
    },
    {
        "id": 193,
        "product_id": 364,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Duracell AA + Charger Kit",
        "sort_order": 0,
    },
    {
        "id": 194,
        "product_id": 365,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Duracell AAA + Charger Kit",
        "sort_order": 0,
    },
    {
        "id": 195,
        "product_id": 366,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Ansmann Industrial AA 10-Pack",
        "sort_order": 0,
    },
    {
        "id": 196,
        "product_id": 367,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Ansmann Industrial AAA 10-Pack",
        "sort_order": 0,
    },
    {
        "id": 197,
        "product_id": 368,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Procell AA 10-Pack",
        "sort_order": 0,
    },
    {
        "id": 198,
        "product_id": 369,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Procell AAA 10-Pack",
        "sort_order": 0,
    },
    {
        "id": 199,
        "product_id": 370,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Energizer Industrial LR14 C 12-Pack",
        "sort_order": 0,
    },
    {
        "id": 200,
        "product_id": 371,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Energizer Industrial LR20 D 12-Pack",
        "sort_order": 0,
    },
    {
        "id": 201,
        "product_id": 372,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "GP Super Alkaline AA 12-Pack",
        "sort_order": 0,
    },
    {
        "id": 202,
        "product_id": 373,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "GP Super Alkaline AAA 12-Pack",
        "sort_order": 0,
    },
    {
        "id": 203,
        "product_id": 374,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Varta AA & AAA Combo 20-Pack",
        "sort_order": 0,
    },
    {
        "id": 204,
        "product_id": 375,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Energizer Max Power Seal AA 20-Pack",
        "sort_order": 0,
    },
    {
        "id": 205,
        "product_id": 376,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Energizer Max Power Seal AAA 20-Pack",
        "sort_order": 0,
    },
    {
        "id": 206,
        "product_id": 377,
        "image": "product-images/energizer-alkaline-power-aaa-12-pack-strip.jpg",
        "alt_text": "Duracell Coppertop AA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 207,
        "product_id": 378,
        "image": "product-images/energizer-alkaline-power-aaa-family-pack-24.jpg",
        "alt_text": "Duracell Coppertop AAA 4-Pack",
        "sort_order": 0,
    },
    {
        "id": 208,
        "product_id": 379,
        "image": "product-images/energizer-max-aaa-4-pack.jpg",
        "alt_text": "Duracell Coppertop AA 8-Pack",
        "sort_order": 0,
    },
    {
        "id": 209,
        "product_id": 380,
        "image": "product-images/energizer-max-plus-aa-31-pack.jpg",
        "alt_text": "Duracell Coppertop AAA 8-Pack",
        "sort_order": 0,
    },
]

PRODUCT_ATTRIBUTE_VALUES_DATA = [
    {"id": 101, "product_id": 50, "option_id": 82},
    {"id": 102, "product_id": 50, "option_id": 83},
    {"id": 103, "product_id": 50, "option_id": 84},
    {"id": 104, "product_id": 50, "option_id": 85},
    {"id": 105, "product_id": 51, "option_id": 82},
    {"id": 106, "product_id": 51, "option_id": 86},
    {"id": 107, "product_id": 51, "option_id": 87},
    {"id": 108, "product_id": 51, "option_id": 88},
    {"id": 109, "product_id": 52, "option_id": 89},
    {"id": 110, "product_id": 52, "option_id": 90},
    {"id": 111, "product_id": 52, "option_id": 91},
    {"id": 112, "product_id": 52, "option_id": 92},
    {"id": 113, "product_id": 53, "option_id": 93},
    {"id": 114, "product_id": 53, "option_id": 94},
    {"id": 115, "product_id": 53, "option_id": 95},
    {"id": 116, "product_id": 53, "option_id": 96},
    {"id": 117, "product_id": 54, "option_id": 82},
    {"id": 118, "product_id": 54, "option_id": 97},
    {"id": 119, "product_id": 54, "option_id": 98},
    {"id": 120, "product_id": 54, "option_id": 99},
    {"id": 121, "product_id": 55, "option_id": 100},
    {"id": 122, "product_id": 55, "option_id": 90},
    {"id": 123, "product_id": 55, "option_id": 101},
    {"id": 124, "product_id": 55, "option_id": 102},
    {"id": 125, "product_id": 56, "option_id": 100},
    {"id": 126, "product_id": 56, "option_id": 103},
    {"id": 127, "product_id": 56, "option_id": 104},
    {"id": 128, "product_id": 56, "option_id": 105},
    {"id": 129, "product_id": 57, "option_id": 106},
    {"id": 130, "product_id": 57, "option_id": 107},
    {"id": 131, "product_id": 57, "option_id": 108},
    {"id": 132, "product_id": 57, "option_id": 109},
    # Alkaline Batteries (category 41) - auto-generated below with 3-4 attributes each
]

_ALKALINE_BRAND_PATTERNS = [
    (re.compile(r"^amazon basics\b", re.IGNORECASE), 123),
    (re.compile(r"^energizer\b", re.IGNORECASE), 82),
    (re.compile(r"^duracell\b", re.IGNORECASE), 110),
    (re.compile(r"^panasonic\b", re.IGNORECASE), 111),
    (re.compile(r"^varta\b", re.IGNORECASE), 112),
    (re.compile(r"^gp\b", re.IGNORECASE), 113),
    (re.compile(r"^ikea\b", re.IGNORECASE), 124),
    (re.compile(r"^toshiba\b", re.IGNORECASE), 125),
    (re.compile(r"^sanyo\b", re.IGNORECASE), 126),
    (re.compile(r"^eveready\b", re.IGNORECASE), 127),
    (re.compile(r"^philips\b", re.IGNORECASE), 128),
    (re.compile(r"^rayovac\b", re.IGNORECASE), 129),
    (re.compile(r"^maxell\b", re.IGNORECASE), 130),
    (re.compile(r"^kodak\b", re.IGNORECASE), 131),
    (re.compile(r"^camelion\b", re.IGNORECASE), 132),
    (re.compile(r"^fujitsu\b", re.IGNORECASE), 133),
    (re.compile(r"^ansmann\b", re.IGNORECASE), 134),
    (re.compile(r"^procell\b", re.IGNORECASE), 135),
    (re.compile(r"^sony\b", re.IGNORECASE), 136),
]

_ALKALINE_PRODUCT_LINE_PATTERNS = [
    (re.compile(r"\bultra\s+plus\b", re.IGNORECASE), 121),
    (re.compile(r"\bpower\s+seal\b", re.IGNORECASE), 154),
    (re.compile(r"\beco\s+advanced\b", re.IGNORECASE), 156),
    (re.compile(r"\bstamina\s+plus\b", re.IGNORECASE), 160),
    (re.compile(r"\bultra\s+alkaline\b", re.IGNORECASE), 163),
    (re.compile(r"\bpower\s+life\b", re.IGNORECASE), 164),
    (re.compile(r"\bcoppertop\b", re.IGNORECASE), 152),
    (re.compile(r"\boptimum\b", re.IGNORECASE), 153),
    (re.compile(r"\bindustrial\b", re.IGNORECASE), 155),
    (re.compile(r"\bpro\s+power\b", re.IGNORECASE), 157),
    (re.compile(r"\bxtralife\b", re.IGNORECASE), 159),
    (re.compile(r"\bgold\b", re.IGNORECASE), 158),
    (re.compile(r"\bfusion\b", re.IGNORECASE), 161),
    (re.compile(r"\bpremium\b", re.IGNORECASE), 162),
    (re.compile(r"\bhigh\s+energy\b", re.IGNORECASE), 120),
    (re.compile(r"\blonglife\b", re.IGNORECASE), 119),
    (re.compile(r"\bevolta\b", re.IGNORECASE), 118),
    (re.compile(r"\bultra\b", re.IGNORECASE), 117),
    (re.compile(r"\bplus\b", re.IGNORECASE), 116),
    (re.compile(r"\bmax\b", re.IGNORECASE), 85),
]

_ALKALINE_BATTERY_TYPE_OPTION_IDS = {
    "AA": 114,
    "AAA": 83,
    "C": 137,
    "D": 138,
    "9V": 139,
    "AA/AAA": 140,
}

_ALKALINE_PACK_SIZE_OPTION_IDS = {
    "1": 151,
    "2": 141,
    "4": 84,
    "6": 142,
    "8": 115,
    "10": 143,
    "12": 144,
    "16": 145,
    "20": 146,
    "24": 147,
    "36": 148,
    "40": 149,
    "48": 150,
    "60": 103,
}

_ALKALINE_VOLTAGE_OPTION_ID = 122


def _extract_pack_size_option_id(name):
    match = re.search(r"(\d+)\s*-\s*Pack", name, re.IGNORECASE)
    if not match:
        match = re.search(r"(\d+)\s*Pack", name, re.IGNORECASE)
    if not match:
        return None
    size = match.group(1)
    return _ALKALINE_PACK_SIZE_OPTION_IDS.get(size)


def _extract_battery_type_option_id(name):
    if re.search(r"aa\s*(?:&|\+|/)\s*aaa", name, re.IGNORECASE):
        return _ALKALINE_BATTERY_TYPE_OPTION_IDS.get("AA/AAA")
    if re.search(r"\baaa\b", name, re.IGNORECASE):
        return _ALKALINE_BATTERY_TYPE_OPTION_IDS.get("AAA")
    if re.search(r"\baa\b", name, re.IGNORECASE):
        return _ALKALINE_BATTERY_TYPE_OPTION_IDS.get("AA")
    if re.search(r"\b9v\b", name, re.IGNORECASE):
        return _ALKALINE_BATTERY_TYPE_OPTION_IDS.get("9V")
    if re.search(r"\bc\b", name, re.IGNORECASE):
        return _ALKALINE_BATTERY_TYPE_OPTION_IDS.get("C")
    if re.search(r"\bd\b", name, re.IGNORECASE):
        return _ALKALINE_BATTERY_TYPE_OPTION_IDS.get("D")
    return None


def _extract_brand_option_id(name):
    for pattern, option_id in _ALKALINE_BRAND_PATTERNS:
        if pattern.search(name):
            return option_id
    return None


def _extract_product_line_option_id(name):
    for pattern, option_id in _ALKALINE_PRODUCT_LINE_PATTERNS:
        if pattern.search(name):
            return option_id
    return None


def _dedupe_option_ids(option_ids):
    seen = set()
    unique_ids = []
    for option_id in option_ids:
        if option_id and option_id not in seen:
            unique_ids.append(option_id)
            seen.add(option_id)
    return unique_ids


_existing_product_option_pairs = {(item["product_id"], item["option_id"]) for item in PRODUCT_ATTRIBUTE_VALUES_DATA}
_existing_product_option_map = {}
for item in PRODUCT_ATTRIBUTE_VALUES_DATA:
    _existing_product_option_map.setdefault(item["product_id"], []).append(item["option_id"])

_next_attribute_value_id = max(item["id"] for item in PRODUCT_ATTRIBUTE_VALUES_DATA) + 1

# Generate attributes for ALL Alkaline Batteries products (category 41)
# Each product gets 3 or 4 attributes (minimum 3, never less)
for product in PRODUCTS_DATA:
    if product["category_id"] != 41:
        continue
    product_id = product["id"]
    existing_option_ids = _existing_product_option_map.get(product_id, [])
    existing_count = len(existing_option_ids)
    # Alternate between 3 and 4 attributes, ensuring minimum 3
    target_count = 4 if product_id % 2 == 0 else 3
    if existing_count >= target_count:
        continue

    brand_option_id = _extract_brand_option_id(product["name"])
    battery_type_option_id = _extract_battery_type_option_id(product["name"])
    pack_size_option_id = _extract_pack_size_option_id(product["name"])
    product_line_option_id = _extract_product_line_option_id(product["name"])

    option_candidates = _dedupe_option_ids(
        [
            brand_option_id,
            battery_type_option_id,
            pack_size_option_id,
            product_line_option_id,
            _ALKALINE_VOLTAGE_OPTION_ID,
        ]
    )

    if pack_size_option_id is None:
        option_candidates.append(_ALKALINE_PACK_SIZE_OPTION_IDS.get("4"))
    if battery_type_option_id is None:
        option_candidates.append(_ALKALINE_BATTERY_TYPE_OPTION_IDS.get("AA"))
    option_candidates = _dedupe_option_ids(option_candidates)

    for option_id in option_candidates:
        if existing_count >= target_count:
            break
        if (product_id, option_id) in _existing_product_option_pairs:
            continue
        PRODUCT_ATTRIBUTE_VALUES_DATA.append(
            {"id": _next_attribute_value_id, "product_id": product_id, "option_id": option_id}
        )
        _existing_product_option_pairs.add((product_id, option_id))
        _existing_product_option_map.setdefault(product_id, []).append(option_id)
        _next_attribute_value_id += 1
        existing_count += 1

BANNER_SETTINGS_DATA = {
    "active_banner_type": "content",
    "available_from": None,
    "available_to": None,
}

BANNERS_DATA = [
    # Simple banners
    {
        "id": 12,
        "banner_type": "simple",
        "name": "Electronics & Gadgets",
        "image": "banners/hero-imac.jpg",
        "mobile_image": "",
        "url": "/products/electronics/",
        "is_active": True,
        "order": 0,
        "available_from": None,
        "available_to": None,
    },
    {
        "id": 13,
        "banner_type": "simple",
        "name": "Fashion Accessories",
        "image": "banners/hero-fashion.jpg",
        "mobile_image": "",
        "url": "/products/fashion/",
        "is_active": True,
        "order": 1,
        "available_from": None,
        "available_to": None,
    },
    # Content banners
    {
        "id": 14,
        "banner_type": "content",
        "name": "iMac Sale Banner",
        "image": "banners/content-imac.jpg",
        "mobile_image": "",
        "url": "",
        "is_active": True,
        "order": 0,
        "available_from": None,
        "available_to": None,
        "badge_label": "Sale",
        "badge_text": "Up to 30% OFF if you order today",
        "title": "Save today on your new iMac computer.",
        "subtitle": 'Reserve your new Apple iMac 27" today and enjoy exclusive savings. Pre-order now to secure your discount.',
        "text_alignment": "left",
        "overlay_opacity": 50,
        "primary_button_text": "Pre-order now",
        "primary_button_url": "#",
        "primary_button_open_in_new_tab": False,
        "primary_button_icon": "",
        "secondary_button_text": "",
        "secondary_button_url": "#",
        "secondary_button_open_in_new_tab": False,
        "secondary_button_icon": "",
    },
    {
        "id": 15,
        "banner_type": "content",
        "name": "Fashion New Arrivals",
        "image": "banners/content-fashion.jpg",
        "mobile_image": "",
        "url": "",
        "is_active": True,
        "order": 1,
        "available_from": None,
        "available_to": None,
        "badge_label": "New arrival",
        "badge_text": "",
        "title": "New arrivals picked just for you",
        "subtitle": "Less is more never out of date.",
        "text_alignment": "left",
        "overlay_opacity": 50,
        "primary_button_text": "Discover more",
        "primary_button_url": "#",
        "primary_button_open_in_new_tab": False,
        "primary_button_icon": "",
        "secondary_button_text": "View catalog",
        "secondary_button_url": "#",
        "secondary_button_open_in_new_tab": False,
        "secondary_button_icon": "play",
    },
    {
        "id": 16,
        "banner_type": "content",
        "name": "Gamers' Favorites",
        "image": "banners/content-gaming.jpg",
        "mobile_image": "",
        "url": "",
        "is_active": True,
        "order": 2,
        "available_from": None,
        "available_to": None,
        "badge_label": "Offer",
        "badge_text": "Save $25 when you spend $250 In-Store or Online",
        "title": "Gamers' Favorites. Best Sellers.",
        "subtitle": "The world's largest retail gaming and trade-in destination for Xbox, PlayStation, and Nintendo games, systems, consoles & accessories.",
        "text_alignment": "left",
        "overlay_opacity": 50,
        "primary_button_text": "Find a store",
        "primary_button_url": "#",
        "primary_button_open_in_new_tab": False,
        "primary_button_icon": "location",
        "secondary_button_text": "",
        "secondary_button_url": "#",
        "secondary_button_open_in_new_tab": False,
        "secondary_button_icon": "",
    },
]

HOMEPAGE_SECTIONS_DATA = [
    {
        "id": 1,
        "section_type": "storefront_hero",
        "name": "Storefront Hero",
        "title": "Don't miss out on exclusive deals.",
        "subtitle": "Unlock even more exclusive member deals when you become a Plus or Diamond member.",
        "primary_button_text": "Shop Now",
        "primary_button_url": "https://google.com?q=shop",
        "primary_button_open_in_new_tab": True,
        "secondary_button_text": "Learn more",
        "secondary_button_url": "https://google.com?q=learn+more",
        "secondary_button_open_in_new_tab": True,
        "custom_html": "",
        "custom_css": "",
        "custom_js": "",
        "is_enabled": True,
        "available_from": None,
        "available_to": None,
        "order": 0,
    },
    {
        "id": 18,
        "section_type": "product_list",
        "name": "Featured Products",
        "title": "",
        "custom_html": "",
        "custom_css": "",
        "custom_js": "",
        "is_enabled": False,
        "available_from": None,
        "available_to": None,
        "order": 1,
    },
    {
        "id": 20,
        "section_type": "product_slider",
        "name": "Product Slider",
        "title": "",
        "custom_html": "",
        "custom_css": "",
        "custom_js": "",
        "is_enabled": True,
        "available_from": None,
        "available_to": None,
        "order": 1,
    },
    {
        "id": 4,
        "section_type": "banner_section",
        "name": "",
        "title": "",
        "custom_html": "",
        "custom_css": "",
        "custom_js": "",
        "is_enabled": True,
        "available_from": None,
        "available_to": None,
        "order": 2,
    },
    {
        "id": 19,
        "section_type": "product_list",
        "name": "All Products",
        "title": "",
        "custom_html": "",
        "custom_css": "",
        "custom_js": "",
        "is_enabled": False,
        "available_from": None,
        "available_to": None,
        "order": 3,
    },
    {
        "id": 21,
        "section_type": "storefront_hero",
        "name": "Promotions Storefront Hero",
        "title": "Discover our best promotions.",
        "subtitle": "Save big with exclusive discounts and special offers available for a limited time.",
        "primary_button_text": "Show promotions",
        "primary_button_url": "/dynamic-page/promotions/2/",
        "primary_button_open_in_new_tab": False,
        "secondary_button_text": "Learn more",
        "secondary_button_url": "/about-promotions/",
        "secondary_button_open_in_new_tab": False,
        "custom_html": "",
        "custom_css": "",
        "custom_js": "",
        "is_enabled": True,
        "available_from": None,
        "available_to": None,
        "order": 4,
    },
]

HOMEPAGE_SECTION_CATEGORY_BOXES_DATA = [
    {
        "id": 1,
        "section_id": 1,
        "title": "Top categories",
        "shop_link_text": "Shop now",
        "shop_link_url": "/categories/",
        "order": 0,
    },
    {
        "id": 2,
        "section_id": 1,
        "title": "Shop consumer electronics",
        "shop_link_text": "Shop now",
        "shop_link_url": "/electronics/",
        "order": 1,
    },
    {
        "id": 3,
        "section_id": 21,
        "title": "Top promotions",
        "shop_link_text": "Show promotions",
        "shop_link_url": "/dynamic-page/promotions/2/",
        "order": 0,
    },
    {
        "id": 4,
        "section_id": 21,
        "title": "Shop promotional offers",
        "shop_link_text": "Show promotions",
        "shop_link_url": "/offers/",
        "order": 1,
    },
]

HOMEPAGE_SECTION_CATEGORY_ITEMS_DATA = [
    # Box 1: Top categories
    {
        "id": 1,
        "category_box_id": 1,
        "name": "Electronics",
        "image": "storefront/category_computers.svg",
        "url": "/products/electronics/",
        "order": 0,
    },
    {
        "id": 2,
        "category_box_id": 1,
        "name": "Batteries",
        "image": "storefront/category_gaming.svg",
        "url": "/products/batteries/",
        "order": 1,
    },
    {
        "id": 3,
        "category_box_id": 1,
        "name": "Car Accessories",
        "image": "storefront/category_tablets.svg",
        "url": "/products/car-accessories/",
        "order": 2,
    },
    {
        "id": 4,
        "category_box_id": 1,
        "name": "Lighting",
        "image": "storefront/category_watches.svg",
        "url": "/products/lighting/",
        "order": 3,
    },
    # Box 2: Consumer electronics
    {
        "id": 5,
        "category_box_id": 2,
        "name": "Beauty & Health",
        "image": "storefront/category_laptops.svg",
        "url": "/products/beauty-health/",
        "order": 0,
    },
    {
        "id": 6,
        "category_box_id": 2,
        "name": "Household",
        "image": "storefront/category_watches.svg",
        "url": "/products/household/",
        "order": 1,
    },
    {
        "id": 7,
        "category_box_id": 2,
        "name": "Pet Supplies",
        "image": "storefront/category_ipad.svg",
        "url": "/products/pet-supplies/",
        "order": 2,
    },
    {
        "id": 8,
        "category_box_id": 2,
        "name": "Wet Wipes",
        "image": "storefront/category_accessories.svg",
        "url": "/products/wet-wipes/",
        "order": 3,
    },
    # Box 3: Top promotions (section 21)
    {
        "id": 9,
        "category_box_id": 3,
        "name": "Electronics",
        "image": "storefront/category_computers.svg",
        "url": "/products/electronics/",
        "order": 0,
    },
    {
        "id": 10,
        "category_box_id": 3,
        "name": "Batteries",
        "image": "storefront/category_gaming.svg",
        "url": "/products/batteries/",
        "order": 1,
    },
    {
        "id": 11,
        "category_box_id": 3,
        "name": "Car Accessories",
        "image": "storefront/category_tablets.svg",
        "url": "/products/car-accessories/",
        "order": 2,
    },
    {
        "id": 12,
        "category_box_id": 3,
        "name": "Lighting",
        "image": "storefront/category_watches.svg",
        "url": "/products/lighting/",
        "order": 3,
    },
    # Box 4: Promotional offers (section 21)
    {
        "id": 13,
        "category_box_id": 4,
        "name": "Beauty & Health",
        "image": "storefront/category_laptops.svg",
        "url": "/products/beauty-health/",
        "order": 0,
    },
    {
        "id": 14,
        "category_box_id": 4,
        "name": "Household",
        "image": "storefront/category_watches.svg",
        "url": "/products/household/",
        "order": 1,
    },
    {
        "id": 15,
        "category_box_id": 4,
        "name": "Pet Supplies",
        "image": "storefront/category_ipad.svg",
        "url": "/products/pet-supplies/",
        "order": 2,
    },
    {
        "id": 16,
        "category_box_id": 4,
        "name": "Wet Wipes",
        "image": "storefront/category_accessories.svg",
        "url": "/products/wet-wipes/",
        "order": 3,
    },
]

HOMEPAGE_SECTION_PRODUCTS_DATA = [
    {"id": 31, "section_id": 18, "product_id": 50, "order": 0},
    {"id": 32, "section_id": 18, "product_id": 51, "order": 1},
    {"id": 33, "section_id": 18, "product_id": 52, "order": 2},
    {"id": 34, "section_id": 18, "product_id": 53, "order": 3},
    {"id": 35, "section_id": 19, "product_id": 50, "order": 0},
    {"id": 36, "section_id": 19, "product_id": 51, "order": 1},
    {"id": 37, "section_id": 19, "product_id": 52, "order": 2},
    {"id": 38, "section_id": 19, "product_id": 53, "order": 3},
    {"id": 39, "section_id": 19, "product_id": 54, "order": 4},
    {"id": 40, "section_id": 19, "product_id": 55, "order": 5},
    {"id": 41, "section_id": 19, "product_id": 56, "order": 6},
    {"id": 42, "section_id": 19, "product_id": 57, "order": 7},
    # Product Slider section (id=20)
    {"id": 43, "section_id": 20, "product_id": 50, "order": 0},
    {"id": 44, "section_id": 20, "product_id": 51, "order": 1},
    {"id": 45, "section_id": 20, "product_id": 52, "order": 2},
    {"id": 46, "section_id": 20, "product_id": 53, "order": 3},
    {"id": 47, "section_id": 20, "product_id": 54, "order": 4},
    {"id": 48, "section_id": 20, "product_id": 55, "order": 5},
]

HOMEPAGE_SECTION_BANNERS_DATA = [
    {
        "id": 11,
        "section_id": 4,
        "name": "Seasonal Sale",
        "image": "section_banners/seeds/promo_sale.jpg",
        "url": "",
        "order": 1,
    },
    {
        "id": 12,
        "section_id": 4,
        "name": "New Arrivals",
        "image": "section_banners/seeds/promo_arrivals.jpg",
        "url": "",
        "order": 2,
    },
    {
        "id": 10,
        "section_id": 4,
        "name": "Smart Home Essentials",
        "image": "section_banners/seeds/promo_smarthome.jpg",
        "url": "https://www.google.pl",
        "order": 0,
    },
]

# =============================================================================
# Category Banners & Recommended Products
# =============================================================================

CATEGORY_BANNERS_DATA = [
    # Alkaline Batteries category (id: 41) banners
    {
        "id": 1,
        "category_id": 41,
        "name": "Duracell Power",
        "image": "section_banners/seeds/promo_sale.jpg",
        "url": "/category/41/alkaline-batteries/",
        "is_active": True,
        "order": 1,
    },
    {
        "id": 2,
        "category_id": 41,
        "name": "Energizer Max",
        "image": "section_banners/seeds/promo_arrivals.jpg",
        "url": "/category/41/alkaline-batteries/",
        "is_active": True,
        "order": 2,
    },
    {
        "id": 3,
        "category_id": 41,
        "name": "Varta Longlife",
        "image": "section_banners/seeds/promo_smarthome.jpg",
        "url": "/category/41/alkaline-batteries/",
        "is_active": True,
        "order": 3,
    },
]

CATEGORY_RECOMMENDED_PRODUCTS_DATA = [
    # Alkaline Batteries category (id: 41) recommended products
    {"id": 1, "category_id": 41, "product_id": 380, "order": 1},  # Duracell Coppertop AAA 8-Pack
    {"id": 2, "category_id": 41, "product_id": 379, "order": 2},  # Duracell Coppertop AA 8-Pack
    {"id": 3, "category_id": 41, "product_id": 378, "order": 3},  # Duracell Coppertop AAA 4-Pack
    {"id": 4, "category_id": 41, "product_id": 377, "order": 4},  # Duracell Coppertop AA 4-Pack
    {"id": 5, "category_id": 41, "product_id": 376, "order": 5},  # Energizer Max Power Seal AAA 20-Pack
    {"id": 6, "category_id": 41, "product_id": 375, "order": 6},  # Energizer Max Power Seal AA 20-Pack
]

MEDIA_STORAGE_SETTINGS_DATA = {
    "provider_type": "s3",
    "aws_bucket_name": "amper-b2c-demo",
    "aws_region": "eu-central-1",
    "aws_location": "media",
    "cdn_enabled": False,
    "cdn_domain": "dm2jdqmtgmvma.cloudfront.net",
}


# =============================================================================
# COMMAND
# =============================================================================


@contextmanager
def _disable_simple_history():
    previous = getattr(settings, "SIMPLE_HISTORY_ENABLED", True)
    settings.SIMPLE_HISTORY_ENABLED = False
    try:
        yield
    finally:
        settings.SIMPLE_HISTORY_ENABLED = previous


class Command(BaseCommand):
    help = "Seed database with predefined data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-users",
            action="store_true",
            help="Skip creating the default superuser",
        )

    def handle(self, *args, **options):
        skip_users = options["skip_users"]

        self.stdout.write(self.style.NOTICE("Seeding database with predefined data..."))

        with transaction.atomic():
            with _disable_simple_history():
                self._seed_sites()
                self._seed_topbar()
                self._seed_custom_css()
                self._seed_site_settings()
                self._seed_system_settings()
                self._seed_dynamic_pages()
                self._seed_media_storage_settings()
                self._seed_footer()
                self._seed_bottombar()
                self._seed_categories()
                self._seed_category_banners()
                self._seed_category_recommended_products()
                self._seed_navbar()
                self._seed_attributes()
                self._seed_products()
                self._seed_banners()
                self._seed_homepage_sections()
                self._seed_storefront_hero_section()
                # MediaFile entries are auto-created by signals when Banner, ProductImage etc. are saved
                self._seed_social_apps()

                if not skip_users:
                    self._create_superuser()

                # Fix PostgreSQL sequences after inserting with explicit IDs
                self._fix_sequences()

            # Populate history for seeded data
            self._populate_history()

        self.stdout.write(self.style.SUCCESS("Database seeded successfully!"))

    def _upload_if_missing(self, instance, field_name, relative_path):
        """Upload seed file to storage if it doesn't exist.

        Uses storage.save() directly to preserve the exact path from seed data,
        instead of using the field's upload_to which generates UUID filenames.
        """
        if not relative_path:
            return

        image_field = getattr(instance, field_name)
        storage = image_field.storage

        def ensure_public_acl():
            try:
                from apps.media.models import MediaStorageSettings
                from apps.media.storage import _build_s3_key

                if hasattr(storage, "bucket"):
                    settings = MediaStorageSettings.get_settings()
                    key = _build_s3_key(relative_path, settings)
                    storage.bucket.Object(key).Acl().put(ACL="public-read")
            except Exception:
                pass

        # Check if file exists on storage
        try:
            if storage.exists(relative_path):
                ensure_public_acl()
                return
        except Exception:
            pass

        # Search for file in seed directories
        seed_dirs = [
            Path(settings.BASE_DIR) / "assets" / "seeds",
            Path(settings.BASE_DIR) / "media",
        ]

        for seed_dir in seed_dirs:
            full_path = seed_dir / relative_path
            if full_path.exists():
                self.stdout.write(f"    Uploading {relative_path} to storage...")
                with open(full_path, "rb") as f:
                    # Save directly to storage with the exact path, bypassing upload_to
                    storage.save(relative_path, ContentFile(f.read()))
                ensure_public_acl()
                return

        self.stdout.write(self.style.WARNING(f"    Warning: Seed file not found: {relative_path}"))

    def _parse_datetime(self, dt_str):
        """Parse datetime string."""
        if not dt_str:
            return None
        return parse_datetime(dt_str)

    def _seed_sites(self):
        """Seed Site model."""
        for item in SITES_DATA:
            Site.objects.update_or_create(id=item["id"], defaults={"domain": item["domain"], "name": item["name"]})
        self.stdout.write(f"  Site: {len(SITES_DATA)} records")

    def _seed_topbar(self):
        """Seed TopBar model."""
        for item in TOPBAR_DATA:
            TopBar.objects.update_or_create(
                id=item["id"],
                defaults={
                    "name": item["name"],
                    "singleton_key": item["singleton_key"],
                    "content_type": item["content_type"],
                    "background_color": item["background_color"],
                    "text": item["text"],
                    "link_label": item["link_label"],
                    "link_url": item["link_url"],
                    "custom_html": item["custom_html"],
                    "custom_css": item["custom_css"],
                    "custom_js": item["custom_js"],
                    "is_active": item["is_active"],
                    "available_from": self._parse_datetime(item["available_from"]),
                    "available_to": self._parse_datetime(item["available_to"]),
                    "order": item["order"],
                },
            )
        self.stdout.write(f"  TopBar: {len(TOPBAR_DATA)} records")

    def _seed_custom_css(self):
        """Seed CustomCSS model."""
        for item in CUSTOM_CSS_DATA:
            CustomCSS.objects.update_or_create(
                id=item["id"],
                defaults={
                    "custom_css": item["custom_css"],
                    "custom_css_active": item["custom_css_active"],
                },
            )
        self.stdout.write(f"  CustomCSS: {len(CUSTOM_CSS_DATA)} records")

    def _seed_site_settings(self):
        """Seed SiteSettings model."""
        for item in SITE_SETTINGS_DATA:
            obj, _ = SiteSettings.objects.update_or_create(
                id=item["id"],
                defaults={
                    "store_name": item["store_name"],
                    "site_url": item["site_url"],
                    "description": item["description"],
                    "keywords": item["keywords"],
                    "default_image": item["default_image"],
                    "currency": item["currency"],
                    "logo": item.get("logo", ""),
                },
            )
            if item.get("logo"):
                self._upload_if_missing(obj, "logo", item["logo"])
        self.stdout.write(f"  SiteSettings: {len(SITE_SETTINGS_DATA)} records")

    def _seed_system_settings(self):
        """Seed SystemSettings model (SMTP, Turnstile config)."""
        from apps.utils.encryption import encrypt_value

        smtp_password = os.environ.get("SMTP_PASSWORD", "")

        for item in SYSTEM_SETTINGS_DATA:
            defaults = {
                "smtp_host": item["smtp_host"],
                "smtp_port": item["smtp_port"],
                "smtp_username": item["smtp_username"],
                "smtp_use_tls": item["smtp_use_tls"],
                "smtp_use_ssl": item["smtp_use_ssl"],
                "smtp_default_from_email": item["smtp_default_from_email"],
                "smtp_timeout": item["smtp_timeout"],
                "smtp_enabled": item["smtp_enabled"],
                "turnstile_enabled": item["turnstile_enabled"],
            }
            if smtp_password:
                defaults["smtp_password_encrypted"] = encrypt_value(smtp_password)

            SystemSettings.objects.update_or_create(
                id=item["id"],
                defaults=defaults,
            )
        self.stdout.write(f"  SystemSettings: {len(SYSTEM_SETTINGS_DATA)} records")

    def _seed_dynamic_pages(self):
        """Seed DynamicPage model."""
        for item in DYNAMIC_PAGES_DATA:
            DynamicPage.objects.update_or_create(
                id=item["id"],
                defaults={
                    "name": item["name"],
                    "slug": item["slug"],
                    "meta_title": item.get("meta_title", ""),
                    "meta_description": item.get("meta_description", ""),
                    "is_active": item.get("is_active", True),
                    "exclude_from_sitemap": item.get("exclude_from_sitemap", False),
                    "seo_noindex": item.get("seo_noindex", False),
                    "content": item.get("content", ""),
                },
            )
        self.stdout.write(f"  DynamicPage: {len(DYNAMIC_PAGES_DATA)} records")

    def _seed_footer(self):
        """Seed Footer and related models."""
        for item in FOOTER_DATA:
            Footer.objects.update_or_create(
                id=item["id"],
                defaults={
                    "singleton_key": item["singleton_key"],
                    "content_type": item["content_type"],
                    "custom_html": item["custom_html"],
                    "custom_css": item["custom_css"],
                    "custom_js": item["custom_js"],
                    "is_active": item["is_active"],
                },
            )
        self.stdout.write(f"  Footer: {len(FOOTER_DATA)} records")

        for item in FOOTER_SECTIONS_DATA:
            FooterSection.objects.update_or_create(
                id=item["id"],
                defaults={
                    "footer_id": item["footer_id"],
                    "name": item["name"],
                    "order": item["order"],
                },
            )
        self.stdout.write(f"  FooterSection: {len(FOOTER_SECTIONS_DATA)} records")

        for item in FOOTER_SECTION_LINKS_DATA:
            FooterSectionLink.objects.update_or_create(
                id=item["id"],
                defaults={
                    "section_id": item["section_id"],
                    "label": item.get("label", ""),
                    "url": item.get("url", ""),
                    "link_type": item.get("link_type", "custom_url"),
                    "dynamic_page_id": item.get("dynamic_page_id"),
                    "order": item["order"],
                },
            )
        self.stdout.write(f"  FooterSectionLink: {len(FOOTER_SECTION_LINKS_DATA)} records")

        for item in FOOTER_SOCIAL_MEDIA_DATA:
            FooterSocialMedia.objects.update_or_create(
                id=item["id"],
                defaults={
                    "footer_id": item["footer_id"],
                    "platform": item["platform"],
                    "label": item["label"],
                    "url": item["url"],
                    "is_active": item["is_active"],
                    "order": item["order"],
                },
            )
        self.stdout.write(f"  FooterSocialMedia: {len(FOOTER_SOCIAL_MEDIA_DATA)} records")

    def _seed_bottombar(self):
        """Seed BottomBar and related models."""
        for item in BOTTOMBAR_DATA:
            BottomBar.objects.update_or_create(
                id=item["id"],
                defaults={
                    "singleton_key": item["singleton_key"],
                    "is_active": item["is_active"],
                },
            )
        self.stdout.write(f"  BottomBar: {len(BOTTOMBAR_DATA)} records")

        for item in BOTTOMBAR_LINKS_DATA:
            BottomBarLink.objects.update_or_create(
                id=item["id"],
                defaults={
                    "bottom_bar_id": item["bottom_bar_id"],
                    "label": item["label"],
                    "url": item["url"],
                    "order": item["order"],
                },
            )
        self.stdout.write(f"  BottomBarLink: {len(BOTTOMBAR_LINKS_DATA)} records")

    def _seed_navbar(self):
        """Seed Navbar and default custom navigation items mirroring standard categories."""
        for item in NAVBAR_DATA:
            Navbar.objects.update_or_create(
                id=item["id"],
                defaults={
                    "singleton_key": item["singleton_key"],
                    "mode": item["mode"],
                },
            )
        self.stdout.write(f"  Navbar: {len(NAVBAR_DATA)} records")

        navbar = Navbar.get_settings()

        # Create custom navbar items matching standard (alphabetical root categories)
        # Seed first 8 categories as custom items example
        root_categories = list(Category.objects.filter(parent__isnull=True).order_by("name")[:8])

        # Clear existing items for a clean mirror
        NavbarItem.objects.filter(navbar=navbar).delete()

        navbar_items = []
        for index, category in enumerate(root_categories, start=1):
            navbar_items.append(
                NavbarItem(
                    navbar=navbar,
                    item_type=NavbarItem.ItemType.CATEGORY,
                    category=category,
                    label="",
                    url="",
                    open_in_new_tab=False,
                    label_color="",
                    icon="",
                    order=index,
                    is_active=True,
                )
            )

        # Add separator at position 9
        navbar_items.append(
            NavbarItem(
                navbar=navbar,
                item_type=NavbarItem.ItemType.SEPARATOR,
                category=None,
                label="",
                url="",
                open_in_new_tab=False,
                label_color="",
                icon="",
                order=9,
                is_active=True,
            )
        )

        # Add "Promotions" custom link at position 10 with red color
        navbar_items.append(
            NavbarItem(
                navbar=navbar,
                item_type=NavbarItem.ItemType.CUSTOM_LINK,
                category=None,
                label="Promotions",
                url="/dynamic-page/promotions/2/",
                open_in_new_tab=False,
                label_color="#dc2626",
                icon="",
                order=10,
                is_active=True,
            )
        )

        dynamic_page = DynamicPage.objects.filter(slug="privacy-policy").first()
        if dynamic_page:
            navbar_items.append(
                NavbarItem(
                    navbar=navbar,
                    item_type=NavbarItem.ItemType.CUSTOM_LINK,
                    dynamic_page=None,
                    category=None,
                    label=dynamic_page.name,
                    url=dynamic_page.get_absolute_url(),
                    open_in_new_tab=False,
                    label_color="",
                    icon="",
                    order=11,
                    is_active=True,
                )
            )

        if navbar_items:
            NavbarItem.objects.bulk_create(navbar_items)
        self.stdout.write(f"  NavbarItem: {len(navbar_items)} records")

    def _seed_categories(self):
        """Seed Category model."""
        # First pass: create categories without parent_id
        for item in CATEGORIES_DATA:
            Category.objects.update_or_create(
                id=item["id"],
                defaults={
                    "name": item["name"],
                    "slug": item["slug"],
                    "parent_id": None,
                    "image": item["image"],
                    "icon": item.get("icon", "circle"),
                },
            )
        # Second pass: set parent_id
        for item in CATEGORIES_DATA:
            if item["parent_id"]:
                Category.objects.filter(id=item["id"]).update(parent_id=item["parent_id"])
        self.stdout.write(f"  Category: {len(CATEGORIES_DATA)} records")

    def _seed_category_banners(self):
        """Seed CategoryBanner models."""
        for item in CATEGORY_BANNERS_DATA:
            obj, created = CategoryBanner.objects.update_or_create(
                id=item["id"],
                defaults={
                    "category_id": item["category_id"],
                    "name": item["name"],
                    "image": item["image"],
                    "url": item.get("url", ""),
                    "is_active": item.get("is_active", True),
                    "order": item.get("order", 0),
                },
            )
            self._upload_if_missing(obj, "image", item["image"])
        self.stdout.write(f"  CategoryBanner: {len(CATEGORY_BANNERS_DATA)} records")

    def _seed_category_recommended_products(self):
        """Seed CategoryRecommendedProduct models."""
        for item in CATEGORY_RECOMMENDED_PRODUCTS_DATA:
            CategoryRecommendedProduct.objects.update_or_create(
                id=item["id"],
                defaults={
                    "category_id": item["category_id"],
                    "product_id": item["product_id"],
                    "order": item.get("order", 0),
                },
            )
        self.stdout.write(f"  CategoryRecommendedProduct: {len(CATEGORY_RECOMMENDED_PRODUCTS_DATA)} records")

    def _seed_attributes(self):
        """Seed AttributeDefinition and AttributeOption models."""
        for item in ATTRIBUTE_DEFINITIONS_DATA:
            AttributeDefinition.objects.update_or_create(
                id=item["id"],
                defaults={
                    "name": item["name"],
                    "show_on_tile": item.get("show_on_tile", True),
                    "tile_display_order": item.get("tile_display_order", 0),
                },
            )
        self.stdout.write(f"  AttributeDefinition: {len(ATTRIBUTE_DEFINITIONS_DATA)} records")

        for item in ATTRIBUTE_OPTIONS_DATA:
            AttributeOption.objects.update_or_create(
                id=item["id"],
                defaults={
                    "attribute_id": item["attribute_id"],
                    "value": item["value"],
                },
            )
        self.stdout.write(f"  AttributeOption: {len(ATTRIBUTE_OPTIONS_DATA)} records")

    def _seed_products(self):
        """Seed Product and related models."""
        for item in PRODUCTS_DATA:
            Product.objects.update_or_create(
                id=item["id"],
                defaults={
                    "name": item["name"],
                    "slug": item["slug"],
                    "category_id": item["category_id"],
                    "status": item["status"],
                    "price": Decimal(item["price"]),
                    "stock": item["stock"],
                    "sales_total": Decimal(item["sales_total"]),
                    "revenue_total": Decimal(item["revenue_total"]),
                    "sales_per_day": Decimal(item["sales_per_day"]),
                    "sales_per_month": Decimal(item["sales_per_month"]),
                    "description": item["description"],
                },
            )
        self.stdout.write(f"  Product: {len(PRODUCTS_DATA)} records")

        for item in PRODUCT_IMAGES_DATA:
            obj, created = ProductImage.objects.update_or_create(
                id=item["id"],
                defaults={
                    "product_id": item["product_id"],
                    "image": item["image"],
                    "alt_text": item["alt_text"],
                    "sort_order": item["sort_order"],
                },
            )
            self._upload_if_missing(obj, "image", item["image"])
        self.stdout.write(f"  ProductImage: {len(PRODUCT_IMAGES_DATA)} records")

        for item in PRODUCT_ATTRIBUTE_VALUES_DATA:
            ProductAttributeValue.objects.update_or_create(
                product_id=item["product_id"],
                option_id=item["option_id"],
                defaults={},
            )
        self.stdout.write(f"  ProductAttributeValue: {len(PRODUCT_ATTRIBUTE_VALUES_DATA)} records")

    def _seed_banners(self):
        """Seed BannerGroup, BannerSettings and Banner models."""
        # First, ensure BannerGroup instances exist for each type
        content_group, _ = BannerGroup.objects.update_or_create(
            banner_type=BannerType.CONTENT,
            defaults={
                "is_active": BANNER_SETTINGS_DATA["active_banner_type"] == "content",
                "available_from": self._parse_datetime(BANNER_SETTINGS_DATA["available_from"]),
                "available_to": self._parse_datetime(BANNER_SETTINGS_DATA["available_to"]),
            },
        )
        simple_group, _ = BannerGroup.objects.update_or_create(
            banner_type=BannerType.SIMPLE,
            defaults={
                "is_active": BANNER_SETTINGS_DATA["active_banner_type"] == "simple",
                "available_from": self._parse_datetime(BANNER_SETTINGS_DATA["available_from"]),
                "available_to": self._parse_datetime(BANNER_SETTINGS_DATA["available_to"]),
            },
        )
        self.stdout.write("  BannerGroup: 2 records")

        # Seed the legacy settings singleton for backwards compatibility
        settings_obj = BannerSettings.get_settings()
        settings_obj.active_banner_type = BANNER_SETTINGS_DATA["active_banner_type"]
        settings_obj.available_from = self._parse_datetime(BANNER_SETTINGS_DATA["available_from"])
        settings_obj.available_to = self._parse_datetime(BANNER_SETTINGS_DATA["available_to"])
        settings_obj.save()
        self.stdout.write("  BannerSettings: configured")

        # Map banner types to groups
        group_map = {
            "content": content_group,
            "simple": simple_group,
        }

        # Then seed the banners
        for item in BANNERS_DATA:
            defaults = {
                "group": group_map.get(item["banner_type"]),
                "banner_type": item["banner_type"],
                "name": item["name"],
                "image": item["image"],
                "mobile_image": item["mobile_image"],
                "url": item.get("url", ""),
                "is_active": item["is_active"],
                "order": item["order"],
                "available_from": self._parse_datetime(item.get("available_from")),
                "available_to": self._parse_datetime(item.get("available_to")),
            }
            # Add content banner fields if present
            if "badge_label" in item:
                defaults.update(
                    {
                        "badge_label": item.get("badge_label", ""),
                        "badge_text": item.get("badge_text", ""),
                        "title": item.get("title", ""),
                        "subtitle": item.get("subtitle", ""),
                        "text_alignment": item.get("text_alignment", "left"),
                        "overlay_opacity": item.get("overlay_opacity", 50),
                        "primary_button_text": item.get("primary_button_text", ""),
                        "primary_button_url": item.get("primary_button_url", "#"),
                        "primary_button_open_in_new_tab": item.get("primary_button_open_in_new_tab", False),
                        "primary_button_icon": item.get("primary_button_icon", ""),
                        "secondary_button_text": item.get("secondary_button_text", ""),
                        "secondary_button_url": item.get("secondary_button_url", "#"),
                        "secondary_button_open_in_new_tab": item.get("secondary_button_open_in_new_tab", False),
                        "secondary_button_icon": item.get("secondary_button_icon", ""),
                    }
                )
            obj, created = Banner.objects.update_or_create(
                id=item["id"],
                defaults=defaults,
            )
            # Ensure images are uploaded to storage
            self._upload_if_missing(obj, "image", item["image"])
            if item.get("mobile_image"):
                self._upload_if_missing(obj, "mobile_image", item["mobile_image"])
        self.stdout.write(f"  Banner: {len(BANNERS_DATA)} records")

    def _seed_homepage_sections(self):
        """Seed HomepageSection and related models."""
        for item in HOMEPAGE_SECTIONS_DATA:
            defaults = {
                "section_type": item["section_type"],
                "name": item["name"],
                "title": item["title"],
                "custom_html": item["custom_html"],
                "custom_css": item["custom_css"],
                "custom_js": item["custom_js"],
                "is_enabled": item["is_enabled"],
                "available_from": self._parse_datetime(item["available_from"]),
                "available_to": self._parse_datetime(item["available_to"]),
                "order": item["order"],
            }
            # Add storefront hero fields if present
            if item["section_type"] == "storefront_hero":
                defaults.update(
                    {
                        "subtitle": item.get("subtitle", ""),
                        "primary_button_text": item.get("primary_button_text", ""),
                        "primary_button_url": item.get("primary_button_url", ""),
                        "primary_button_open_in_new_tab": item.get("primary_button_open_in_new_tab", False),
                        "secondary_button_text": item.get("secondary_button_text", ""),
                        "secondary_button_url": item.get("secondary_button_url", ""),
                        "secondary_button_open_in_new_tab": item.get("secondary_button_open_in_new_tab", False),
                    }
                )
            HomepageSection.objects.update_or_create(
                id=item["id"],
                defaults=defaults,
            )
        self.stdout.write(f"  HomepageSection: {len(HOMEPAGE_SECTIONS_DATA)} records")

        for item in HOMEPAGE_SECTION_PRODUCTS_DATA:
            HomepageSectionProduct.objects.update_or_create(
                id=item["id"],
                defaults={
                    "section_id": item["section_id"],
                    "product_id": item["product_id"],
                    "order": item["order"],
                },
            )
        self.stdout.write(f"  HomepageSectionProduct: {len(HOMEPAGE_SECTION_PRODUCTS_DATA)} records")

        for item in HOMEPAGE_SECTION_BANNERS_DATA:
            obj, created = HomepageSectionBanner.objects.update_or_create(
                id=item["id"],
                defaults={
                    "section_id": item["section_id"],
                    "name": item["name"],
                    "image": item["image"],
                    "url": item["url"],
                    "order": item["order"],
                },
            )
            self._upload_if_missing(obj, "image", item["image"])
        self.stdout.write(f"  HomepageSectionBanner: {len(HOMEPAGE_SECTION_BANNERS_DATA)} records")

        # Seed category boxes for storefront hero sections
        for item in HOMEPAGE_SECTION_CATEGORY_BOXES_DATA:
            HomepageSectionCategoryBox.objects.update_or_create(
                id=item["id"],
                defaults={
                    "section_id": item["section_id"],
                    "title": item["title"],
                    "shop_link_text": item["shop_link_text"],
                    "shop_link_url": item["shop_link_url"],
                    "order": item["order"],
                },
            )
        self.stdout.write(f"  HomepageSectionCategoryBox: {len(HOMEPAGE_SECTION_CATEGORY_BOXES_DATA)} records")

        for item in HOMEPAGE_SECTION_CATEGORY_ITEMS_DATA:
            obj, created = HomepageSectionCategoryItem.objects.update_or_create(
                id=item["id"],
                defaults={
                    "category_box_id": item["category_box_id"],
                    "name": item["name"],
                    "image": item["image"],
                    "url": item["url"],
                    "order": item["order"],
                },
            )
            self._upload_if_missing(obj, "image", item["image"])
        self.stdout.write(f"  HomepageSectionCategoryItem: {len(HOMEPAGE_SECTION_CATEGORY_ITEMS_DATA)} records")

    def _seed_storefront_hero_section(self):
        """Legacy storefront hero section - now handled via HomepageSection with type storefront_hero."""
        # Category boxes and items are now seeded in _seed_homepage_sections
        self.stdout.write("  StorefrontHeroSection: skipped (using section type instead)")

    def _seed_media_storage_settings(self):
        """Seed MediaStorageSettings with AWS keys from environment variables."""
        if MEDIA_STORAGE_SETTINGS_DATA:
            settings_obj = MediaStorageSettings.get_settings()
            settings_obj.provider_type = MEDIA_STORAGE_SETTINGS_DATA["provider_type"]
            settings_obj.aws_bucket_name = MEDIA_STORAGE_SETTINGS_DATA["aws_bucket_name"]
            settings_obj.aws_region = MEDIA_STORAGE_SETTINGS_DATA["aws_region"]
            settings_obj.aws_location = MEDIA_STORAGE_SETTINGS_DATA["aws_location"]
            settings_obj.cdn_enabled = MEDIA_STORAGE_SETTINGS_DATA["cdn_enabled"]
            settings_obj.cdn_domain = MEDIA_STORAGE_SETTINGS_DATA["cdn_domain"]
            # Read AWS keys from environment variables
            aws_access_key = os.environ.get("AWS_ACCESS_KEY_ID", "")
            aws_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
            settings_obj.aws_access_key_id = aws_access_key
            settings_obj.aws_secret_access_key = aws_secret_key
            settings_obj.save()
            if aws_access_key and aws_secret_key:
                self.stdout.write("  MediaStorageSettings: configured with AWS keys from env")
            else:
                self.stdout.write(self.style.WARNING("  MediaStorageSettings: configured (AWS keys not found in env)"))

    def _seed_social_apps(self):
        """Seed SocialApp for Google OAuth with credentials from environment variables."""
        from django.contrib.sites.models import Site

        google_client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
        google_secret_id = os.environ.get("GOOGLE_SECRET_ID", "")

        if google_client_id and google_secret_id:
            site = Site.objects.get(pk=1)
            social_app, created = SocialApp.objects.update_or_create(
                provider="google",
                defaults={
                    "name": "Google",
                    "client_id": google_client_id,
                    "secret": google_secret_id,
                },
            )
            # Ensure the app is linked to the site
            if site not in social_app.sites.all():
                social_app.sites.add(site)
            # Ensure SocialAppSettings exists and is active
            SocialAppSettings.objects.get_or_create(social_app=social_app, defaults={"is_active": True})
            action = "created" if created else "updated"
            self.stdout.write(f"  SocialApp (Google): {action} with credentials from env")
        else:
            self.stdout.write(self.style.WARNING("  SocialApp (Google): skipped (credentials not found in env)"))

    def _create_superuser(self):
        """Create the default superuser."""
        email = "admin@example.com"
        password = "admin"

        user, created = CustomUser.objects.get_or_create(
            email=email,
            defaults={
                "username": email,
                "first_name": "Admin",
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )

        if created:
            user.set_password(password)
            user.save()
            EmailAddress.objects.get_or_create(user=user, email=email, defaults={"verified": True, "primary": True})
            self.stdout.write(self.style.SUCCESS(f"  Superuser created: {email} / {password}"))
        else:
            user.first_name = "Admin"
            user.is_staff = True
            user.is_superuser = True
            user.set_password(password)
            user.save()
            self.stdout.write(f"  Superuser updated: {email}")

    def _fix_sequences(self):
        """
        Fix PostgreSQL sequences after inserting records with explicit IDs.

        When using update_or_create with explicit IDs, PostgreSQL sequences
        don't get updated, causing IntegrityError on subsequent inserts.
        This resets each sequence to the max ID in its table.
        """
        from django.db import connection

        # Tables that were seeded with explicit IDs
        tables = [
            "web_footersection",
            "web_footersectionlink",
            "web_footersocialmedia",
            "web_bottombarlink",
            "web_navbar",
            "web_navbaritem",
            "web_topbar",
            "web_footer",
            "web_bottombar",
            "web_customcss",
            "web_sitesettings",
            "web_dynamicpage",
            "catalog_category",
            "catalog_categorybanner",
            "catalog_categoryrecommendedproduct",
            "catalog_product",
            "catalog_productimage",
            "catalog_attributedefinition",
            "catalog_attributeoption",
            "catalog_productattributevalue",
            "homepage_banner",
            "homepage_bannergroup",
            "homepage_bannersettings",
            "homepage_homepagesection",
            "homepage_homepagesectionproduct",
            "homepage_homepagesectionbanner",
            "homepage_homepagesectioncategorybox",
            "homepage_homepagesectioncategoryitem",
            "homepage_storefrontherosection",
            "homepage_storefrontcategorybox",
            "homepage_storefrontcategoryitem",
        ]

        fixed_count = 0
        with connection.cursor() as cursor:
            for table in tables:
                try:
                    # Get max ID from table
                    cursor.execute(f"SELECT MAX(id) FROM {table}")
                    max_id = cursor.fetchone()[0]
                    if max_id is None:
                        continue

                    # Reset sequence to max_id
                    seq_name = f"{table}_id_seq"
                    cursor.execute(f"SELECT setval('{seq_name}', %s)", [max_id])
                    fixed_count += 1
                except Exception:
                    # Table might not exist or have a different sequence name
                    pass

        self.stdout.write(f"  Sequences fixed: {fixed_count} tables")

    def _populate_history(self):
        """Populate historical records for seeded data."""
        try:
            call_command("populate_history", auto=True, stdout=self.stdout, stderr=self.stderr)
            self.stdout.write("  History: initial records created")
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"  History: skipped ({exc})"))
