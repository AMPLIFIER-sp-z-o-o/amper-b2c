"""
Reusable admin utilities for Django Unfold admin.

This module provides common utilities for admin interfaces, including
image preview generation with consistent styling across all admin views.
"""

import re
from pathlib import Path

from django.utils.html import format_html
from django.utils.safestring import mark_safe


def get_view_url(image_field):
    """
    Get the URL for viewing an image file in browser.
    For S3, presigned URLs already include response-content-disposition=inline
    and response-content-type, so they display directly in browser.
    """
    if not image_field or not image_field.name:
        return None
    # Use the direct URL - for S3 it already has inline disposition
    return image_field.url


def make_image_preview_html(
    image_field,
    alt_text: str = None,
    size: int = 64,
    show_open_link: bool = True,
):
    """
    Generate ProductImageInline-style preview HTML for an image field.

    Features:
    - Thumbnail with rounded corners and subtle shadow
    - Filename tooltip on hover
    - Click to open fullscreen (uses openFullscreen() JS function)
    - "Open in new tab" link (only if image exists on storage)
    - Placeholder icon when no image

    Args:
        image_field: Django ImageField instance (or None)
        alt_text: Alt text for the image (defaults to filename)
        size: Thumbnail size in pixels (default: 64)
        show_open_link: Whether to show "open in new tab" link

    Returns:
        SafeString with HTML markup

    Example:
        def logo_preview(self, obj):
            return make_image_preview_html(obj.logo if obj else None)
        logo_preview.short_description = _("Preview")
    """
    if image_field:
        try:
            # Check if file has a name (path)
            if image_field.name:
                # Use direct URL for thumbnail display (small, cached)
                thumbnail_url = image_field.url
                # Use proxy URL for "open in new tab" to ensure inline display
                view_url = get_view_url(image_field)
                filename = Path(image_field.name).name if image_field.name else ""

                # Generate readable alt from filename if not provided
                if not alt_text:
                    base = Path(filename).stem
                    base = re.sub(r"[_-]+", " ", base)
                    base = re.sub(r"\s+", " ", base).strip()
                    alt_text = (base[:1].upper() + base[1:]) if base else filename

                # Build HTML with thumbnail + optional open link
                open_link_html = ""
                # We show open link if we have a view_url.
                # We skip storage.exists() for performance, especially in list views.
                if show_open_link and view_url:
                    open_link_html = format_html(
                        '<a href="{}" target="_blank" rel="noopener" '
                        'style="display: inline-flex; align-items: center; justify-content: center; '
                        "width: 24px; height: 24px; border-radius: 4px; background: rgba(0,0,0,0.05); "
                        'color: #6b7280; text-decoration: none; margin-left: 8px;" '
                        'title="Open in new tab">'
                        '<span class="material-symbols-outlined" style="font-size: 16px;">open_in_new</span>'
                        "</a>",
                        view_url,
                    )

                return format_html(
                    '<div class="product-image-preview" style="display: flex; align-items: center;">'
                    '<img src="{url}" alt="{alt}" title="{filename}" data-filename="{filename}" '
                    'style="width: {size}px; height: {size}px; object-fit: contain; border-radius: 8px; '
                    "background: #f9fafb; border: 2px solid #f3f4f6; cursor: pointer; "
                    'box-shadow: 0 1px 3px rgba(0,0,0,0.1);" '
                    'onclick="openFullscreen(this)" />'
                    "{open_link}"
                    "</div>",
                    url=thumbnail_url,
                    alt=alt_text,
                    filename=filename,
                    size=size,
                    open_link=open_link_html,
                )
        except Exception:
            pass

    # Placeholder when no image
    return mark_safe(
        f'<div class="product-image-preview">'
        f'<div style="width: {size}px; height: {size}px; background: rgba(0,0,0,0.05); '
        f"border-radius: 8px; border: 1px dashed #d1d5db; display: flex; "
        f'align-items: center; justify-content: center;">'
        f'<span class="material-symbols-outlined" style="color: #9ca3af;">image</span>'
        f"</div>"
        f"</div>"
    )


def make_status_badge_html(is_enabled: bool, available_from, available_to):
    """
    Generate a status badge HTML for availability-based entities.

    Returns a styled badge indicating one of:
    - Disabled: Entity is not enabled/active
    - Pending: Entity is enabled but start date is in the future
    - Expired: Entity is enabled but end date has passed
    - Active: Entity is enabled and currently available

    Args:
        is_enabled: Whether the entity is enabled/active
        available_from: Optional datetime for start of availability
        available_to: Optional datetime for end of availability

    Returns:
        SafeString with HTML badge markup
    """
    from django.utils.translation import gettext_lazy as _

    from apps.utils.datetime_utils import to_wall_clock, wall_clock_now

    if not is_enabled:
        return format_html(
            '<span class="rounded-md text-xs font-bold bg-slate-500/20 text-slate-600 uppercase">{}</span>',
            _("Disabled"),
        )

    now = wall_clock_now()
    available_from = to_wall_clock(available_from)
    available_to = to_wall_clock(available_to)

    if available_from and now < available_from:
        return format_html(
            '<span class="rounded-md text-xs font-bold bg-blue-500/20 text-blue-600 uppercase">{}</span>',
            _("Pending"),
        )
    if available_to and now > available_to:
        return format_html(
            '<span class="rounded-md text-xs font-bold bg-rose-500/20 text-rose-600 uppercase">{}</span>',
            _("Expired"),
        )

    return format_html(
        '<span class="rounded-md text-xs font-bold bg-emerald-500/20 text-emerald-600 uppercase">{}</span>',
        _("Active"),
    )


def make_status_text_html(is_enabled: bool, available_from, available_to):
    """
    Generate a plain status text (no badge background) for list alignment.

    Returns a colored uppercase label indicating one of:
    - Disabled
    - Pending
    - Expired
    - Active
    """
    from django.utils.translation import gettext_lazy as _

    from apps.utils.datetime_utils import to_wall_clock, wall_clock_now

    if not is_enabled:
        return format_html(
            '<span class="text-xs font-bold uppercase text-slate-500">{}</span>',
            _("Disabled"),
        )

    now = wall_clock_now()
    available_from = to_wall_clock(available_from)
    available_to = to_wall_clock(available_to)

    if available_from and now < available_from:
        return format_html(
            '<span class="text-xs font-bold uppercase text-blue-600">{}</span>',
            _("Pending"),
        )
    if available_to and now > available_to:
        return format_html(
            '<span class="text-xs font-bold uppercase text-rose-600">{}</span>',
            _("Expired"),
        )

    return format_html(
        '<span class="text-xs font-bold uppercase text-emerald-600">{}</span>',
        _("Active"),
    )


def filename_to_alt(filename: str) -> str:
    """
    Convert a filename to a human-readable alt text.

    Example:
        "product-image-01.webp" -> "Product image 01"
    """
    if not filename:
        return ""
    base = Path(filename).stem
    base = re.sub(r"[_-]+", " ", base)
    base = re.sub(r"\s+", " ", base).strip()
    if not base:
        return ""
    return base[:1].upper() + base[1:]
