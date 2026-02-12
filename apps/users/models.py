import hashlib
import uuid
from functools import cached_property

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialApp
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone as tz
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.users.helpers import validate_profile_picture
from apps.utils.models import BaseModel


def _get_avatar_filename(instance, filename):
    """Use random filename prevent overwriting existing files & to fix caching issues."""
    return f"profile-pictures/{uuid.uuid4()}.{filename.split('.')[-1]}"


class CustomUser(AbstractUser):
    """
    Add additional fields to the user model here.
    """

    history = HistoricalRecords()
    avatar = models.FileField(upload_to=_get_avatar_filename, blank=True, validators=[validate_profile_picture])
    language = models.CharField(max_length=10, blank=True, null=True)
    timezone = models.CharField(max_length=100, blank=True, default="")
    password_changed_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_("Password last changed"),
        help_text=_("Timestamp of the last password change."),
    )

    def __str__(self):
        return f"{self.get_full_name()} <{self.email or self.username}>"

    def get_display_name(self) -> str:
        if self.get_full_name().strip():
            return self.get_full_name()
        return self.email or self.username

    @property
    def avatar_url(self) -> str:
        if self.avatar:
            return self.avatar.url
        else:
            return f"https://www.gravatar.com/avatar/{self.gravatar_id}?s=128&d=identicon"

    @property
    def gravatar_id(self) -> str:
        # https://en.gravatar.com/site/implement/hash/
        return hashlib.md5(self.email.lower().strip().encode("utf-8")).hexdigest()

    @cached_property
    def has_verified_email(self):
        return EmailAddress.objects.filter(user=self, verified=True).exists()


class SocialAppSettings(models.Model):
    """
    Extended settings for SocialApp to enable/disable providers without deleting them.
    """

    history = HistoricalRecords()
    social_app = models.OneToOneField(
        SocialApp,
        on_delete=models.CASCADE,
        related_name="app_settings",
        verbose_name=_("Social App"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
        help_text=_("Uncheck to disable this provider without deleting it."),
    )

    class Meta:
        verbose_name = _("Social App Settings")
        verbose_name_plural = _("Social App Settings")

    def __str__(self):
        return f"Settings for {self.social_app.name}"


@receiver(post_save, sender=SocialApp)
def create_social_app_settings(sender, instance, created, **kwargs):
    """Automatically create SocialAppSettings when a SocialApp is created."""
    if created:
        SocialAppSettings.objects.get_or_create(social_app=instance)


class PendingEmailChange(BaseModel):
    """
    Tracks a pending email change request. A verification link is sent to
    the new email; the change is applied only when the user clicks the link.
    Tokens expire after 24 hours.
    """

    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="pending_email_change",
        verbose_name=_("User"),
    )
    new_email = models.EmailField(verbose_name=_("New email address"))
    token = models.CharField(max_length=64, unique=True, verbose_name=_("Verification token"))
    expires_at = models.DateTimeField(verbose_name=_("Expires at"))
    notified_old_email = models.BooleanField(
        default=False,
        verbose_name=_("Notified old email"),
        help_text=_("Whether a notification was sent to the old email."),
    )

    class Meta:
        verbose_name = _("Pending Email Change")
        verbose_name_plural = _("Pending Email Changes")

    def __str__(self):
        return f"{self.user.email} → {self.new_email}"

    @property
    def is_expired(self):
        return tz.now() > self.expires_at

    @classmethod
    def create_for_user(cls, user, new_email):
        """Create (or replace) a pending email change for a user."""
        import secrets
        from datetime import timedelta

        cls.objects.filter(user=user).delete()
        token = secrets.token_urlsafe(48)
        expires_at = tz.now() + timedelta(hours=24)
        return cls.objects.create(
            user=user,
            new_email=new_email,
            token=token,
            expires_at=expires_at,
        )
