from django.apps import AppConfig
from django.template import engines
from django.template import loader as template_loader
from django.template.context import make_context


class SupportConfig(AppConfig):
    default_auto_field = "django.db.models.AutoField"
    name = "apps.support"

    def ready(self):
        # Import admin to trigger model registrations
        from apps.support import admin  # noqa: F401

        from allauth.socialaccount.models import SocialAccount, SocialApp, SocialToken
        from django.contrib.auth.models import Group, Permission
        from simple_history import register

        def _register_history(model):
            if hasattr(model, "history"):
                return
            register(model, app="apps.support")

        for model in [Group, Permission, SocialApp, SocialAccount, SocialToken]:
            _register_history(model)

        if getattr(template_loader, "_draft_preview_wrapped", False):
            return

        from .draft_utils import apply_drafts_to_context

        original_render_to_string = template_loader.render_to_string

        def render_to_string_with_drafts(template_name, context=None, request=None, using=None):
            if request and getattr(request, "draft_preview_enabled", False):
                if not request.path.startswith("/admin/"):
                    engine = engines[using] if using else engines.all()[0]
                    ctx = make_context(context, request, autoescape=engine.engine.autoescape)
                    drafts_map = getattr(request, "draft_changes_map", {})
                    template = template_loader.get_template(template_name, using=using)
                    with ctx.bind_template(template.template):
                        apply_drafts_to_context(ctx, drafts_map)
                        return template.template._render(ctx)
            return original_render_to_string(template_name, context, request, using)

        template_loader.render_to_string = render_to_string_with_drafts
        template_loader._draft_preview_wrapped = True
