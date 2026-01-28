from allauth.socialaccount.adapter import get_adapter
from django import template

from apps.users.models import SocialAppSettings

register = template.Library()


@register.simple_tag(takes_context=True)
def get_socialapps(context):
    """
    Returns a list of active social authentication apps.

    Usage: `{% get_socialapps as socialapps %}`.

    Then within the template context, `socialapps` will hold
    a list of social app providers configured for the current site
    that are marked as active.
    """
    providers = get_adapter().list_providers(context["request"])

    # Get list of disabled provider IDs
    disabled_providers = set(
        SocialAppSettings.objects.filter(is_active=False).values_list("social_app__provider", flat=True)
    )

    active_providers = []
    for provider in providers:
        # Skip disabled providers
        if provider.id in disabled_providers:
            continue

        logo_paths = {
            "twitter_oauth2": "twitter",
        }
        logo_id = logo_paths.get(provider.id, provider.id)
        provider.logo_path = f"images/socialauth/{logo_id}-logo.svg"
        active_providers.append(provider)

    return active_providers
