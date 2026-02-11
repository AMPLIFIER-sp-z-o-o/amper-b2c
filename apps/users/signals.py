from allauth.account.signals import email_confirmed, password_changed, password_reset, user_signed_up
from django.core.files.storage import default_storage
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone

from apps.users.models import CustomUser


@receiver(user_signed_up)
def handle_sign_up(request, user, **kwargs):
    # customize this function to do custom logic on sign up, e.g. send a welcome email
    # or subscribe them to your mailing list.
    pass


@receiver(email_confirmed)
def update_user_email(sender, request, email_address, **kwargs):
    """
    When an email address is confirmed make it the primary email.
    """
    # This also sets user.email to the new email address.
    # hat tip: https://stackoverflow.com/a/29661871/8207
    email_address.set_as_primary()


@receiver(password_changed)
@receiver(password_reset)
def track_password_change(sender, request, user, **kwargs):
    """Record timestamp when user changes or resets their password."""
    user.password_changed_at = timezone.now()
    user.save(update_fields=["password_changed_at"])


@receiver(pre_save, sender=CustomUser)
def remove_old_profile_picture_on_change(sender, instance, **kwargs):
    if not instance.pk:
        return False

    try:
        old_file = sender.objects.get(pk=instance.pk).avatar
    except sender.DoesNotExist:
        return False

    if old_file and old_file.name != instance.avatar.name and default_storage.exists(old_file.name):
        default_storage.delete(old_file.name)


@receiver(post_delete, sender=CustomUser)
def remove_profile_picture_on_delete(sender, instance, **kwargs):
    if instance.avatar and default_storage.exists(instance.avatar.name):
        default_storage.delete(instance.avatar.name)
