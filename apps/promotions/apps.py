from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PromotionsConfig(AppConfig):
    default_auto_field = "django.db.models.AutoField"
    name = "apps.promotions"
    verbose_name = _("Promotions")
