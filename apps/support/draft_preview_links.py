"""
Build preview links for draft changes.

This module generates preview URLs for draft changes in the admin.
"""

from __future__ import annotations

from collections.abc import Iterable

from django.contrib import admin
from django.db import models
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

from .draft_utils import apply_draft_to_instance
from .models import DraftChange


def _home_url() -> str:
    try:
        return reverse("web:home")
    except Exception:
        return "/"


def _truncate_label(text: str | None, max_length: int = 46) -> str:
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3]}..."


def _safe_get_absolute_url(obj: object) -> str | None:
    get_url = getattr(obj, "get_absolute_url", None)
    if not callable(get_url):
        return None
    try:
        url = get_url()
    except Exception:
        return None
    return url or None


def _model_admin_has_home_preview(model_class: type) -> bool:
    """Return True only if the model's ModelAdmin declares draft_preview_home = True."""
    model_admin = admin.site._registry.get(model_class)
    if not model_admin:
        return False
    return bool(getattr(model_admin, "draft_preview_home", False))


def _templates_exist_for_model(app_label: str, model_name: str) -> bool:
    """Return True if any generic detail template exists for this model."""
    from django.template import TemplateDoesNotExist
    from django.template.loader import get_template

    for candidate in [
        f"web/{model_name}s/detail.html",
        f"web/{app_label}/{model_name}_detail.html",
        f"{app_label}/{model_name}_detail.html",
    ]:
        try:
            get_template(candidate)
            return True
        except TemplateDoesNotExist:
            continue
    return False


def _label_for_object(obj: models.Model) -> str:
    """Format label as 'Open Draft (ModelName: ObjectLabel)'."""
    model_label = str(obj._meta.verbose_name).title() if hasattr(obj, "_meta") else ""
    obj_label = _truncate_label(str(obj)) if obj else ""
    if model_label and obj_label:
        page_name = f"{model_label}: {obj_label}"
    elif obj_label:
        page_name = obj_label
    else:
        page_name = model_label or str(_("Preview"))
    return str(_("Open Draft")) + f" ({page_name})"


def _resolve_instance(draft: DraftChange) -> models.Model | None:
    if not draft.content_type or not draft.object_id:
        return None
    model_class = draft.content_type.model_class()
    if not model_class:
        return None
    return model_class.objects.filter(pk=draft.object_id).first()


def _get_new_record_preview_url(draft: DraftChange) -> str | None:
    """Get preview URL for a new (unsaved) record."""
    if not draft.content_type:
        return None

    model_class = draft.content_type.model_class()
    if not model_class:
        return None

    # Only provide preview for models registered in admin
    if model_class not in admin.site._registry:
        return None

    # Only provide preview when a detail template actually exists for the model
    app_label = draft.content_type.app_label
    model_name = draft.content_type.model
    if not _templates_exist_for_model(app_label, model_name):
        return None

    try:
        return reverse(
            "support:generic_draft_preview",
            kwargs={
                "app_label": app_label,
                "model_name": model_name,
            },
        )
    except NoReverseMatch:
        return None


def _get_link_for_draft(draft: DraftChange) -> dict[str, str] | None:
    """Get a single preview link for a draft change."""
    # Try existing instance first
    instance = _resolve_instance(draft)
    if instance:
        payload = draft.payload if isinstance(draft.payload, dict) else {}
        form_data = payload.get("form_data", {}) if isinstance(payload, dict) else {}
        temp_files = payload.get("temp_files", {}) if isinstance(payload, dict) else {}
        apply_draft_to_instance(instance, form_data, temp_files)

        url = _safe_get_absolute_url(instance)
        if url:
            return {"label": _label_for_object(instance), "url": url}

        # Fallback for site-wide models that explicitly opt-in via draft_preview_home = True
        if _model_admin_has_home_preview(instance._meta.model):
            home_url = _home_url()
            return {"label": str(_("Open Draft")) + f" ({_('Home')})", "url": home_url}

        return None

    # Try new record preview URL
    new_record_url = _get_new_record_preview_url(draft)
    if new_record_url:
        model_class = draft.content_type.model_class() if draft.content_type else None
        model_name = model_class._meta.verbose_name.title() if model_class else "Record"
        return {"label": str(_("Open Draft")) + f" (New {model_name})", "url": new_record_url}

    # Fallback for site-wide models that explicitly opt-in via draft_preview_home = True
    if draft.content_type:
        model_class = draft.content_type.model_class()
        if model_class and _model_admin_has_home_preview(model_class):
            home_url = _home_url()
            return {"label": str(_("Open Draft")) + f" ({_('Home')})", "url": home_url}

    return None


def build_preview_links(drafts: Iterable[DraftChange]) -> list[dict[str, str]]:
    """
    Build preview links for draft changes.

    Returns a deduplicated list of preview links. Each draft is checked for
    a valid preview URL, and duplicate URLs are removed.
    """
    seen_urls: set[str] = set()
    links: list[dict[str, str]] = []

    for draft in drafts:
        link = _get_link_for_draft(draft)
        if link and link["url"] not in seen_urls:
            seen_urls.add(link["url"])
            links.append(link)

    return links
