from colorfield.fields import ColorField
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.utils.datetime_utils import is_within_wall_clock_range, wall_clock_utc_now
from apps.utils.models import BaseModel, SingletonModel


class TopBar(BaseModel):
    """
    Top bar announcement displayed above the navigation.
    Only one active top bar is shown at a time (the one with lowest order).
    """

    class ContentType(models.TextChoices):
        STANDARD = "standard", _("Standard")
        CUSTOM = "custom", _("Custom")

    name = models.CharField(
        max_length=120,
        verbose_name=_("Name"),
        help_text=_("Internal name for identification."),
    )
    singleton_key = models.PositiveSmallIntegerField(
        default=1,
        unique=True,
        editable=False,
    )
    content_type = models.CharField(
        max_length=20,
        choices=ContentType.choices,
        default=ContentType.STANDARD,
        verbose_name=_("Content type"),
    )
    background_color = models.CharField(
        max_length=50,
        default="#1A56DB",
        verbose_name=_("Background color"),
        help_text=_("Hex code (e.g. #1A56DB) to use as background."),
    )
    text = models.CharField(
        max_length=240,
        verbose_name=_("Text"),
        help_text=_("Message displayed in the top bar."),
    )
    link_label = models.CharField(
        max_length=60,
        blank=True,
        default="",
        verbose_name=_("Link label"),
        help_text=_("Optional call-to-action button label."),
    )
    link_url = models.URLField(
        max_length=500,
        blank=True,
        default="",
        verbose_name=_("Link URL"),
        help_text=_("URL for the call-to-action. If set without label, the text becomes a link."),
    )
    custom_html = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Custom HTML"),
    )
    custom_css = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Custom CSS"),
        help_text=_("Optional CSS styles for the custom HTML. These styles apply only to this section."),
    )
    custom_js = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Custom JavaScript"),
        help_text=_("Optional JavaScript for the custom section. Only available for staff users."),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
        help_text=_("Only active top bars can be displayed."),
    )
    available_from = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Available from"),
        help_text=_("Start date (leave empty for immediate display)."),
    )
    available_to = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Available to"),
        help_text=_("End date (leave empty for no end date)."),
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Order"),
        help_text=_("Lower number = higher priority."),
    )

    class Meta:
        verbose_name = _("Top bar")
        verbose_name_plural = _("Top bar")
        ordering = ["order", "-created_at"]

    def __str__(self) -> str:
        return self.name

    def is_available(self) -> bool:
        return is_within_wall_clock_range(self.available_from, self.available_to)

    @classmethod
    def get_active(cls):
        """Return the currently active top bar (first by order)."""
        now = wall_clock_utc_now()
        return (
            cls.objects.filter(is_active=True)
            .filter(models.Q(available_from__isnull=True) | models.Q(available_from__lte=now))
            .filter(models.Q(available_to__isnull=True) | models.Q(available_to__gte=now))
            .order_by("order", "-created_at")
            .first()
        )


class CustomCSS(SingletonModel):
    """
    Singleton model for site-wide custom CSS styling.
    """

    custom_css = models.TextField(
        _("custom CSS"),
        blank=True,
    )
    custom_css_active = models.BooleanField(
        _("custom CSS active"),
        default=False,
        help_text=_("When enabled, custom CSS is applied to the public site."),
    )

    class Meta:
        verbose_name = _("Custom CSS")
        verbose_name_plural = _("Custom CSS")

    def __str__(self) -> str:
        return str(self._meta.verbose_name)


class SiteSettings(SingletonModel):
    """
    Singleton model for store-wide settings like currency, store name, SEO metadata, etc.
    """

    class Currency(models.TextChoices):
        PLN = "PLN", _("PLN (zł)")
        EUR = "EUR", _("EUR (€)")
        USD = "USD", _("USD ($)")

    CURRENCY_SYMBOLS = {
        "PLN": "zł",
        "EUR": "€",
        "USD": "$",
    }

    store_name = models.CharField(
        max_length=200,
        default="",
        blank=True,
        verbose_name=_("Store name"),
        help_text=_("Name of your store, used in page titles and SEO."),
    )
    site_url = models.URLField(
        default="",
        blank=True,
        verbose_name=_("Site URL"),
        help_text=_("Main URL of the site (e.g. https://example.com)."),
    )
    description = models.TextField(
        default="",
        blank=True,
        verbose_name=_("Site description"),
        help_text=_("Description used in meta tags for SEO."),
    )
    keywords = models.CharField(
        max_length=500,
        default="",
        blank=True,
        verbose_name=_("SEO keywords"),
        help_text=_("Comma-separated keywords for search engines."),
    )
    default_image = models.ImageField(
        upload_to="site/",
        blank=True,
        null=True,
        verbose_name=_("Default image"),
        help_text=_("Image used for social media sharing and search engine previews (og:image)."),
    )
    currency = models.CharField(
        max_length=3,
        choices=Currency.choices,
        default=Currency.PLN,
        verbose_name=_("Currency"),
        help_text=_("Currency symbol displayed on prices. No conversion is performed - this is display only."),
    )

    class Meta:
        verbose_name = _("Site settings")
        verbose_name_plural = _("Site settings")

    def __str__(self) -> str:
        return str(self._meta.verbose_name)

    @property
    def currency_symbol(self) -> str:
        """Return the symbol for the selected currency."""
        return self.CURRENCY_SYMBOLS.get(self.currency, self.currency)


class Footer(SingletonModel):
    """
    Singleton model for customizable footer configuration.
    Supports standard sections with links or custom HTML.
    """

    class ContentType(models.TextChoices):
        STANDARD = "standard", _("Standard")
        CUSTOM = "custom", _("Custom")

    singleton_key = models.PositiveSmallIntegerField(
        default=1,
        unique=True,
        editable=False,
    )
    content_type = models.CharField(
        max_length=20,
        choices=ContentType.choices,
        default=ContentType.STANDARD,
        verbose_name=_("Content type"),
    )
    custom_html = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Custom HTML"),
    )
    custom_css = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Custom CSS"),
        help_text=_("Optional CSS styles for the custom HTML. These styles apply only to this section."),
    )
    custom_js = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Custom JavaScript"),
        help_text=_("Optional JavaScript for the custom section. Only available for staff users."),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
        help_text=_("Toggle footer visibility."),
    )

    class Meta:
        verbose_name = _("Footer")
        verbose_name_plural = _("Footer")

    def __str__(self) -> str:
        return str(self._meta.verbose_name)

    def has_content(self) -> bool:
        """Check if footer has any sections or social media configured."""
        return self.sections.exists() or self.social_media.filter(is_active=True).exists()


class FooterSection(BaseModel):
    """A section in the footer (e.g., Company, Order & Purchases)."""

    footer = models.ForeignKey(
        Footer,
        on_delete=models.CASCADE,
        related_name="sections",
        verbose_name=_("Footer"),
        default=Footer.get_settings,
    )
    name = models.CharField(
        max_length=120,
        verbose_name=_("Section name"),
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Order"),
    )

    class Meta:
        verbose_name = _("Footer section")
        verbose_name_plural = _("Footer sections")
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return self.name


class FooterSectionLink(BaseModel):
    """A link within a footer section."""

    section = models.ForeignKey(
        FooterSection,
        on_delete=models.CASCADE,
        related_name="links",
        verbose_name=_("Section"),
    )
    label = models.CharField(
        max_length=120,
        verbose_name=_("Label"),
    )
    url = models.CharField(
        max_length=500,
        verbose_name=_("URL"),
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Order"),
    )

    class Meta:
        verbose_name = _("Footer section link")
        verbose_name_plural = _("Footer section links")
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return self.label


class FooterSocialMedia(BaseModel):
    """Social media links for the footer."""

    class Platform(models.TextChoices):
        FACEBOOK = "facebook", _("Facebook")
        YOUTUBE = "youtube", _("YouTube")
        INSTAGRAM = "instagram", _("Instagram")
        TWITTER = "twitter", _("Twitter")
        TIKTOK = "tiktok", _("TikTok")

    footer = models.ForeignKey(
        Footer,
        on_delete=models.CASCADE,
        related_name="social_media",
        verbose_name=_("Footer"),
        default=Footer.get_settings,
    )
    platform = models.CharField(
        max_length=20,
        choices=Platform.choices,
        verbose_name=_("Platform"),
    )
    label = models.CharField(
        max_length=60,
        blank=True,
        default="",
        verbose_name=_("Display label"),
        help_text=_("Optional label displayed next to the icon."),
    )
    url = models.URLField(
        max_length=500,
        verbose_name=_("URL"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Order"),
    )

    class Meta:
        verbose_name = _("Social media link")
        verbose_name_plural = _("Social media links")
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return self.label or self.get_platform_display()


class BottomBar(SingletonModel):
    """
    Singleton model for bottom bar configuration.
    Contains legal links displayed between logo and copyright.
    """

    singleton_key = models.PositiveSmallIntegerField(
        default=1,
        unique=True,
        editable=False,
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
        help_text=_("Toggle bottom bar visibility."),
    )

    class Meta:
        verbose_name = _("Bottom bar")
        verbose_name_plural = _("Bottom bar")

    def __str__(self) -> str:
        return str(self._meta.verbose_name)


class BottomBarLink(BaseModel):
    """A link in the bottom bar (e.g., Legal Notice, Terms of Use)."""

    bottom_bar = models.ForeignKey(
        BottomBar,
        on_delete=models.CASCADE,
        related_name="links",
        verbose_name=_("Bottom bar"),
        default=BottomBar.get_settings,
    )
    label = models.CharField(
        max_length=120,
        verbose_name=_("Label"),
    )
    url = models.CharField(
        max_length=500,
        verbose_name=_("URL"),
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Order"),
    )

    class Meta:
        verbose_name = _("Bottom bar link")
        verbose_name_plural = _("Bottom bar links")
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return self.label


class Navbar(SingletonModel):
    """
    Singleton model for navigation bar configuration.
    Allows switching between default (auto-generated from categories)
    and custom (user-defined items) navigation.
    """

    class NavbarMode(models.TextChoices):
        STANDARD = "standard", _("Standard (categories alphabetically)")
        CUSTOM = "custom", _("Custom navigation")

    singleton_key = models.PositiveSmallIntegerField(
        default=1,
        unique=True,
        editable=False,
    )
    mode = models.CharField(
        max_length=20,
        choices=NavbarMode.choices,
        default=NavbarMode.STANDARD,
        verbose_name=_("Navigation mode"),
        help_text=_("Standard: shows categories alphabetically. Custom: shows manually configured items."),
    )

    class Meta:
        verbose_name = _("Navigation bar")
        verbose_name_plural = _("Navigation bar")

    def __str__(self) -> str:
        return str(self._meta.verbose_name)


class NavbarItem(BaseModel):
    """
    A single item in the custom navigation bar.
    Can be a link to an existing category or a custom link with label and URL.
    """

    class ItemType(models.TextChoices):
        CATEGORY = "category", _("Category")
        CUSTOM_LINK = "custom_link", _("Custom link")
        SEPARATOR = "separator", _("Separator")

    navbar = models.ForeignKey(
        Navbar,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Navbar"),
        default=Navbar.get_settings,
    )
    item_type = models.CharField(
        max_length=20,
        choices=ItemType.choices,
        default=ItemType.CATEGORY,
        verbose_name=_("Item type"),
    )
    # For category type
    category = models.ForeignKey(
        "catalog.Category",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="navbar_items",
        verbose_name=_("Category"),
        help_text=_("Select a category to display (only for category type)."),
    )
    # For custom link type
    label = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name=_("Label"),
        help_text=_("Display label for custom links."),
    )
    url = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name=_("URL"),
        help_text=_("URL for custom links. Can be relative (/page) or absolute (https://...)."),
    )
    open_in_new_tab = models.BooleanField(
        default=False,
        verbose_name=_("Open in new tab"),
        help_text=_("If enabled, the link opens in a new browser tab."),
    )
    # Styling options
    label_color = ColorField(
        blank=True,
        default="",
        verbose_name=_("Label color"),
        help_text=_("Optional color for the label text."),
    )
    icon = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name=_("Icon"),
        help_text=_("Optional icon class name (e.g., 'star', 'fire', 'tag')."),
    )
    # Ordering
    order = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Order"),
        help_text=_("Lower number = appears first."),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
        help_text=_("Inactive items are not displayed."),
    )

    class Meta:
        verbose_name = _("Navbar item")
        verbose_name_plural = _("Navbar items")
        ordering = ["order", "id"]

    def __str__(self) -> str:
        if self.item_type == self.ItemType.CATEGORY and self.category:
            return f"{self.category.name}"
        elif self.item_type == self.ItemType.CUSTOM_LINK:
            return self.label or self.url
        elif self.item_type == self.ItemType.SEPARATOR:
            return "--- Separator ---"
        return f"Item {self.pk}"

    def get_display_label(self) -> str:
        """Return the label to display in navigation."""
        if self.item_type == self.ItemType.CATEGORY and self.category:
            return self.label or self.category.name
        return self.label

    def get_url(self) -> str:
        """Return the URL for this item."""
        if self.item_type == self.ItemType.CATEGORY and self.category:
            return self.category.get_absolute_url()
        return self.url

    def get_children(self):
        """Return children for mega menu (only for categories)."""
        if self.item_type == self.ItemType.CATEGORY and self.category:
            return self.category.children.all()
        return []

    @property
    def has_children(self) -> bool:
        """Check if this item has children to display in dropdown."""
        return self.item_type == self.ItemType.CATEGORY and self.category and self.category.children.exists()
