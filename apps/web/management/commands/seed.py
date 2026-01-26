"""
Seed command for populating the database with predefined data.

It populates the current database with site settings, categories, products, etc.

EXCLUDED (you must configure manually in CMS):
- AWS credentials (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
- Google credentials (GOOGLE_CLIENT_ID, GOOGLE_SECRET_ID)

Default superuser:
- Email: admin@example.com
- Password: admin

Usage:
    uv run manage.py seed
    uv run manage.py seed --skip-users  # Skip superuser creation
"""

from decimal import Decimal

from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.dateparse import parse_datetime

from allauth.account.models import EmailAddress

from apps.users.models import CustomUser
from apps.web.models import (
    TopBar,
    CustomCSS,
    SiteSettings,
    Footer,
    FooterSection,
    FooterSectionLink,
    FooterSocialMedia,
    BottomBar,
    BottomBarLink,
)
from apps.catalog.models import (
    Category,
    Product,
    ProductImage,
    AttributeDefinition,
    AttributeOption,
    ProductAttributeValue,
)
from apps.homepage.models import (
    Banner,
    HomepageSection,
    HomepageSectionProduct,
    HomepageSectionBanner,
)
from apps.media.models import MediaStorageSettings


SITES_DATA = [
    {"id": 1, "domain": "localhost:8000", "name": "AMPLFIER sp. z o.o."}
]

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
        "store_name": "",
        "site_url": "",
        "description": "",
        "keywords": "",
        "default_image": "",
        "currency": "PLN",
    }
]

FOOTER_DATA = [
    {
        "id": 1,
        "singleton_key": 1,
        "content_type": "custom",
        "custom_html": '''<div class="footer-sections"><div class="footer-section"><h6 class="footer-section-title">Test Section2</h6><ul class="footer-section-links"><li><a class="footer-link" href="/about/">About Us</a></li><li><a class="footer-link" href="/contact/">Contact</a></li></ul></div><div class="footer-section"><h6 class="footer-section-title">Shop</h6><ul class="footer-section-links"><li><a class="footer-link" href="/">Catalog</a></li><li><a class="footer-link" href="/">New Arrivals</a></li><li><a class="footer-link" href="/">Best Sellers</a></li><li><a class="footer-link" href="/">Deals</a></li></ul></div><div class="footer-section"><h6 class="footer-section-title">Support</h6><ul class="footer-section-links"><li><a class="footer-link" href="/">Help Center</a></li><li><a class="footer-link" href="/">Contact Us</a></li><li><a class="footer-link" href="/">Shipping</a></li><li><a class="footer-link" href="/">Returns</a></li></ul></div><div class="footer-section"><h6 class="footer-section-title">Company</h6><ul class="footer-section-links"><li><a class="footer-link" href="/">About Us</a></li><li><a class="footer-link" href="/">Careers</a></li><li><a class="footer-link" href="/">Press</a></li><li><a class="footer-link" href="/">Blog</a></li></ul></div><div class="footer-section"><h6 class="footer-section-title">Legal</h6><ul class="footer-section-links"><li><a class="footer-link" href="/">Privacy Policy</a></li><li><a class="footer-link" href="/">Terms of Service</a></li><li><a class="footer-link" href="/">Cookie Policy</a></li><li><a class="footer-link" href="/">Sitemap</a></li></ul></div><div class="footer-section"><h6 class="footer-section-title">Resources</h6><ul class="footer-section-links"><li><a class="footer-link" href="/">Documentation</a></li><li><a class="footer-link" href="/">API Reference</a></li><li><a class="footer-link" href="/">Community</a></li><li><a class="footer-link" href="/">Partners</a></li></ul></div><div class="footer-section"><h6 class="footer-section-title">Account</h6><ul class="footer-section-links"><li><a class="footer-link" href="/users/profile/">My Profile</a></li><li><a class="footer-link" href="/">My Orders</a></li><li><a class="footer-link" href="/">Wishlist</a></li><li><a class="footer-link" href="/">Settings</a></li></ul></div><div class="footer-section"><h6 class="footer-section-title">Social Media</h6><ul class="footer-section-links"><li><a class="footer-social-link" target="_blank" rel="noopener noreferrer" href="https://facebook.com"><svg class="footer-social-icon" fill="currentColor" viewbox="0 0 24 24" aria-hidden="true"><path fill-rule="evenodd" d="M22 12c0-5.523-4.477-10-10-10S2 6.477 2 12c0 4.991 3.657 9.128 8.438 9.878v-6.987h-2.54V12h2.54V9.797c0-2.506 1.492-3.89 3.777-3.89 1.094 0 2.238.195 2.238.195v2.46h-1.26c-1.243 0-1.63.771-1.63 1.562V12h2.773l-.443 2.89h-2.33v6.988C18.343 21.128 22 16.991 22 12z" clip-rule="evenodd"></path></svg>Facebook</a></li><li><a class="footer-social-link" target="_blank" rel="noopener noreferrer" href="https://youtube.com"><svg class="footer-social-icon" fill="currentColor" viewbox="0 0 24 24" aria-hidden="true"><path fill-rule="evenodd" d="M19.812 5.418c.861.23 1.538.907 1.768 1.768C21.998 8.746 22 12 22 12s0 3.255-.418 4.814a2.504 2.504 0 0 1-1.768 1.768c-1.56.419-7.814.419-7.814.419s-6.255 0-7.814-.419a2.505 2.505 0 0 1-1.768-1.768C2 15.255 2 12 2 12s0-3.255.418-4.814a2.507 2.507 0 0 1 1.768-1.768C5.746 5 12 5 12 5s6.255 0 7.814.418zM15.194 12 10 15V9l5.194 3z" clip-rule="evenodd"></path></svg>YouTube</a></li><li><a class="footer-social-link" target="_blank" rel="noopener noreferrer" href="https://instagram.com"><svg class="footer-social-icon" fill="currentColor" viewbox="0 0 24 24" aria-hidden="true"><path fill-rule="evenodd" d="M12.315 2c2.43 0 2.784.013 3.808.06 1.064.049 1.791.218 2.427.465a4.902 4.902 0 011.772 1.153 4.902 4.902 0 011.153 1.772c.247.636.416 1.363.465 2.427.048 1.067.06 1.407.06 4.123v.08c0 2.643-.012 2.987-.06 4.043-.049 1.064-.218 1.791-.465 2.427a4.902 4.902 0 01-1.153 1.772 4.902 4.902 0 01-1.772 1.153c-.636.247-1.363.416-2.427.465-1.067.048-1.407.06-4.123.06h-.08c-2.643 0-2.987-.012-4.043-.06-1.064-.049-1.791-.218-2.427-.465a4.902 4.902 0 01-1.772-1.153 4.902 4.902 0 01-1.153-1.772c-.247-.636-.416-1.363-.465-2.427-.047-1.024-.06-1.379-.06-3.808v-.63c0-2.43.013-2.784.06-3.808.049-1.064.218-1.791.465-2.427a4.902 4.902 0 011.153-1.772A4.902 4.902 0 015.45 2.525c.636-.247 1.363-.416 2.427-.465C8.901 2.013 9.256 2 11.685 2h.63zm-.081 1.802h-.468c-2.456 0-2.784.011-3.807.058-.975.045-1.504.207-1.857.344-.467.182-.8.398-1.15.748-.35.35-.566.683-.748 1.15-.137.353-.3.882-.344 1.857-.047 1.023-.058 1.351-.058 3.807v.468c0 2.456.011 2.784.058 3.807.045.975.207 1.504.344 1.857.182.466.399.8.748 1.15.35.35.683.566 1.15.748.353.137.882.3 1.857.344 1.054.048 1.37.058 4.041.058h.08c2.597 0 2.917-.01 3.96-.058.976-.045 1.505-.207 1.858-.344.466-.182.8-.398 1.15-.748.35-.35.566-.683.748-1.15.137-.353.3-.882.344-1.857.048-1.055.058-1.37.058-4.041v-.08c0-2.597-.01-2.917-.058-3.96-.045-.976-.207-1.505-.344-1.858a3.097 3.097 0 00-.748-1.15 3.098 3.098 0 00-1.15-.748c-.353-.137-.882-.3-1.857-.344-1.023-.047-1.351-.058-3.807-.058zM12 6.865a5.135 5.135 0 110 10.27 5.135 5.135 0 010-10.27zm0 1.802a3.333 3.333 0 100 6.666 3.333 3.333 0 000-6.666zm5.338-3.205a1.2 1.2 0 110 2.4 1.2 1.2 0 010-2.4z" clip-rule="evenodd"></path></svg>Instagram</a></li><li><a class="footer-social-link" target="_blank" rel="noopener noreferrer" href="https://twitter.com"><svg class="footer-social-icon" fill="currentColor" viewbox="0 0 24 24" aria-hidden="true"><path d="M8.29 20.251c7.547 0 11.675-6.253 11.675-11.675 0-.178 0-.355-.012-.53A8.348 8.348 0 0022 5.92a8.19 8.19 0 01-2.357.646 4.118 4.118 0 001.804-2.27 8.224 8.224 0 01-2.605.996 4.107 4.107 0 00-6.993 3.743 11.65 11.65 0 01-8.457-4.287 4.106 4.106 0 001.27 5.477A4.072 4.072 0 012.8 9.713v.052a4.105 4.105 0 003.292 4.022 4.095 4.095 0 01-1.853.07 4.108 4.108 0 003.834 2.85A8.233 8.233 0 012 18.407a11.616 11.616 0 006.29 1.84"></path></svg>Twitter</a></li><li><a class="footer-social-link" target="_blank" rel="noopener noreferrer" href="https://tiktok.com"><svg class="footer-social-icon" fill="currentColor" viewbox="0 0 24 24" aria-hidden="true"><path d="M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z"></path></svg>TikTok&nbsp;</a></li></ul></div></div>''',
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
    {"id": 7, "section_id": 3, "label": "Help Center", "url": "/", "order": 0},
    {"id": 8, "section_id": 3, "label": "Contact Us", "url": "/", "order": 1},
    {"id": 9, "section_id": 3, "label": "Shipping", "url": "/", "order": 2},
    {"id": 10, "section_id": 3, "label": "Returns", "url": "/", "order": 3},
    {"id": 11, "section_id": 4, "label": "About Us", "url": "/", "order": 0},
    {"id": 12, "section_id": 4, "label": "Careers", "url": "/", "order": 1},
    {"id": 13, "section_id": 4, "label": "Press", "url": "/", "order": 2},
    {"id": 14, "section_id": 4, "label": "Blog", "url": "/", "order": 3},
    {"id": 15, "section_id": 5, "label": "Privacy Policy", "url": "/", "order": 0},
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
    {"id": 1, "footer_id": 1, "platform": "facebook", "label": "Facebook", "url": "https://facebook.com", "is_active": True, "order": 0},
    {"id": 2, "footer_id": 1, "platform": "youtube", "label": "YouTube", "url": "https://youtube.com", "is_active": True, "order": 1},
    {"id": 3, "footer_id": 1, "platform": "instagram", "label": "Instagram", "url": "https://instagram.com", "is_active": True, "order": 2},
    {"id": 4, "footer_id": 1, "platform": "twitter", "label": "Twitter", "url": "https://twitter.com", "is_active": True, "order": 3},
    {"id": 5, "footer_id": 1, "platform": "tiktok", "label": "TikTok", "url": "https://tiktok.com", "is_active": True, "order": 4},
]

BOTTOMBAR_DATA = [
    {"id": 1, "singleton_key": 1, "is_active": True}
]

BOTTOMBAR_LINKS_DATA = [
    {"id": 1, "bottom_bar_id": 1, "label": "Legal Notice", "url": "/legal/", "order": 0},
    {"id": 2, "bottom_bar_id": 1, "label": "Privacy Policy", "url": "/terms/", "order": 1},
    {"id": 3, "bottom_bar_id": 1, "label": "Terms of Use", "url": "/terms/", "order": 2},
    {"id": 4, "bottom_bar_id": 1, "label": "Cookie Settings", "url": "#", "order": 3},
    {"id": 5, "bottom_bar_id": 1, "label": "Accessibility", "url": "#", "order": 4},
]

CATEGORIES_DATA = [
    {"id": 47, "name": "Car Accessories", "slug": "car-accessories", "parent_id": None, "image": ""},
    {"id": 49, "name": "Lighting", "slug": "lighting", "parent_id": None, "image": ""},
    {"id": 43, "name": "Wet Wipes", "slug": "wet-wipes", "parent_id": None, "image": ""},
    {"id": 40, "name": "Batteries", "slug": "batteries", "parent_id": None, "image": ""},
    {"id": 42, "name": "Watch Batteries", "slug": "watch-batteries", "parent_id": 40, "image": ""},
    {"id": 41, "name": "Alkaline Batteries", "slug": "alkaline-batteries", "parent_id": 40, "image": ""},
    {"id": 45, "name": "Kids Wipes", "slug": "kids-wipes", "parent_id": 43, "image": ""},
    {"id": 44, "name": "Baby Wipes", "slug": "baby-wipes", "parent_id": 43, "image": ""},
    {"id": 46, "name": "Intimate Care", "slug": "intimate-care", "parent_id": 43, "image": ""},
    {"id": 48, "name": "Air Fresheners", "slug": "air-fresheners", "parent_id": 47, "image": ""},
    {"id": 50, "name": "LED Bulbs", "slug": "led-bulbs", "parent_id": 49, "image": ""},
]

ATTRIBUTE_DEFINITIONS_DATA = [
    {"id": 44, "name": "brand", "display_name": "Brand"},
    {"id": 45, "name": "battery_type", "display_name": "Battery Type"},
    {"id": 46, "name": "pack_size", "display_name": "Pack Size"},
    {"id": 47, "name": "product_line", "display_name": "Product Line"},
    {"id": 48, "name": "voltage", "display_name": "Voltage"},
    {"id": 49, "name": "wipe_type", "display_name": "Wipe Type"},
    {"id": 50, "name": "scent", "display_name": "Scent"},
    {"id": 51, "name": "weight", "display_name": "Weight"},
    {"id": 52, "name": "product_type", "display_name": "Product Type"},
    {"id": 53, "name": "wattage", "display_name": "Wattage"},
    {"id": 54, "name": "lumens", "display_name": "Lumens"},
    {"id": 55, "name": "socket_type", "display_name": "Socket Type"},
    {"id": 56, "name": "character", "display_name": "Character"},
    {"id": 57, "name": "age_range", "display_name": "Age Range"},
    {"id": 58, "name": "volume", "display_name": "Volume"},
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
]

PRODUCT_IMAGES_DATA = [
    {"id": 37, "product_id": 50, "image": "product-images/energizer-max-aaa-4-pack_5CvQIwn.webp", "alt_text": "Energizer MAX AAA 4-Pack", "sort_order": 0},
    {"id": 38, "product_id": 51, "image": "product-images/energizer-silver-watch-battery-155v_BEyoBmV.webp", "alt_text": "Energizer Silver Watch Battery 1.55V", "sort_order": 0},
    {"id": 39, "product_id": 52, "image": "product-images/novita-intimate-wet-wipes-15pcs_lAReI41.webp", "alt_text": "Novita Intimate Wet Wipes 15pcs", "sort_order": 0},
    {"id": 40, "product_id": 53, "image": "product-images/california-scents-car-freshener-coronado-cherry-42.webp", "alt_text": "California Scents Car Freshener Coronado Cherry 42g", "sort_order": 0},
    {"id": 41, "product_id": 54, "image": "product-images/energizer-led-r50-e14-62w-450-lumens_EV1fmMH.webp", "alt_text": "Energizer LED R50 E14 6.2W 450 Lumens", "sort_order": 0},
    {"id": 42, "product_id": 55, "image": "product-images/smile-wet-wipes-cars-jackson-storm-15pcs_41Rbmtx.webp", "alt_text": "Smile Wet Wipes Cars Jackson Storm 15pcs", "sort_order": 0},
    {"id": 43, "product_id": 56, "image": "product-images/smile-baby-wet-wipes-with-chamomile-60pcs_g5Z4usZ.webp", "alt_text": "Smile Baby Wet Wipes with Chamomile 60pcs", "sort_order": 0},
    {"id": 44, "product_id": 57, "image": "product-images/5050028253013.webp", "alt_text": "Refresh Your Car Diffuser New Car/Cool Breeze 7ml", "sort_order": 0},
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
]

BANNERS_DATA = [
    {"id": 12, "name": "Electronics & Gadgets", "image": "banners/5e5b77c5-7a86-42a7-a8f8-6ecee165a5b1.png", "mobile_image": "banners/mobile_ab1de3ca-6957-4529-a629-06cc8e6e612d.png", "url": "", "is_active": True, "available_from": None, "available_to": None, "order": 0},
    {"id": 13, "name": "Fashion Accessories", "image": "banners/9bf2da5c-3839-42fd-955e-a8f7e8be6181.png", "mobile_image": "banners/mobile_6be17e66-09e2-4c09-ab86-6dc009322ca2.png", "url": "", "is_active": True, "available_from": None, "available_to": None, "order": 1},

]

HOMEPAGE_SECTIONS_DATA = [
    {"id": 12, "section_type": "custom_section", "name": "", "title": "", "custom_html": '<div style="background-color:#ffffff;border-radius:24px;box-shadow:0 10px 25px rgba(0,0,0,0.08);margin:40px auto;max-width:800px;padding:48px 32px;text-align:center;transition:transform 0.3s, box-shadow 0.3s;"><h1 style="font-size:40px;line-height:1.2;margin-bottom:16px;"><strong>Nowa kolekcja</strong></h1><p style="color:#555555;font-size:20px;margin-bottom:24px;">Sprawdź nasze bestsellery</p><p><a style="background-color:#000000;border-radius:16px;color:#ffffff;display:inline-block;font-size:16px;padding:16px 40px;text-decoration:none;transition:background-color 0.3s, transform 0.3s;" href="#">Zobacz produkty</a></p></div>', "custom_css": "", "custom_js": "", "is_enabled": True, "available_from": None, "available_to": None, "order": 0},
    {"id": 18, "section_type": "product_list", "name": "Featured Products", "title": "Featured Products", "custom_html": "", "custom_css": "", "custom_js": "", "is_enabled": True, "available_from": None, "available_to": None, "order": 1},
    {"id": 4, "section_type": "banner_section", "name": "", "title": "Promotions", "custom_html": "", "custom_css": "", "custom_js": "", "is_enabled": True, "available_from": None, "available_to": None, "order": 2},
    {"id": 19, "section_type": "product_list", "name": "All Products", "title": "All Products", "custom_html": "", "custom_css": "", "custom_js": "", "is_enabled": True, "available_from": None, "available_to": None, "order": 3},
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
]

HOMEPAGE_SECTION_BANNERS_DATA = [
    {"id": 11, "section_id": 4, "name": "Seasonal Sale", "image": "section_banners/8b7c118b-1172-4b92-ac03-8d5580a307ed.png", "url": "", "order": 1},
    {"id": 12, "section_id": 4, "name": "New Arrivals", "image": "section_banners/95e2bbd6-e24b-4225-864c-ba70cdf47aa5.jpg", "url": "", "order": 2},
    {"id": 10, "section_id": 4, "name": "Smart Home Essentials", "image": "section_banners/8a5e7f6e-0d13-495a-8156-b785606cc9c0.png", "url": "https://www.google.pl", "order": 0},
]

MEDIA_STORAGE_SETTINGS_DATA = {
    "provider_type": "s3",
    "aws_bucket_name": "amper-b2c-qa-eu",
    "aws_region": "eu-central-1",
    "aws_location": "media",
    "cdn_enabled": False,
    "cdn_domain": "dm2jdqmtgmvma.cloudfront.net",
}


# =============================================================================
# COMMAND
# =============================================================================

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
            self._seed_sites()
            self._seed_topbar()
            self._seed_custom_css()
            self._seed_site_settings()
            self._seed_footer()
            self._seed_bottombar()
            self._seed_categories()
            self._seed_attributes()
            self._seed_products()
            self._seed_banners()
            self._seed_homepage_sections()
            # MediaFile entries are auto-created by signals when Banner, ProductImage etc. are saved
            self._seed_media_storage_settings()

            if not skip_users:
                self._create_superuser()

            # Fix PostgreSQL sequences after inserting with explicit IDs
            self._fix_sequences()

        self.stdout.write(self.style.SUCCESS("Database seeded successfully!"))

    def _parse_datetime(self, dt_str):
        """Parse datetime string."""
        if not dt_str:
            return None
        return parse_datetime(dt_str)

    def _seed_sites(self):
        """Seed Site model."""
        for item in SITES_DATA:
            Site.objects.update_or_create(
                id=item["id"],
                defaults={"domain": item["domain"], "name": item["name"]}
            )
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
                }
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
                }
            )
        self.stdout.write(f"  CustomCSS: {len(CUSTOM_CSS_DATA)} records")

    def _seed_site_settings(self):
        """Seed SiteSettings model."""
        for item in SITE_SETTINGS_DATA:
            SiteSettings.objects.update_or_create(
                id=item["id"],
                defaults={
                    "store_name": item["store_name"],
                    "site_url": item["site_url"],
                    "description": item["description"],
                    "keywords": item["keywords"],
                    "default_image": item["default_image"],
                    "currency": item["currency"],
                }
            )
        self.stdout.write(f"  SiteSettings: {len(SITE_SETTINGS_DATA)} records")

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
                }
            )
        self.stdout.write(f"  Footer: {len(FOOTER_DATA)} records")

        for item in FOOTER_SECTIONS_DATA:
            FooterSection.objects.update_or_create(
                id=item["id"],
                defaults={
                    "footer_id": item["footer_id"],
                    "name": item["name"],
                    "order": item["order"],
                }
            )
        self.stdout.write(f"  FooterSection: {len(FOOTER_SECTIONS_DATA)} records")

        for item in FOOTER_SECTION_LINKS_DATA:
            FooterSectionLink.objects.update_or_create(
                id=item["id"],
                defaults={
                    "section_id": item["section_id"],
                    "label": item["label"],
                    "url": item["url"],
                    "order": item["order"],
                }
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
                }
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
                }
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
                }
            )
        self.stdout.write(f"  BottomBarLink: {len(BOTTOMBAR_LINKS_DATA)} records")

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
                }
            )
        # Second pass: set parent_id
        for item in CATEGORIES_DATA:
            if item["parent_id"]:
                Category.objects.filter(id=item["id"]).update(parent_id=item["parent_id"])
        self.stdout.write(f"  Category: {len(CATEGORIES_DATA)} records")

    def _seed_attributes(self):
        """Seed AttributeDefinition and AttributeOption models."""
        for item in ATTRIBUTE_DEFINITIONS_DATA:
            AttributeDefinition.objects.update_or_create(
                id=item["id"],
                defaults={
                    "name": item["name"],
                    "display_name": item["display_name"],
                }
            )
        self.stdout.write(f"  AttributeDefinition: {len(ATTRIBUTE_DEFINITIONS_DATA)} records")

        for item in ATTRIBUTE_OPTIONS_DATA:
            AttributeOption.objects.update_or_create(
                id=item["id"],
                defaults={
                    "attribute_id": item["attribute_id"],
                    "value": item["value"],
                }
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
                }
            )
        self.stdout.write(f"  Product: {len(PRODUCTS_DATA)} records")

        for item in PRODUCT_IMAGES_DATA:
            ProductImage.objects.update_or_create(
                id=item["id"],
                defaults={
                    "product_id": item["product_id"],
                    "image": item["image"],
                    "alt_text": item["alt_text"],
                    "sort_order": item["sort_order"],
                }
            )
        self.stdout.write(f"  ProductImage: {len(PRODUCT_IMAGES_DATA)} records")

        for item in PRODUCT_ATTRIBUTE_VALUES_DATA:
            ProductAttributeValue.objects.update_or_create(
                id=item["id"],
                defaults={
                    "product_id": item["product_id"],
                    "option_id": item["option_id"],
                }
            )
        self.stdout.write(f"  ProductAttributeValue: {len(PRODUCT_ATTRIBUTE_VALUES_DATA)} records")

    def _seed_banners(self):
        """Seed Banner model."""
        for item in BANNERS_DATA:
            Banner.objects.update_or_create(
                id=item["id"],
                defaults={
                    "name": item["name"],
                    "image": item["image"],
                    "mobile_image": item["mobile_image"],
                    "url": item["url"],
                    "is_active": item["is_active"],
                    "available_from": self._parse_datetime(item["available_from"]),
                    "available_to": self._parse_datetime(item["available_to"]),
                    "order": item["order"],
                }
            )
        self.stdout.write(f"  Banner: {len(BANNERS_DATA)} records")

    def _seed_homepage_sections(self):
        """Seed HomepageSection and related models."""
        for item in HOMEPAGE_SECTIONS_DATA:
            HomepageSection.objects.update_or_create(
                id=item["id"],
                defaults={
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
            )
        self.stdout.write(f"  HomepageSection: {len(HOMEPAGE_SECTIONS_DATA)} records")

        for item in HOMEPAGE_SECTION_PRODUCTS_DATA:
            HomepageSectionProduct.objects.update_or_create(
                id=item["id"],
                defaults={
                    "section_id": item["section_id"],
                    "product_id": item["product_id"],
                    "order": item["order"],
                }
            )
        self.stdout.write(f"  HomepageSectionProduct: {len(HOMEPAGE_SECTION_PRODUCTS_DATA)} records")

        for item in HOMEPAGE_SECTION_BANNERS_DATA:
            HomepageSectionBanner.objects.update_or_create(
                id=item["id"],
                defaults={
                    "section_id": item["section_id"],
                    "name": item["name"],
                    "image": item["image"],
                    "url": item["url"],
                    "order": item["order"],
                }
            )
        self.stdout.write(f"  HomepageSectionBanner: {len(HOMEPAGE_SECTION_BANNERS_DATA)} records")

    def _seed_media_storage_settings(self):
        """Seed MediaStorageSettings (without AWS keys)."""
        if MEDIA_STORAGE_SETTINGS_DATA:
            settings_obj = MediaStorageSettings.get_settings()
            settings_obj.provider_type = MEDIA_STORAGE_SETTINGS_DATA["provider_type"]
            settings_obj.aws_bucket_name = MEDIA_STORAGE_SETTINGS_DATA["aws_bucket_name"]
            settings_obj.aws_region = MEDIA_STORAGE_SETTINGS_DATA["aws_region"]
            settings_obj.aws_location = MEDIA_STORAGE_SETTINGS_DATA["aws_location"]
            settings_obj.cdn_enabled = MEDIA_STORAGE_SETTINGS_DATA["cdn_enabled"]
            settings_obj.cdn_domain = MEDIA_STORAGE_SETTINGS_DATA["cdn_domain"]
            # AWS keys are NOT set - must be configured manually in CMS
            settings_obj.aws_access_key_id = ""
            settings_obj.aws_secret_access_key = ""
            settings_obj.save()
            self.stdout.write("  MediaStorageSettings: configured (without AWS keys)")

    def _create_superuser(self):
        """Create the default superuser."""
        email = "admin@example.com"
        password = "admin"

        user, created = CustomUser.objects.get_or_create(
            email=email,
            defaults={
                "username": email,
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            }
        )

        if created:
            user.set_password(password)
            user.save()
            EmailAddress.objects.get_or_create(
                user=user,
                email=email,
                defaults={"verified": True, "primary": True}
            )
            self.stdout.write(self.style.SUCCESS(f"  Superuser created: {email} / {password}"))
        else:
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
            "web_topbar",
            "web_footer",
            "web_bottombar",
            "web_customcss",
            "web_sitesettings",
            "catalog_category",
            "catalog_product",
            "catalog_productimage",
            "catalog_attributedefinition",
            "catalog_attributeoption",
            "catalog_productattributevalue",
            "homepage_banner",
            "homepage_homepagesection",
            "homepage_homepagesectionproduct",
            "homepage_homepagesectionbanner",
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

