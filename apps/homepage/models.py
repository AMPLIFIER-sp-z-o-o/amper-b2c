import uuid

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.media.storage import DynamicMediaStorage
from apps.utils.datetime_utils import is_within_wall_clock_range, wall_clock_utc_now
from apps.utils.models import BaseModel


def _get_banner_filename(instance, filename):
    """Use random filename to prevent overwriting existing files & to fix caching issues."""
    return f"banners/{uuid.uuid4()}.{filename.split('.')[-1]}"


class Banner(BaseModel):
    """
    Homepage banner model for displaying promotional banners.
    Maximum image width: 1920px. Images will scale responsively for smaller screens.
    """

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
            "Desktop banner. Recommended size: 1920x400 pixels. Displayed on screens wider than 768px. "
            "Images scale to fill the width; the height adjusts automatically to maintain proportions (limited to 600px on desktop)."
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
    url = models.URLField(
        max_length=500,
        verbose_name=_("Target URL"),
        help_text=_("URL to redirect when the banner is clicked"),
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

    class Meta:
        verbose_name = _("Hero Banner")
        verbose_name_plural = _("Hero Banners")
        ordering = ["order", "-created_at"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self._state.adding and self.order == 0:
            max_order = Banner.objects.aggregate(max_order=models.Max("order"))["max_order"]
            if max_order is not None:
                self.order = max_order + 1
        super().save(*args, **kwargs)

    def is_available(self):
        """Check if the banner is currently available based on date range."""
        return is_within_wall_clock_range(self.available_from, self.available_to)

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
        """Return all active and available banners."""
        now = wall_clock_utc_now()
        return (
            cls.objects.filter(
                is_active=True,
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
    BANNER_SECTION = "banner_section", _("Banner section")
    CUSTOM_SECTION = "custom_section", _("Custom section")


class HomepageSection(BaseModel):
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
