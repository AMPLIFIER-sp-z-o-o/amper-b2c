"""
Admin configuration for Media Storage settings and Media Library.
Uses Unfold admin theme for modern UI.
"""

from django.apps import apps
from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.decorators import display

from apps.utils.admin_mixins import HistoryModelAdmin, SingletonAdminMixin

from .models import MediaFile, MediaStorageSettings

# =============================================================================
# Media File Admin
# =============================================================================


@admin.register(MediaFile)
class MediaFileAdmin(HistoryModelAdmin):
    """
    Admin for media files - read-only gallery view of all media in the system.
    Files are added through the application (product images, banners, etc.),
    not manually through admin.
    """

    list_display = [
        "thumbnail_preview",
        "filename",
        "file_type_badge",
        "source_link",
        "file_size_display",
        "created_at",
    ]
    list_display_links = [
        "thumbnail_preview",
        "filename",
    ]
    list_filter = ["file_type", "source_model", "created_at"]
    search_fields = ["filename", "alt_text", "description", "source_model"]
    list_select_related = ["uploaded_by"]
    list_per_page = 50  # Limit items per page for better performance
    show_full_result_count = False  # Disable COUNT(*) query for large tables
    readonly_fields = [
        "file",
        "filename",
        "file_size",
        "file_size_display",
        "width",
        "height",
        "mime_type",
        "file_type",
        "source_model",
        "source_field",
        "source_link_display",
        "thumbnail_large",
        "uploaded_by",
        "created_at",
        "updated_at",
    ]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]

    fieldsets = (
        (
            None,
            {
                "fields": ("thumbnail_large", "file"),
            },
        ),
        (
            _("File Information"),
            {
                "fields": (
                    "filename",
                    "file_type",
                    "mime_type",
                    "file_size_display",
                    ("width", "height"),
                ),
            },
        ),
        (
            _("Source"),
            {
                "fields": ("source_link_display",),
            },
        ),
        (
            _("Metadata"),
            {
                "fields": ("uploaded_by", "created_at", "updated_at"),
            },
        ),
    )

    def has_add_permission(self, request):
        """Disable manual file adding - files come from application."""
        return False

    def has_change_permission(self, request, obj=None):
        """MediaFile is read-only - no changes allowed."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Disable deletion - files should be managed from source models."""
        return False

    @display(description=_("Preview"), ordering="file_type")
    def thumbnail_preview(self, obj):
        """Display thumbnail for images or icon for other file types."""
        if obj.is_image and obj.file:
            url = obj.get_full_url()
            return format_html(
                '<img src="{}" style="width: 48px; height: 48px; object-fit: contain; '
                'background: #f9fafb; border-radius: 8px; border: 1px solid var(--color-gray-200);" />',
                url,
            )
        extension = (obj.extension or "").lower()

        if extension in {"zip", "rar", "7z", "tar", "gz"}:
            icon = "archive"
            color = "text-amber-500"
        elif extension in {"xls", "xlsx", "csv"}:
            icon = "table_chart"
            color = "text-emerald-500"
        elif extension in {"ppt", "pptx"}:
            icon = "slideshow"
            color = "text-purple-500"
        elif extension in {"doc", "docx", "odt", "rtf", "pdf"}:
            icon = "description"
            color = "text-blue-500"
        elif extension in {"txt"}:
            icon = "article"
            color = "text-slate-500"
        elif obj.file_type == "video":
            icon = "movie"
            color = "text-purple-500"
        elif obj.file_type == "audio":
            icon = "audio_file"
            color = "text-amber-500"
        else:
            icon = "attach_file"
            color = "text-slate-500"
        return format_html(
            '<div class="flex items-center justify-center w-12 h-12 bg-neutral-secondary rounded-lg">'
            '<span class="material-symbols-outlined {} text-2xl">{}</span>'
            "</div>",
            color,
            icon,
        )

    @display(description=_("Type"), ordering="file_type")
    def file_type_badge(self, obj):
        """Display file type as colored badge with matching text color."""
        # Each tuple: (background class, text class)
        type_colors = {
            "image": ("bg-emerald-500/20", "text-emerald-600 dark:text-emerald-400"),
            "document": ("bg-blue-500/20", "text-blue-600 dark:text-blue-400"),
            "video": ("bg-purple-500/20", "text-purple-600 dark:text-purple-400"),
            "audio": ("bg-amber-500/20", "text-amber-600 dark:text-amber-400"),
            "other": ("bg-slate-500/20", "text-slate-600 dark:text-slate-400"),
        }
        bg, text = type_colors.get(obj.file_type, ("bg-slate-500/20", "text-slate-600 dark:text-slate-400"))
        return format_html(
            '<span class="px-2 py-1 rounded-md text-xs font-bold {} {} uppercase">{}</span>',
            bg,
            text,
            obj.extension or obj.get_file_type_display(),
        )

    @display(description=_("Source"), ordering="source_model")
    def source_display(self, obj):
        """Display source model as a badge with dynamically generated color."""
        if not obj.source_model:
            return format_html(
                '<span style="display:inline-block; padding:4px 8px; border-radius:6px; font-size:11px; '
                'font-weight:700; text-transform:uppercase; background:rgba(239,68,68,0.2); color:#ef4444;">'
                "{}</span>",
                _("Unknown"),
            )

        # Color palette for dynamic assignment (hex colors for inline styles)
        # Each tuple: (background with 20% opacity, text color)
        color_palette = [
            ("rgba(59,130,246,0.2)", "#3b82f6"),  # blue
            ("rgba(168,85,247,0.2)", "#a855f7"),  # purple
            ("rgba(16,185,129,0.2)", "#10b981"),  # emerald
            ("rgba(245,158,11,0.2)", "#f59e0b"),  # amber
            ("rgba(6,182,212,0.2)", "#06b6d4"),  # cyan
            ("rgba(244,63,94,0.2)", "#f43f5e"),  # rose
            ("rgba(99,102,241,0.2)", "#6366f1"),  # indigo
            ("rgba(20,184,166,0.2)", "#14b8a6"),  # teal
            ("rgba(249,115,22,0.2)", "#f97316"),  # orange
            ("rgba(236,72,153,0.2)", "#ec4899"),  # pink
            ("rgba(132,204,22,0.2)", "#84cc16"),  # lime
            ("rgba(139,92,246,0.2)", "#8b5cf6"),  # violet
        ]

        # Generate consistent color based on hash of source_model
        source_key = obj.source_model.lower()
        color_index = hash(source_key) % len(color_palette)
        bg_color, text_color = color_palette[color_index]

        # Generate readable label from model name (e.g., "catalog.productimage" -> "Product Image")
        model_name = source_key.split(".")[-1] if "." in source_key else source_key
        # Convert camelCase/lowercase to readable format
        import re

        label = re.sub(r"([a-z])([A-Z])", r"\1 \2", model_name)
        label = label.replace("_", " ").title()

        return format_html(
            '<span style="display:inline-block; padding:4px 8px; border-radius:6px; font-size:11px; '
            'font-weight:700; text-transform:uppercase; background:{}; color:{};">'
            "{}</span>",
            bg_color,
            text_color,
            label,
        )

    @display(description=_("Source"), ordering="source_model")
    def source_link(self, obj):
        """Display source model as a clickable badge linking to the source object."""
        import re

        from django.urls import NoReverseMatch, reverse

        if not obj.source_model:
            return format_html(
                '<span style="display:inline-block; padding:4px 8px; border-radius:6px; font-size:11px; '
                'font-weight:700; text-transform:uppercase; background:rgba(239,68,68,0.2); color:#ef4444;">'
                "{}</span>",
                _("Unknown"),
            )

        # Color palette for dynamic assignment
        color_palette = [
            ("rgba(59,130,246,0.2)", "#3b82f6"),  # blue
            ("rgba(168,85,247,0.2)", "#a855f7"),  # purple
            ("rgba(16,185,129,0.2)", "#10b981"),  # emerald
            ("rgba(245,158,11,0.2)", "#f59e0b"),  # amber
            ("rgba(6,182,212,0.2)", "#06b6d4"),  # cyan
            ("rgba(244,63,94,0.2)", "#f43f5e"),  # rose
            ("rgba(99,102,241,0.2)", "#6366f1"),  # indigo
            ("rgba(20,184,166,0.2)", "#14b8a6"),  # teal
            ("rgba(249,115,22,0.2)", "#f97316"),  # orange
            ("rgba(236,72,153,0.2)", "#ec4899"),  # pink
            ("rgba(132,204,22,0.2)", "#84cc16"),  # lime
            ("rgba(139,92,246,0.2)", "#8b5cf6"),  # violet
        ]

        source_key = obj.source_model.lower()
        color_index = hash(source_key) % len(color_palette)
        bg_color, text_color = color_palette[color_index]

        # Generate readable label from model verbose name
        try:
            app_label, model_name_lower = obj.source_model.lower().split(".", 1)
            model = apps.get_model(app_label, model_name_lower)
            label = model._meta.verbose_name.title()
        except Exception:
            model_name = source_key.split(".")[-1] if "." in source_key else source_key
            label = re.sub(r"([a-z])([A-Z])", r"\1 \2", model_name)
            label = label.replace("_", " ").title()

        # Try to build admin URL for the source object
        admin_url = None
        if obj.source_object_id and "." in obj.source_model:
            app_label, model_name_lower = obj.source_model.lower().split(".", 1)
            try:
                admin_url = reverse(
                    f"admin:{app_label}_{model_name_lower}_change",
                    args=[obj.source_object_id],
                )
            except NoReverseMatch:
                pass

        if admin_url:
            return format_html(
                '<a href="{}" target="_blank" rel="noopener" style="display:inline-flex; align-items:center; gap:4px; padding:4px 8px; '
                "border-radius:6px; font-size:11px; font-weight:700; text-transform:uppercase; "
                'background:{}; color:{}; text-decoration:none; transition:transform 0.15s ease, box-shadow 0.15s ease;" '
                'title="Open source in new tab" '
                "onmouseover=\"this.style.transform='scale(1.05)'; this.style.boxShadow='0 2px 8px rgba(0,0,0,0.15)'\" "
                "onmouseout=\"this.style.transform='scale(1)'; this.style.boxShadow='none'\">"
                '{}<span style="font-size:14px;">↗</span></a>',
                admin_url,
                bg_color,
                text_color,
                label,
            )

        # No link available - just show badge
        return format_html(
            '<span style="display:inline-block; padding:4px 8px; border-radius:6px; font-size:11px; '
            'font-weight:700; text-transform:uppercase; background:{}; color:{};">'
            "{}</span>",
            bg_color,
            text_color,
            label,
        )

    @display(description=_("Source"))
    def source_link_display(self, obj):
        """Display source model and field as a clickable badge for the change view."""
        import re

        from django.urls import NoReverseMatch, reverse

        if not obj.source_model:
            return format_html(
                '<div style="display:flex; flex-direction:column; gap:8px;">'
                '<span style="display:inline-block; padding:6px 12px; border-radius:8px; font-size:12px; '
                'font-weight:700; text-transform:uppercase; background:rgba(239,68,68,0.15); color:#ef4444;">'
                "{}</span></div>",
                _("Unknown source"),
            )

        # Color palette for dynamic assignment
        color_palette = [
            ("rgba(59,130,246,0.15)", "#3b82f6"),  # blue
            ("rgba(168,85,247,0.15)", "#a855f7"),  # purple
            ("rgba(16,185,129,0.15)", "#10b981"),  # emerald
            ("rgba(245,158,11,0.15)", "#f59e0b"),  # amber
            ("rgba(6,182,212,0.15)", "#06b6d4"),  # cyan
            ("rgba(244,63,94,0.15)", "#f43f5e"),  # rose
            ("rgba(99,102,241,0.15)", "#6366f1"),  # indigo
            ("rgba(20,184,166,0.15)", "#14b8a6"),  # teal
            ("rgba(249,115,22,0.15)", "#f97316"),  # orange
            ("rgba(236,72,153,0.15)", "#ec4899"),  # pink
        ]

        source_key = obj.source_model.lower()
        color_index = hash(source_key) % len(color_palette)
        bg_color, text_color = color_palette[color_index]

        # Generate readable label from model verbose name
        try:
            app_label, model_name_lower = obj.source_model.lower().split(".", 1)
            model = apps.get_model(app_label, model_name_lower)
            label = model._meta.verbose_name.title()
        except Exception:
            model_name = source_key.split(".")[-1] if "." in source_key else source_key
            label = re.sub(r"([a-z])([A-Z])", r"\1 \2", model_name)
            label = label.replace("_", " ").title()

        # Try to build admin URL for the source object
        admin_url = None
        if obj.source_object_id and "." in obj.source_model:
            app_label, model_name_lower = obj.source_model.lower().split(".", 1)
            try:
                admin_url = reverse(
                    f"admin:{app_label}_{model_name_lower}_change",
                    args=[obj.source_object_id],
                )
            except NoReverseMatch:
                pass

        # Field info
        field_info = ""
        if obj.source_field:
            field_info = format_html(
                '<div style="font-size:11px; color:rgba(148,163,184,0.8); margin-top:4px;">'
                'Field: <span style="font-weight:600;">{}</span></div>',
                obj.source_field,
            )

        if admin_url:
            return format_html(
                '<div style="display:flex; flex-direction:column; gap:4px;">'
                '<a href="{}" target="_blank" rel="noopener" style="display:inline-flex; align-items:center; '
                "gap:6px; padding:8px 14px; border-radius:8px; font-size:12px; font-weight:700; "
                "text-transform:uppercase; background:{}; color:{}; text-decoration:none; "
                'transition:transform 0.15s ease, box-shadow 0.15s ease; width:fit-content;" '
                'title="Open source in new tab" '
                "onmouseover=\"this.style.transform='scale(1.05)'; this.style.boxShadow='0 4px 12px rgba(0,0,0,0.15)'\" "
                "onmouseout=\"this.style.transform='scale(1)'; this.style.boxShadow='none'\">"
                "{}"
                '<span class="material-symbols-outlined" style="font-size:16px;">open_in_new</span>'
                "</a>{}</div>",
                admin_url,
                bg_color,
                text_color,
                label,
                field_info,
            )

        # No link available - just show badge
        return format_html(
            '<div style="display:flex; flex-direction:column; gap:4px;">'
            '<span style="display:inline-block; padding:8px 14px; border-radius:8px; font-size:12px; '
            'font-weight:700; text-transform:uppercase; background:{}; color:{}; width:fit-content;">'
            "{}</span>{}</div>",
            bg_color,
            text_color,
            label,
            field_info,
        )

    @display(description=_("Uploaded by"))
    def uploaded_by_display(self, obj):
        """Display uploaded by user name or email."""
        if obj.uploaded_by:
            user = obj.uploaded_by
            full_name = user.get_full_name().strip()
            email = user.email

            if full_name:
                if email:
                    return f"{full_name} ({email})"
                return full_name
            return email or user.username
        return "-"

    def thumbnail_large(self, obj):
        """Large preview for detail view - handles all file types with fullscreen support."""
        url = obj.get_full_url() if obj.file else None
        extension = (obj.extension or "").lower()
        filename = obj.filename or ""

        def render_download_card(icon, accent, title, subtitle, download_url, note):
            return format_html(
                """
                <div style="width:100%; display:flex; justify-content:center;">
                    <div style="display:flex; flex-direction:column; align-items:center; gap:12px; padding:24px;
                        background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08);
                        border-radius:12px; max-width:520px; width:100%; text-align:center;">
                        <div style="width:72px; height:72px; border-radius:999px; display:flex;
                            align-items:center; justify-content:center; background:{};">
                            <span class="material-symbols-outlined" style="font-size:36px; color:{};">{}</span>
                        </div>
                        <div style="font-weight:600; color:var(--color-text-primary, #e5e7eb); word-break:break-word;">{}</div>
                        <div style="font-size:12px; color:rgba(255,255,255,0.6);">{}</div>
                        <div style="font-size:11px; letter-spacing:0.14em; font-weight:700; text-transform:uppercase; color:{}; margin-top:8px;">{}</div>
                    </div>
                </div>
                """,
                f"{accent}20",
                accent,
                icon,
                title,
                subtitle,
                accent,
                note,
            )

        if obj.is_image and url:
            dimensions = (
                format_html(
                    '<div style="margin-top:8px; font-size:12px; color:rgba(255,255,255,0.65);">{} × {} px</div>',
                    obj.width,
                    obj.height,
                )
                if obj.width and obj.height
                else ""
            )
            return format_html(
                """
                <div style="width:100%; display:flex; flex-direction:column; align-items:center; gap:8px;">
                    <div style="width:100%; min-height:320px; display:flex; align-items:center; justify-content:center;
                        padding:16px; background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08);
                        border-radius:12px;">
                        <a href="{}" target="_blank" style="display:block; transition:opacity 0.2s;" onmouseover="this.style.opacity='0.8'" onmouseout="this.style.opacity='1'">
                            <img id="preview-image" src="{}" alt="{}" data-filename="{}"
                                style="max-width:100%; max-height:420px; object-fit:contain; border-radius:10px;
                                border:1px solid rgba(255,255,255,0.12); cursor:pointer;" onclick="event.preventDefault(); event.stopPropagation(); openFullscreen(this);" />
                        </a>
                    </div>
                    {}
                </div>
                """,
                url,
                url,
                filename,
                filename,
                dimensions,
            )

        if obj.file_type == "video" and url:
            return format_html(
                """
                <div style="width:100%; display:flex; justify-content:center;">
                    <video controls style="max-width:100%; max-height:420px; border-radius:12px;
                        border:1px solid rgba(255,255,255,0.08); background:#000;">
                        <source src="{}" type="{}">Your browser does not support video playback.
                    </video>
                </div>
                """,
                url,
                obj.mime_type or "video/mp4",
            )

        if obj.file_type == "audio" and url:
            return format_html(
                """
                <div style="width:100%; display:flex; justify-content:center;">
                    <div style="display:flex; flex-direction:column; align-items:center; gap:14px; padding:24px;
                        background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08);
                        border-radius:12px; max-width:520px; width:100%;">
                        <div style="width:72px; height:72px; border-radius:999px; display:flex;
                            align-items:center; justify-content:center; background:rgba(245,158,11,0.2);">
                            <span class="material-symbols-outlined" style="font-size:36px; color:#f59e0b;">audio_file</span>
                        </div>
                        <div style="text-align:center; font-weight:600; color:var(--color-text-primary, #e5e7eb); word-break:break-word;">{}</div>
                        <audio controls style="width:100%;">
                            <source src="{}" type="{}">Your browser does not support audio playback.
                        </audio>
                    </div>
                </div>
                """,
                filename,
                url,
                obj.mime_type or "audio/mpeg",
            )

        if obj.file_type == "document" and extension == "pdf" and url:
            return format_html(
                """
                <div style="width:100%; display:flex; justify-content:center;">
                    <div style="width:100%; display:flex; flex-direction:column; gap:12px;">
                        <iframe src="{}" style="width:100%; height:520px; border-radius:12px;
                            border:1px solid rgba(255,255,255,0.08); background:#fff;"></iframe>
                        <div style="display:flex; gap:8px; flex-wrap:wrap;">
                            <a href="{}" target="_blank" style="display:inline-flex; align-items:center; gap:8px;
                                padding:10px 16px; border-radius:10px; background:#2563eb; color:#fff; font-weight:600; text-decoration:none;">
                                <span class="material-symbols-outlined" style="font-size:18px;">open_in_new</span>Open in new tab</a>
                        </div>
                        <div style="font-size:12px; color:rgba(255,255,255,0.6);">
                            If the preview does not load, use the "Open in new tab" button or click the download link below.
                        </div>
                    </div>
                </div>
                """,
                url,
                url,
            )

        if url:
            if extension in {"doc", "docx", "odt", "rtf"}:
                return render_download_card(
                    "description", "#3b82f6", filename, obj.file_size_display, url, "Download to view"
                )
            if extension in {"xls", "xlsx", "csv"}:
                return render_download_card(
                    "table_chart", "#22c55e", filename, obj.file_size_display, url, "Download to view"
                )
            if extension in {"ppt", "pptx"}:
                return render_download_card(
                    "slideshow", "#a855f7", filename, obj.file_size_display, url, "Download to view"
                )
            if extension in {"txt"}:
                return render_download_card(
                    "article", "#94a3b8", filename, obj.file_size_display, url, "Download to view"
                )
            if extension in {"zip", "rar", "7z", "tar", "gz"}:
                return render_download_card(
                    "archive", "#f59e0b", filename, obj.file_size_display, url, "Download to view"
                )
            if obj.file_type == "document":
                return render_download_card(
                    "description", "#3b82f6", filename, obj.file_size_display, url, "Download to view"
                )
            if obj.file_type == "other":
                return render_download_card(
                    "attach_file", "#94a3b8", filename, obj.file_size_display, url, "Download to view"
                )

        return format_html(
            """
            <div style="width:100%; display:flex; justify-content:center;">
                <div style="display:flex; flex-direction:column; align-items:center; gap:10px; padding:24px;
                    background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08);
                    border-radius:12px; max-width:520px; width:100%;">
                    <div style="width:72px; height:72px; border-radius:999px; display:flex; align-items:center;
                        justify-content:center; background:rgba(148,163,184,0.2);">
                        <span class="material-symbols-outlined" style="font-size:36px; color:#94a3b8;">block</span>
                    </div>
                    <div style="font-size:13px; color:rgba(255,255,255,0.7);">No file available</div>
                </div>
            </div>
            """
        )

    thumbnail_large.short_description = _("Preview")


# =============================================================================
# Media Storage Settings Admin
# =============================================================================


@admin.register(MediaStorageSettings)
class MediaStorageSettingsAdmin(SingletonAdminMixin, HistoryModelAdmin):
    """Admin for media storage settings - singleton model with direct form access."""

    def get_readonly_fields(self, request, obj=None):
        """Make aws_bucket_name and aws_region read-only when editing existing object."""
        readonly = list(super().get_readonly_fields(request, obj))
        if obj and obj.pk and obj.aws_bucket_name:
            # Bucket name and region cannot be changed after configuration
            # Changing these would break existing file references
            readonly.extend(["aws_bucket_name", "aws_region"])
        return readonly

    def get_form(self, request, obj=None, **kwargs):
        """Add help text to bucket and region fields."""
        form = super().get_form(request, obj, **kwargs)
        is_configured = obj and obj.pk and obj.aws_bucket_name

        if "aws_bucket_name" in form.base_fields:
            if is_configured:
                form.base_fields["aws_bucket_name"].help_text = _(
                    "Bucket name cannot be changed after configuration. "
                    "To use a different bucket, delete this configuration and create a new one."
                )
            else:
                form.base_fields["aws_bucket_name"].help_text = _(
                    "Enter the name of your S3 bucket. This cannot be changed after configuration."
                )

        if "aws_region" in form.base_fields:
            if is_configured:
                form.base_fields["aws_region"].help_text = _(
                    "Region cannot be changed after configuration. "
                    "To use a different region, delete this configuration and create a new one."
                )
            else:
                form.base_fields["aws_region"].help_text = _(
                    "Select the AWS region where your S3 bucket is located. This cannot be changed after configuration."
                )
        return form

    fieldsets = (
        (
            _("Storage Type"),
            {
                "fields": ("provider_type",),
                "description": format_html(
                    "{}<br><span class='text-amber-600'>{}</span>",
                    _("Choose where media files are stored."),
                    _(
                        "Warning: changing the storage type will hide media that is not present on the currently active storage. "
                        "Files on other storage locations remain in their original folders and will reappear when switching back to that storage."
                    ),
                ),
            },
        ),
        (
            _("Amazon S3 Configuration"),
            {
                "fields": (
                    "aws_access_key_id",
                    "aws_secret_access_key",
                    "aws_bucket_name",
                    "aws_region",
                    "aws_location",
                ),
                "description": _("Your AWS credentials. The secret key is stored encrypted."),
            },
        ),
        (
            _("CDN Configuration"),
            {
                "fields": ("cdn_enabled", "cdn_domain"),
                "description": _("Optional CloudFront or other CDN configuration."),
            },
        ),
    )

    def has_add_permission(self, request):
        """Only allow one settings instance - auto create if needed."""
        return not MediaStorageSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """Allow deletion to reset configuration. Files in S3 remain untouched."""
        return True

    def changelist_view(self, request, extra_context=None):
        """Always redirect to change view or add view - singleton pattern."""
        from django.shortcuts import redirect

        if MediaStorageSettings.objects.exists():
            obj = MediaStorageSettings.get_settings()
            return redirect("admin:media_mediastoragesettings_change", obj.pk)
        else:
            # No settings exist, redirect to add view
            return redirect("admin:media_mediastoragesettings_add")

    def delete_view(self, request, object_id, extra_context=None):
        """Add warning about deletion not affecting S3 files."""
        extra_context = extra_context or {}
        extra_context["delete_confirmation_message"] = _(
            "This will only delete the storage configuration from the database. "
            "Files stored in S3 will NOT be deleted and will remain in the bucket. "
            "You can reconfigure a new storage provider after deletion."
        )
        return super().delete_view(request, object_id, extra_context)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        """Add test connection button context."""
        extra_context = extra_context or {}
        extra_context["show_save_and_continue"] = True
        extra_context["show_save"] = True
        return super().change_view(request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        """Test connection after saving if S3 is selected."""
        super().save_model(request, obj, form, change)

        if obj.provider_type == "s3" and obj.aws_access_key_id and obj.aws_secret_access_key:
            success, message = obj.test_connection()
            if success:
                messages.success(request, f"✓ {message}")
            else:
                messages.warning(request, f"⚠ S3 Connection Test: {message}")
