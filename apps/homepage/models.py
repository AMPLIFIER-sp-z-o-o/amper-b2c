import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.media.storage import DynamicMediaStorage
from apps.utils.datetime_utils import is_within_wall_clock_range, wall_clock_utc_now
from apps.utils.models import BaseModel, SingletonModel


def _get_banner_filename(instance, filename):
    """Use random filename to prevent overwriting existing files & to fix caching issues."""
    return f"banners/{uuid.uuid4()}.{filename.split('.')[-1]}"


class BannerType(models.TextChoices):
    SIMPLE = "simple", _("Standard banner")
    CONTENT = "content", _("Full hero banner")


class BannerTextAlignment(models.TextChoices):
    LEFT = "left", _("Left")
    CENTER = "center", _("Center")


class BannerImageAlignment(models.TextChoices):
    TOP = "top", _("Top")
    CENTER = "center", _("Center")
    BOTTOM = "bottom", _("Bottom")


class BannerGroup(BaseModel):
    """
    Represents a group of banners of a specific type.
    There should be exactly two instances: one for Standard banner and one for Full hero banner.
    """

    banner_type = models.CharField(
        max_length=20,
        choices=BannerType.choices,
        unique=True,
        verbose_name=_("Banner type"),
    )
    is_active = models.BooleanField(
        default=False,
        verbose_name=_("Active"),
        help_text=_(
            "Only one banner group can be active at a time. Active group's banners are displayed on the homepage."
        ),
    )
    available_from = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Available from"),
        help_text=_("Start date and time for banner display (leave empty for immediate display)"),
    )
    available_to = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Available to"),
        help_text=_("End date and time for banner display (leave empty for no end date)"),
    )

    class Meta:
        verbose_name = _("Banner Group")
        verbose_name_plural = _("Banner Groups")
        ordering = ["-banner_type"]  # Content (Full hero) first, then Simple (Standard)

    def __str__(self):
        return self.get_banner_type_display()

    def save(self, *args, **kwargs):
        # Ensure only one group is active at a time
        if self.is_active:
            BannerGroup.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)
        # Update legacy BannerSettings singleton for backwards compatibility
        self._sync_to_banner_settings()

    def _sync_to_banner_settings(self):
        """Sync active state to legacy BannerSettings singleton."""
        if self.is_active:
            settings = BannerSettings.get_settings()
            settings.active_banner_type = self.banner_type
            settings.available_from = self.available_from
            settings.available_to = self.available_to
            settings.save()

    def is_available(self):
        """Check if banners are currently available based on date range."""
        return is_within_wall_clock_range(self.available_from, self.available_to)

    @classmethod
    def get_active_group(cls):
        """Get the currently active banner group."""
        return cls.objects.filter(is_active=True).first()

    @classmethod
    def ensure_groups_exist(cls):
        """Ensure both banner group instances exist."""
        for banner_type, _ in BannerType.choices:
            cls.objects.get_or_create(
                banner_type=banner_type, defaults={"is_active": banner_type == BannerType.CONTENT}
            )


class BannerSettings(SingletonModel):
    """
    Singleton model for banner display settings.
    Controls which type of banners (Simple or Content) are displayed on the homepage.
    """

    active_banner_type = models.CharField(
        max_length=20,
        choices=BannerType.choices,
        default=BannerType.CONTENT,
        verbose_name=_("Active banner type"),
        help_text=_("Select which type of banners to display on the homepage."),
    )
    available_from = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Available from"),
        help_text=_("Start date and time for banner display (leave empty for immediate display)"),
    )
    available_to = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Available to"),
        help_text=_("End date and time for banner display (leave empty for no end date)"),
    )

    class Meta:
        verbose_name = _("Banner Settings")
        verbose_name_plural = _("Banner Settings")

    def __str__(self):
        return f"Banner Settings ({self.get_active_banner_type_display()})"

    def is_available(self):
        """Check if banners are currently available based on date range."""
        return is_within_wall_clock_range(self.available_from, self.available_to)

    @classmethod
    def get_settings(cls):
        """Return the singleton instance."""
        instance, _ = cls.objects.get_or_create(pk=1)
        return instance


class Banner(BaseModel):
    """
    Homepage banner model for displaying promotional banners.
    Maximum image width: 1920px. Images will scale responsively for smaller screens.
    """

    css_hook = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)

    group = models.ForeignKey(
        BannerGroup,
        on_delete=models.CASCADE,
        related_name="banners",
        verbose_name=_("Banner group"),
        null=True,
        blank=True,
        help_text=_("The banner group this banner belongs to."),
    )
    banner_type = models.CharField(
        max_length=20,
        choices=BannerType.choices,
        default=BannerType.SIMPLE,
        verbose_name=_("Banner type"),
        help_text=_(
            "Standard banner: image only with optional link. Full hero banner: full-screen image with text overlay, badge, and buttons."
        ),
    )
    name = models.CharField(
        max_length=255,
        verbose_name=_("Name"),
        help_text=_("Internal name for identification"),
    )
    image = models.ImageField(
        upload_to=_get_banner_filename,
        storage=DynamicMediaStorage(),
        verbose_name=_("Image"),
        help_text=_(
            "Desktop banner. Recommended size: 1920x512 pixels. Displayed on screens wider than 768px. "
            "Images scale to fill the width; the height adjusts automatically to maintain proportions."
        ),
    )
    mobile_image = models.ImageField(
        upload_to=_get_banner_filename,
        storage=DynamicMediaStorage(),
        verbose_name=_("Mobile Image"),
        help_text=_(
            "Optional mobile-optimized banner. Recommended size: 1080x540 pixels. "
            "Displayed on screens ≤768px. Images scale to fill the width; the height adjusts automatically to maintain proportions. "
            "If not provided, the desktop image will be used."
        ),
        blank=True,
        null=True,
    )
    image_alignment = models.CharField(
        max_length=10,
        choices=BannerImageAlignment.choices,
        default=BannerImageAlignment.CENTER,
        verbose_name=_("Image alignment"),
        help_text=_("How the image is aligned within its container (object-position)."),
    )
    url = models.CharField(
        max_length=500,
        verbose_name=_("Target URL"),
        help_text=_("URL to redirect when the banner is clicked (for simple banners)"),
        blank=True,
        default="",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
        help_text=_("Only active banners will be displayed"),
    )
    available_from = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Available from"),
        help_text=_("Start date and time for banner display (leave empty for immediate display)"),
    )
    available_to = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Available to"),
        help_text=_("End date and time for banner display (leave empty for no end date)"),
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Order"),
        help_text=_("Display order (lower number = higher priority)"),
    )

    # Content banner specific fields
    badge_label = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name=_("Badge label"),
        help_text=_("Short label for the badge (e.g., 'Sale', 'Offer', 'New arrival')."),
    )
    badge_text = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name=_("Badge text"),
        help_text=_("Additional text next to the badge (e.g., 'Save $25 when you spend $250')."),
    )
    title = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Title"),
        help_text=_("Main headline text displayed on the banner."),
    )
    subtitle = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Subtitle"),
        help_text=_("Description text below the title."),
    )
    text_alignment = models.CharField(
        max_length=10,
        choices=BannerTextAlignment.choices,
        default=BannerTextAlignment.LEFT,
        verbose_name=_("Text alignment"),
        help_text=_("Position of the text content on the banner."),
    )
    overlay_opacity = models.PositiveIntegerField(
        default=50,
        verbose_name=_("Overlay opacity (%)"),
        help_text=_("Darkness of the overlay behind text (0-100). Higher = darker."),
    )

    # Primary button
    primary_button_text = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("Primary button text"),
        help_text=_("Text displayed on the primary button."),
    )
    primary_button_url = models.CharField(
        max_length=500,
        blank=True,
        default="#",
        verbose_name=_("Primary button URL"),
        help_text=_("Use '#', relative path (e.g., /shop/), or full URL."),
    )
    primary_button_open_in_new_tab = models.BooleanField(
        default=False,
        verbose_name=_("Primary button opens in new tab"),
    )
    primary_button_icon = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name=_("Primary button icon"),
        help_text=_("Icon name (e.g., 'location', 'play', 'arrow-right'). Leave empty for no icon."),
    )

    # Secondary button
    secondary_button_text = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("Secondary button text"),
        help_text=_("Text displayed on the secondary button."),
    )
    secondary_button_url = models.CharField(
        max_length=500,
        blank=True,
        default="#",
        verbose_name=_("Secondary button URL"),
        help_text=_("Use '#', relative path, or full URL."),
    )
    secondary_button_open_in_new_tab = models.BooleanField(
        default=False,
        verbose_name=_("Secondary button opens in new tab"),
    )
    secondary_button_icon = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name=_("Secondary button icon"),
        help_text=_("Icon name (e.g., 'play', 'arrow-right'). Leave empty for no icon."),
    )

    class Meta:
        verbose_name = _("Banner")
        verbose_name_plural = _("Banners")
        ordering = ["banner_type", "order", "-created_at"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Sync banner_type from group if group is set
        if self.group_id:
            self.banner_type = self.group.banner_type
        # Auto-assign to group based on banner_type if not set
        elif self.banner_type:
            BannerGroup.ensure_groups_exist()
            group = BannerGroup.objects.filter(banner_type=self.banner_type).first()
            if group:
                self.group = group

        if self._state.adding and self.order == 0:
            max_order = Banner.objects.filter(banner_type=self.banner_type).aggregate(max_order=models.Max("order"))[
                "max_order"
            ]
            if max_order is not None:
                self.order = max_order + 1
        super().save(*args, **kwargs)

    def has_image_on_active_storage(self) -> bool:
        """Check if the banner image exists on the currently active storage."""
        if not self.image:
            return False
        try:
            return self.image.storage.exists(self.image.name)
        except Exception:
            return False

    @classmethod
    def get_active_banners(cls):
        """Return all active banners of the currently active type."""
        settings = BannerSettings.get_settings()
        if not settings.is_available():
            return cls.objects.none()

        now = wall_clock_utc_now()
        return (
            cls.objects.filter(
                is_active=True,
                banner_type=settings.active_banner_type,
            )
            .filter(models.Q(available_from__isnull=True) | models.Q(available_from__lte=now))
            .filter(models.Q(available_to__isnull=True) | models.Q(available_to__gte=now))
            .order_by("order", "-created_at")
        )

    @classmethod
    def get_active_banners_with_existing_media(cls):
        """Return active banners whose images exist on the active storage."""
        return [banner for banner in cls.get_active_banners() if banner.has_image_on_active_storage()]


class HomepageSectionType(models.TextChoices):
    PRODUCT_LIST = "product_list", _("Product list")
    PRODUCT_SLIDER = "product_slider", _("Product slider")
    BANNER_SECTION = "banner_section", _("Banner section")
    CUSTOM_SECTION = "custom_section", _("Custom section")
    STOREFRONT_HERO = "storefront_hero", _("Storefront hero")


class HomepageSection(BaseModel):
    css_hook = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)

    section_type = models.CharField(
        max_length=50,
        choices=HomepageSectionType.choices,
        default=HomepageSectionType.PRODUCT_LIST,
        verbose_name=_("Section type"),
    )
    name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Name"),
        help_text=_("Internal name for identification"),
    )
    title = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name=_("Title"),
        help_text=_("Optional title displayed above the section."),
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
        help_text=_("Optional styles for the custom section. Only layout and typography styles are allowed."),
    )
    custom_js = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Custom JavaScript"),
        help_text=_("Optional JavaScript for the custom section. Only available for staff users."),
    )
    is_enabled = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
        help_text=_("Only enabled sections will be displayed."),
    )
    available_from = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Available from"),
        help_text=_("Start date and time for section display (leave empty for immediate display)."),
    )
    available_to = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Available to"),
        help_text=_("End date and time for section display (leave empty for no end date)."),
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Order"),
        help_text=_("Display order (lower number = higher priority)."),
    )
    products = models.ManyToManyField(
        "catalog.Product",
        through="HomepageSectionProduct",
        related_name="homepage_sections",
        blank=True,
    )

    # Storefront Hero specific fields
    subtitle = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Subtitle"),
        help_text=_("Description text below the title (for Storefront Hero)."),
    )
    primary_button_text = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("Primary button text"),
        help_text=_("Text displayed on the primary CTA button."),
    )
    primary_button_url = models.CharField(
        max_length=500,
        blank=True,
        default="#",
        verbose_name=_("Primary button URL"),
        help_text=_("Use '#', relative path (e.g., /shop/), or full URL."),
    )
    primary_button_open_in_new_tab = models.BooleanField(
        default=False,
        verbose_name=_("Primary button opens in new tab"),
        help_text=_("If enabled, the primary button link opens in a new browser tab."),
    )
    secondary_button_text = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("Secondary button text"),
        help_text=_("Text displayed on the secondary outline button."),
    )
    secondary_button_url = models.CharField(
        max_length=500,
        blank=True,
        default="#",
        verbose_name=_("Secondary button URL"),
        help_text=_("Use '#', relative path (e.g., /about/), or full URL."),
    )
    secondary_button_open_in_new_tab = models.BooleanField(
        default=False,
        verbose_name=_("Secondary button opens in new tab"),
        help_text=_("If enabled, the secondary button link opens in a new browser tab."),
    )

    class Meta:
        verbose_name = _("Section")
        verbose_name_plural = _("Sections")
        ordering = ["order", "-created_at"]

    def __str__(self) -> str:
        if self.name:
            return self.name
        if self.title:
            return self.title
        return f"{self.get_section_type_display()} #{self.pk or '-'}"

    def is_available(self) -> bool:
        """Check if the section is currently available based on date range."""
        return is_within_wall_clock_range(self.available_from, self.available_to)

    @classmethod
    def get_active_sections(cls):
        """Return all enabled and available sections."""
        now = wall_clock_utc_now()
        return (
            cls.objects.filter(
                is_enabled=True,
            )
            .filter(models.Q(available_from__isnull=True) | models.Q(available_from__lte=now))
            .filter(models.Q(available_to__isnull=True) | models.Q(available_to__gte=now))
            .order_by("order", "-created_at")
        )


class HomepageSectionProduct(BaseModel):
    section = models.ForeignKey(
        HomepageSection,
        related_name="section_products",
        on_delete=models.CASCADE,
    )
    product = models.ForeignKey(
        "catalog.Product",
        related_name="homepage_section_products",
        on_delete=models.CASCADE,
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Order"),
        help_text=_("Display order (lower number = higher priority)."),
    )

    class Meta:
        verbose_name = _("Homepage section product")
        verbose_name_plural = _("Homepage section products")
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["section", "product"], name="uniq_homepage_section_product"),
        ]

    def __str__(self) -> str:
        return f"{self.section} / {self.product}"

    def save(self, *args, **kwargs):
        # Auto-increment order for new items if not explicitly set
        if self._state.adding and self.order == 0:
            max_order = HomepageSectionProduct.objects.filter(section=self.section).aggregate(
                max_order=models.Max("order")
            )["max_order"]
            if max_order is not None:
                self.order = max_order + 1
        super().save(*args, **kwargs)


def _get_section_banner_filename(instance, filename):
    """Use random filename to prevent overwriting existing files & to fix caching issues."""
    return f"section_banners/{uuid.uuid4()}.{filename.split('.')[-1]}"


class HomepageSectionBanner(BaseModel):
    """
    Banner within a homepage section.
    Maximum combined width of all banners in a section: 1920px.
    """

    css_hook = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)

    section = models.ForeignKey(
        HomepageSection,
        related_name="section_banners",
        on_delete=models.CASCADE,
    )
    name = models.CharField(
        max_length=255,
        verbose_name=_("Name"),
        help_text=_("Internal name for identification"),
    )
    image = models.ImageField(
        upload_to=_get_section_banner_filename,
        storage=DynamicMediaStorage(),
        verbose_name=_("Image"),
        help_text="",
    )
    url = models.URLField(
        max_length=500,
        verbose_name=_("Target URL"),
        help_text=_("URL to redirect when the banner is clicked"),
        blank=True,
        default="",
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Order"),
        help_text=_("Display order (lower number = higher priority)."),
    )

    class Meta:
        verbose_name = _("Section banner")
        verbose_name_plural = _("Section banners")
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return f"{self.section} / {self.name}"

    def save(self, *args, **kwargs):
        # Auto-increment order for new items if not explicitly set
        if self._state.adding and self.order == 0:
            max_order = HomepageSectionBanner.objects.filter(section=self.section).aggregate(
                max_order=models.Max("order")
            )["max_order"]
            if max_order is not None:
                self.order = max_order + 1
        super().save(*args, **kwargs)

    def has_image_on_active_storage(self) -> bool:
        """Check if the banner image exists on the currently active storage."""
        if not self.image:
            return False
        try:
            return self.image.storage.exists(self.image.name)
        except Exception:
            return False


# =============================================================================
# Homepage Section Category Box (for Storefront Hero sections)
# =============================================================================


def _get_section_category_image_filename(instance, filename):
    """Use random filename to prevent overwriting existing files & to fix caching issues."""
    return f"storefront/{uuid.uuid4()}.{filename.split('.')[-1]}"


class HomepageSectionCategoryBox(BaseModel):
    """
    Category box within a Storefront Hero Section.
    Contains customizable title, items, and shop link.
    """

    css_hook = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)

    section = models.ForeignKey(
        HomepageSection,
        related_name="category_boxes",
        on_delete=models.CASCADE,
    )
    title = models.CharField(
        max_length=255,
        verbose_name=_("Title"),
        help_text=_("Box title (e.g., 'Top categories', 'Shop consumer electronics'). Keep it short (2–4 words)."),
    )
    shop_link_text = models.CharField(
        max_length=100,
        default="",
        blank=True,
        verbose_name=_("Shop link text"),
        help_text=_("Text for the link at the bottom (e.g., 'Shop now', 'Browse all')."),
    )
    shop_link_url = models.CharField(
        max_length=500,
        blank=True,
        default="#",
        verbose_name=_("Shop link URL"),
        help_text=_("Use '#', relative path (e.g., /categories/), or full URL."),
    )
    shop_link_open_in_new_tab = models.BooleanField(
        default=False,
        verbose_name=_("Shop link opens in new tab"),
        help_text=_("If enabled, the shop link opens in a new browser tab."),
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Order"),
        help_text=_("Display order (lower number = higher priority)."),
    )

    class Meta:
        verbose_name = _("Category Box")
        verbose_name_plural = _("Category Boxes")
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.title}"

    def save(self, *args, **kwargs):
        if self._state.adding and self.order == 0:
            max_order = HomepageSectionCategoryBox.objects.filter(section=self.section).aggregate(
                max_order=models.Max("order")
            )["max_order"]
            if max_order is not None:
                self.order = max_order + 1
        super().save(*args, **kwargs)


class HomepageSectionCategoryItem(BaseModel):
    """
    Individual item within a Homepage Section Category Box.
    Contains image, name, and optional URL.
    """

    css_hook = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)

    category_box = models.ForeignKey(
        HomepageSectionCategoryBox,
        related_name="items",
        on_delete=models.CASCADE,
    )
    name = models.CharField(
        max_length=100,
        verbose_name=_("Name"),
        help_text=_("Item name (e.g., 'Computers', 'Gaming')."),
    )
    image = models.ImageField(
        upload_to=_get_section_category_image_filename,
        storage=DynamicMediaStorage(),
        verbose_name=_("Image"),
        help_text=_(
            "Item image. Supported formats: SVG (recommended), PNG, JPG, WEBP. "
            "SVG works best for crisp icons. "
            "Example file: category_computers.svg."
        ),
    )
    url = models.CharField(
        max_length=500,
        blank=True,
        default="#",
        verbose_name=_("URL"),
        help_text=_("Use '#', relative path (e.g., /c/computers/), or full URL."),
    )
    open_in_new_tab = models.BooleanField(
        default=False,
        verbose_name=_("Open in new tab"),
        help_text=_("If enabled, the item link opens in a new browser tab."),
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Order"),
        help_text=_("Display order (lower number = higher priority)."),
    )

    class Meta:
        verbose_name = _("Category Item")
        verbose_name_plural = _("Category Items")
        ordering = ["order", "id"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self._state.adding and self.order == 0:
            max_order = HomepageSectionCategoryItem.objects.filter(category_box=self.category_box).aggregate(
                max_order=models.Max("order")
            )["max_order"]
            if max_order is not None:
                self.order = max_order + 1
        super().save(*args, **kwargs)


# =============================================================================
# Storefront Hero Section Models (DEPRECATED - use HomepageSection with section_type=STOREFRONT_HERO)
# =============================================================================


def _get_storefront_image_filename(instance, filename):
    """Use random filename to prevent overwriting existing files & to fix caching issues."""
    return f"storefront/{uuid.uuid4()}.{filename.split('.')[-1]}"


class StorefrontHeroSection(SingletonModel):
    """
    Storefront Hero Section - displays below Hero Banner.
    Contains promotional text, CTA buttons, category boxes, and brand logos.
    """

    css_hook = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)

    # Left side content - Title and CTA
    title = models.CharField(
        max_length=255,
        default="",
        blank=True,
        verbose_name=_("Title"),
        help_text=_("Main headline displayed on the left side."),
    )
    subtitle = models.TextField(
        default="",
        blank=True,
        verbose_name=_("Subtitle"),
        help_text=_("Description text below the title."),
    )
    primary_button_text = models.CharField(
        max_length=100,
        default="",
        blank=True,
        verbose_name=_("Primary button text"),
        help_text=_("Text displayed on the primary CTA button."),
    )
    primary_button_url = models.CharField(
        max_length=500,
        blank=True,
        default="#",
        verbose_name=_("Primary button URL"),
        help_text=_("Use '#', relative path (e.g., /shop/), or full URL."),
    )
    secondary_button_text = models.CharField(
        max_length=100,
        default="",
        blank=True,
        verbose_name=_("Secondary button text"),
        help_text=_("Text displayed on the secondary outline button."),
    )
    secondary_button_url = models.CharField(
        max_length=500,
        blank=True,
        default="#",
        verbose_name=_("Secondary button URL"),
        help_text=_("Use '#', relative path (e.g., /about/), or full URL."),
    )
    primary_button_open_in_new_tab = models.BooleanField(
        default=False,
        verbose_name=_("Primary button opens in new tab"),
        help_text=_("If enabled, the primary button link opens in a new browser tab."),
    )
    secondary_button_open_in_new_tab = models.BooleanField(
        default=False,
        verbose_name=_("Secondary button opens in new tab"),
        help_text=_("If enabled, the secondary button link opens in a new browser tab."),
    )

    # Display settings
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
        help_text=_("Only active sections will be displayed."),
    )
    available_from = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Available from"),
        help_text=_("Start date and time for display (leave empty for immediate display)."),
    )
    available_to = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Available to"),
        help_text=_("End date and time for display (leave empty for no end date)."),
    )

    class Meta:
        verbose_name = _("Storefront Hero Section")
        verbose_name_plural = _("Storefront Hero Sections")

    def __str__(self):
        return self.title[:50] if self.title else "Storefront Hero Section"

    def is_available(self):
        """Check if the section is currently available based on date range."""
        return is_within_wall_clock_range(self.available_from, self.available_to)

    @classmethod
    def get_active_section(cls):
        """Return the singleton instance if it's active and available."""
        now = wall_clock_utc_now()
        instance = (
            cls.objects.filter(is_active=True)
            .filter(models.Q(available_from__isnull=True) | models.Q(available_from__lte=now))
            .filter(models.Q(available_to__isnull=True) | models.Q(available_to__gte=now))
            .prefetch_related(
                models.Prefetch(
                    "category_boxes",
                    queryset=StorefrontCategoryBox.objects.order_by("order", "id").prefetch_related(
                        models.Prefetch(
                            "items",
                            queryset=StorefrontCategoryItem.objects.order_by("order", "id"),
                        )
                    ),
                ),
            )
            .first()
        )
        return instance if instance and instance.is_available() else None


class StorefrontCategoryBox(BaseModel):
    """
    Category box within the Storefront Hero Section.
    Contains customizable title, items, and shop link.
    """

    css_hook = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)

    section = models.ForeignKey(
        StorefrontHeroSection,
        related_name="category_boxes",
        on_delete=models.CASCADE,
    )
    title = models.CharField(
        max_length=255,
        verbose_name=_("Title"),
        help_text=_("Box title (e.g., 'Top categories', 'Shop consumer electronics'). Keep it short (2–4 words)."),
    )
    shop_link_text = models.CharField(
        max_length=100,
        default="",
        blank=True,
        verbose_name=_("Shop link text"),
        help_text=_("Text for the link at the bottom (e.g., 'Shop now', 'Browse all')."),
    )
    shop_link_url = models.CharField(
        max_length=500,
        blank=True,
        default="#",
        verbose_name=_("Shop link URL"),
        help_text=_("Use '#', relative path (e.g., /categories/), or full URL."),
    )
    shop_link_open_in_new_tab = models.BooleanField(
        default=False,
        verbose_name=_("Shop link opens in new tab"),
        help_text=_("If enabled, the shop link opens in a new browser tab."),
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Order"),
        help_text=_("Display order (lower number = higher priority)."),
    )

    class Meta:
        verbose_name = _("Category Box")
        verbose_name_plural = _("Category Boxes")
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.title}"

    def save(self, *args, **kwargs):
        if self._state.adding and self.order == 0:
            max_order = StorefrontCategoryBox.objects.filter(section=self.section).aggregate(
                max_order=models.Max("order")
            )["max_order"]
            if max_order is not None:
                self.order = max_order + 1
        super().save(*args, **kwargs)


class StorefrontCategoryItem(BaseModel):
    """
    Individual item within a Storefront Category Box.
    Contains image, name, and optional URL.
    """

    css_hook = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)

    category_box = models.ForeignKey(
        StorefrontCategoryBox,
        related_name="items",
        on_delete=models.CASCADE,
    )
    name = models.CharField(
        max_length=100,
        verbose_name=_("Name"),
        help_text=_("Item name (e.g., 'Computers', 'Gaming')."),
    )
    image = models.ImageField(
        upload_to=_get_storefront_image_filename,
        storage=DynamicMediaStorage(),
        verbose_name=_("Image"),
        help_text=_(
            "Item image. Supported formats: SVG (recommended), PNG, JPG, WEBP. "
            "SVG works best for crisp icons. "
            "Example file: category_computers.svg."
        ),
    )
    url = models.CharField(
        max_length=500,
        blank=True,
        default="#",
        verbose_name=_("URL"),
        help_text=_("Use '#', relative path (e.g., /c/computers/), or full URL."),
    )
    open_in_new_tab = models.BooleanField(
        default=False,
        verbose_name=_("Open in new tab"),
        help_text=_("If enabled, the item link opens in a new browser tab."),
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Order"),
        help_text=_("Display order (lower number = higher priority)."),
    )

    class Meta:
        verbose_name = _("Category Item")
        verbose_name_plural = _("Category Items")
        ordering = ["order", "id"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self._state.adding and self.order == 0:
            max_order = StorefrontCategoryItem.objects.filter(category_box=self.category_box).aggregate(
                max_order=models.Max("order")
            )["max_order"]
            if max_order is not None:
                self.order = max_order + 1
        super().save(*args, **kwargs)
